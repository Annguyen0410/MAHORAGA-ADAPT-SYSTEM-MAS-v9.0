// Tracks REAL Gemini API calls per rolling window.
// The express rate limiter counts HTTP requests; this counts actual
// AI invocations so batch mode + caching are rewarded, not penalized.
const MAX = parseInt(process.env.AI_RATE_LIMIT_MAX || "20", 10);
const WINDOW_MS = parseInt(process.env.AI_RATE_LIMIT_WINDOW_MS || "3600000", 10);

let count = 0;
let windowStart = Date.now();

function rollWindow() {
  const now = Date.now();
  if (now - windowStart >= WINDOW_MS) {
    count = 0;
    windowStart = now;
  }
}

function record(n = 1) {
  rollWindow();
  count += n;
}

function status() {
  rollWindow();
  return {
    limit: MAX,
    remaining: Math.max(0, MAX - count),
    hits: count,
    windowSeconds: Math.floor(WINDOW_MS / 1000),
    windowMs: WINDOW_MS,
    resetAt: new Date(windowStart + WINDOW_MS).toISOString()
  };
}

module.exports = { record, status, MAX, WINDOW_MS };
