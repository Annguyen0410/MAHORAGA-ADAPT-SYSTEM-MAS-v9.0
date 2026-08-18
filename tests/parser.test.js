// Server-side tests: batched-response parser, contentHash, Gemini budget.
const { assert } = require("./harness");
const { parseBatchedResponse, contentHash } = require("../server/deepAnalysis");
const budget = require("../server/geminiBudget");

// 1) Parser: all 9 sections with ### headers.
const sample = [
  "### ANALYTICAL — Analytical Lens", "wobble correlates with thumb tension",
  "### SYSTEMS — Systems Lens", "feedback loop: grip tightens",
  "### KINESTHETIC — Kinesthetic Lens", "relax the index finger",
  "### TEMPORAL — Temporal Lens", "cramp appears at minute 8",
  "### RELATIONAL — Relational Lens", "desk is stable, no social pressure",
  "### PATTERN — Pattern Lens", "wobble increases when speed rises",
  "### CONSTRAINT — Constraint Lens", "paper tears above 3N",
  "### DIALECTICAL — Dialectical Lens", "precision vs relaxation",
  "### GENERATIVE — Generative Lens", "hold the pencil like a brush"
].join("\n");
const parsed = parseBatchedResponse(sample);
assert(parsed.length === 9, "expected 9 perspectives");
assert(parsed.every((p) => p.analysis && !p.analysis.startsWith("(no section")), "all sections parsed");
assert(parsed[0].analysis.includes("wobble"), "analytical content parsed");
assert(parsed[7].analysis.includes("precision"), "dialectical content parsed");

// 2) Parser: missing section flagged for the repair pass.
const partial = parseBatchedResponse("### ANALYTICAL — Analytical Lens\nOnly this one.");
assert(partial[1].analysis.startsWith("(no section"), "missing section flagged");

// 3) contentHash stable / differs.
const s1 = { target: "pencil", domain: "tool", goal: "g", baseline: {}, humanCapture: { observedProperties: "hex" }, aiAssessment: null };
const s2 = { ...s1, humanCapture: { observedProperties: "hex!" } };
assert(contentHash(s1) === contentHash(s1), "hash stable for identical data");
assert(contentHash(s1) !== contentHash(s2), "hash differs on change");

// 4) Gemini budget.
const before = budget.status().remaining;
budget.record(1);
assert(budget.status().remaining === before - 1, "budget decrements on record");
assert(budget.status().limit === 20, "budget limit is 20");

console.log("  parser/budget: batch parse, repair flag, contentHash, budget OK");
