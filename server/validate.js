// Input validation for the session API.
// Whitelists fields, coerces types, and caps lengths so clients can never
// inject internal state (ids, caches) or unbounded payloads.

const CAPTURE_FIELDS = ["observedProperties", "evaluation", "description", "testPerformed", "testResult", "environment", "measuredSignals", "failureType"];

function cleanSessionInput(body) {
  const out = {};
  if (!body || typeof body !== "object") return out;

  if (typeof body.target === "string") {
    const target = body.target.trim().slice(0, 200);
    if (target) out.target = target;
  }
  if (typeof body.domain === "string") out.domain = body.domain.slice(0, 40);
  if (typeof body.goal === "string") out.goal = body.goal.slice(0, 2000);

  if (body.baseline && typeof body.baseline === "object") {
    out.baseline = {
      skillLevel: String(body.baseline.skillLevel ?? "").slice(0, 10),
      historicalPatterns: String(body.baseline.historicalPatterns ?? "").slice(0, 2000),
      previousAttempts: String(body.baseline.previousAttempts ?? "").slice(0, 2000)
    };
  }

  if (body.humanCapture && typeof body.humanCapture === "object") {
    const c = {};
    for (const field of CAPTURE_FIELDS) {
      c[field] = String(body.humanCapture[field] ?? "").slice(0, 4000);
    }
    out.humanCapture = c;
  }

  return out;
}

module.exports = { cleanSessionInput, CAPTURE_FIELDS };
