// REST client. Classic script; shared globals with the other MAS modules.
const API_BASE = "";
let apiAvailable = false;
let geminiAvailable = false;
let rateLimitInfo = { limit: 20, remaining: 20, hits: 0 };
let currentAiModelName = "";

function sessionApiId() {
  return currentSession?.serverId || currentSession?.id || null;
}

async function apiRequest(path, method, body, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const options = { method, signal: controller.signal, cache: "no-store" };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    const res = await fetch(`${API_BASE}${path}`, options);
    let data = await res.json().catch(() => ({ error: res.statusText || "Invalid server response" }));
    if (!data || typeof data !== "object") data = { error: "Invalid server response" };
    return { ok: res.ok && !data.error, data, status: res.status };
  } catch (error) {
    return { ok: false, data: { error: error.name === "AbortError" ? "Server request timed out" : "Server unreachable" }, status: 0 };
  } finally {
    clearTimeout(timer);
  }
}

function apiGet(path) { return apiRequest(path, "GET", undefined, 5000); }
function apiPost(path, body, timeoutMs = 30000) { return apiRequest(path, "POST", body, timeoutMs); }
function apiPut(path, body) { return apiRequest(path, "PUT", body, 5000); }

async function checkApiHealth() {
  const result = await apiGet("/api/health");
  apiAvailable = result.ok;
  geminiAvailable = result.ok && !!result.data.deepAnalysisAvailable;
  currentAiModelName = result.ok ? result.data.aiModel || "" : "";
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
