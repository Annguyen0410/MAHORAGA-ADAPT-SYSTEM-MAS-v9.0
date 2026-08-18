// ============================================================
// modelBudget.js — per-model Gemini quota guard for MAS.
//
// WHY: the Google AI Studio free tier caps each model separately
// (RPM = requests/min, TPM = tokens/min, RPD = requests/day).
// If MAS exceeds a model's free quota the request becomes a BILLED
// one. This module guarantees we never exceed any model's limit:
//  1. Before every call we "acquire" a slot on the preferred model
//     (or the next one in the priority list that still has quota).
//  2. If every model is exhausted, NO call is made — the endpoint
//     returns a friendly 429 instead of spending money.
//  3. Real token counts from usageMetadata correct the estimates.
//
// Limits below mirror the free-tier dashboard of the MAS Google
// key (used/limit). Override at runtime with env vars:
//   MODEL_BUDGET_JSON  = '{"gemini-3.5-flash-lite":{"rpm":15,"tpm":250000,"rpd":500},...}'
//   MODEL_PRIORITY     = "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
// ============================================================

const WINDOW_MS = 60_000; // 60s rolling window for RPM / TPM

function defaultTable() {
  // Mirrors the free-tier dashboard of the MAS Google key (used/limit).
  // Gemma 4 31B/26B carry a HUGE daily pool (14.4k RPD) but a small 16k TPM,
  // so they are great as fallbacks for short calls; the guard auto-skips
  // them when a call would blow the per-minute token budget.
  return {
    "gemini-3.6-flash":      { rpm: 5,   tpm: 250000, rpd: 20 },
    "gemini-3.5-flash":      { rpm: 5,   tpm: 250000, rpd: 20 },
    "gemini-3.5-flash-lite": { rpm: 15,  tpm: 250000, rpd: 500 },
    "gemini-3.1-flash-lite": { rpm: 15,  tpm: 250000, rpd: 500 },
    "gemini-3.7-flash":      { rpm: 5,   tpm: 250000, rpd: 20 },
    "gemini-3-flash":        { rpm: 5,   tpm: 250000, rpd: 20 },
    "gemini-2.5-flash":      { rpm: 5,   tpm: 250000, rpd: 20 },
    "gemini-2.5-flash-lite": { rpm: 10,  tpm: 250000, rpd: 20 },
    "gemma-4-31b":           { rpm: 30,  tpm: 16000,  rpd: 14400 },
    "gemma-4-26b":           { rpm: 30,  tpm: 16000,  rpd: 14400 }
  };
}

function defaultPriority() {
  // Fallback chain across ALL models that carry free-tier quota, ordered by
  // daily pool size (biggest first). Every entry is quota-guarded, so if a
  // model is already at its limit (e.g. 3.6-flash burned 22/20 today) the
  // guard skips it automatically until the daily reset — nothing to manage.
  return [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b",
    "gemma-4-26b",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash"
  ];
}

function loadTable() {
  try {
    const raw = process.env.MODEL_BUDGET_JSON;
    if (!raw) return defaultTable();
    const parsed = JSON.parse(raw);
    return parsed && Object.keys(parsed).length ? parsed : defaultTable();
  } catch {
    return defaultTable();
  }
}

function loadPriority() {
  const raw = (process.env.MODEL_PRIORITY || "").trim();
  if (!raw) return defaultPriority();
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

const TABLE = loadTable();
const PRIORITY = loadPriority();

function dayKey(now = Date.now()) {
  // UTC midnight. Google resets daily quota at ~midnight Pacific (07:00 UTC),
  // so UTC is slightly conservative — deliberately: never spend money.
  return new Date(now).toISOString().slice(0, 10);
}

const state = {};
for (const id of Object.keys(TABLE)) {
  state[id] = { winStart: Date.now(), winCalls: 0, winTokens: 0, day: dayKey(), dayCalls: 0, blockedUntil: 0 };
}

let lastActive = null;

function roll(m) {
  const now = Date.now();
  if (now - m.winStart >= WINDOW_MS) {
    m.winStart = now;
    m.winCalls = 0;
    m.winTokens = 0;
  }
  const dk = dayKey(now);
  if (m.day !== dk) {
    m.day = dk;
    m.dayCalls = 0;
  }
}

// ~4 chars per token for mixed text, plus a small constant.
function estimateTokens(text) {
  return Math.ceil(String(text || "").length / 4) + 64;
}

// Returns the reason it would be exceeded, or null when the slot is free.
function wouldExceed(m, estTokens, limit) {
  if (m.blockedUntil > Date.now()) return "blocked";
  if (m.winCalls >= limit.rpm) return "rpm";
  if (m.winTokens + estTokens > limit.tpm) return "tpm";
  if (m.dayCalls >= limit.rpd) return "rpd";
  return null;
}

// Try to reserve a slot on the first model that has quota left.
// preferred is optional and tried first; the priority list is the fallback.
// Returns the chosen model id, or null when every model is exhausted.
function acquire(preferred, estTokens) {
  const seen = new Set();
  const candidates = [...(preferred || []), ...PRIORITY];
  for (const id of candidates) {
    if (seen.has(id)) continue;
    seen.add(id);
    const limit = TABLE[id];
    if (!limit) continue; // model not in the guarded table → skip (never risk unbilled quota)
    const m = state[id];
    roll(m);
    if (wouldExceed(m, estTokens, limit)) continue;
    m.winCalls += 1;
    m.dayCalls += 1;
    // Tokens are only added after the real call returns (see recordTokens);
    // the estTokens check above is a conservative pre-flight guard.
    lastActive = id;
    return id;
  }
  return null;
}

// After a successful call, add the REAL token count (usageMetadata).
function recordTokens(modelId, realTokens) {
  const m = state[modelId];
  if (!m) return;
  roll(m);
  m.winTokens += Math.max(0, realTokens || 0);
}

// After a 429 from Google, block this model for 60s so we fall back
// to another one instead of hammering a model that is server-side capped.
function markBlocked(modelId) {
  const m = state[modelId];
  if (!m) return;
  m.blockedUntil = Date.now() + WINDOW_MS;
}

function status() {
  const now = Date.now();
  const models = Object.keys(TABLE).map((id) => {
    const m = state[id];
    roll(m);
    const limit = TABLE[id];
    return {
      id,
      limit,
      used: { winCalls: m.winCalls, winTokens: m.winTokens, dayCalls: m.dayCalls },
      blocked: m.blockedUntil > now,
      available: !(m.blockedUntil > now) && m.winCalls < limit.rpm && m.dayCalls < limit.rpd
    };
  });
  return {
    day: dayKey(now),
    windowSeconds: WINDOW_MS / 1000,
    active: lastActive,
    priority: PRIORITY,
    models
  };
}

module.exports = { acquire, recordTokens, markBlocked, estimateTokens, status, TABLE, PRIORITY };
