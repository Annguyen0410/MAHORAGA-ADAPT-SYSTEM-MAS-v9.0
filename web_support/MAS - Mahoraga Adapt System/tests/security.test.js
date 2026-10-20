// Security tests: input validation whitelist for the session API.
const { assert } = require("./harness");
const { cleanSessionInput } = require("../server/validate");

// 1) Unknown/internal fields are dropped, never assigned.
const out = cleanSessionInput({
  target: "pencil",
  id: "../../evil",
  serverId: "x",
  deepAnalysisCache: { hacked: true },
  roadmap: "injected",
  aiAssessment: { fake: true }
});
assert(out.target === "pencil", "target kept");
assert(!("id" in out), "id must be dropped");
assert(!("serverId" in out), "serverId must be dropped");
assert(!("deepAnalysisCache" in out), "deepAnalysisCache must be dropped");
assert(!("roadmap" in out), "roadmap must be dropped");
assert(!("aiAssessment" in out), "aiAssessment must be dropped");

// 2) Type coercion: non-string capture fields become strings.
const coerced = cleanSessionInput({
  target: "pencil",
  humanCapture: { observedProperties: 12345, failureType: null }
});
assert(coerced.humanCapture.observedProperties === "12345", "number coerced to string");
assert(coerced.humanCapture.failureType === "", "null coerced to empty string");

// 3) Length caps.
const big = cleanSessionInput({ target: "x".repeat(500), goal: "y".repeat(3000) });
assert(big.target.length === 200, "target capped at 200");
assert(big.goal.length === 2000, "goal capped at 2000");

// 4) Blank target is dropped (create requires it).
const blank = cleanSessionInput({ target: "   " });
assert(!("target" in blank), "blank target dropped");

// 5) Non-object body is safe.
assert(Object.keys(cleanSessionInput(null)).length === 0, "null body safe");
assert(Object.keys(cleanSessionInput("string")).length === 0, "string body safe");

// 6) Baseline is re-shaped, never passed through.
const baseline = cleanSessionInput({ target: "pencil", baseline: { skillLevel: 3, extra: "x" } });
assert(baseline.baseline.skillLevel === "3", "baseline skillLevel coerced");
assert(!("extra" in baseline.baseline), "baseline extra field dropped");

console.log("  security: field whitelist, type coercion, length caps, non-object safety OK");
