// ============================================================
// REST client + health/rate-limit polling (server state)
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

const API_BASE = "";
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
}
