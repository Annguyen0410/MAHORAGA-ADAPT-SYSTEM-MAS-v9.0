// ============================================================
// REST client + health/rate-limit polling (server state)
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

// API base resolution:
//   1. ?api=<url> query param (MeiRemote deep-link override)
//   2. localStorage 'mas_api_base' (manual override)
//   3. same-origin when served by the Node backend (http/https — Render,
//      localhost …)
//   4. fallback to the deployed Render service when opened from file:// or a
//      static host, so MAS always talks to a real backend ("chạy bên render").
const _apiQ = (() => { try { return new URLSearchParams(location.search).get("api"); } catch (e) { return null; } })();
const _apiL = (() => { try { return localStorage.getItem("mas_api_base"); } catch (e) { return null; } })();
let API_BASE = (_apiQ || _apiL || (/^https?:/i.test(location.protocol) ? "" : "https://mahoraga-adapt-system-mas-v9-0.onrender.com")).replace(/\/+$/, "");
let apiAvailable = false;
let geminiAvailable = false;
let rateLimitInfo = { limit: 20, remaining: 20, hits: 0 };

function sessionApiId() {
  return currentSession?.serverId || currentSession?.id || null;
}

async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(5000) });
    return { ok: res.ok, data: res.ok ? await res.json() : await res.json().catch(() => ({ error: res.statusText })), status: res.status };
  } catch (e) { return { ok: false, data: { error: "Server unreachable" }, status: 0 }; }
}

async function apiPost(path, body, timeoutMs = 30000) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs)
    });
    return { ok: res.ok, data: res.ok ? await res.json() : await res.json().catch(() => ({ error: res.statusText })), status: res.status };
  } catch (e) { return { ok: false, data: { error: "Server unreachable" }, status: 0 }; }
}

async function apiPut(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(5000)
    });
    return { ok: res.ok, data: res.ok ? await res.json() : await res.json().catch(() => ({ error: res.statusText })), status: res.status };
  } catch (e) { return { ok: false, data: { error: "Server unreachable" }, status: 0 }; }
}

let currentAiModelName = "";

async function checkApiHealth() {
  const result = await apiGet("/api/health");
  apiAvailable = result.ok;
  if (result.ok) {
    geminiAvailable = !!result.data.deepAnalysisAvailable;
    apiAvailable = result.ok;
    currentAiModelName = result.data.aiModel || "";
  }
  updateDeepBadge();
  return result.ok ? result.data : null;
}

async function pollRateLimit() {
  const result = await apiGet("/api/rate-limit");
  if (result.ok) {
    rateLimitInfo = {
      limit: result.data.limit,
      remaining: result.data.remaining,
      hits: result.data.hits,
      windowSeconds: result.data.windowSeconds,
      resetAt: result.data.resetAt
    };
  }
  updateRateLimitUI();
  fetchModelBudget();
}

// Per-model free-tier quota (RPM/TPM/RPD) enforced by the server.
let modelBudgetInfo = null;

async function fetchModelBudget() {
  const result = await apiGet("/api/models");
  if (result.ok) modelBudgetInfo = result.data;
  updateModelBudgetUI();
}
