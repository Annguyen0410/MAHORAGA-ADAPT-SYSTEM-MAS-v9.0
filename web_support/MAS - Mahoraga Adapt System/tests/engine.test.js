// Adaptation engine tests: phases, trends, anti-overfit, per-target isolation.
const { standardPage, loadClient } = require("./harness");

const body = `
  const mk = (q, o = {}) => ({
    id: "x", target: "pencil", date: new Date().toISOString(),
    quality: q, effort: o.effort ?? 5, stability: o.stability ?? 5,
    discomfort: o.discomfort ?? 2, note: "", contextChanged: o.ctx ?? false
  });

  const cases = [
    [[], "first-hit", "unknown"],
    [[mk(4)], "calibrating", "unknown"],
    [[mk(3), mk(4), mk(5), mk(6)], "drilling", "improving"],
    [[mk(5), mk(5), mk(5), mk(5)], "refining", "plateau"],
    [[mk(7), mk(6), mk(5)], "stuck", "declining"],
    [[mk(8, { effort: 3, stability: 8 }), mk(8, { effort: 3, stability: 8 }), mk(8, { effort: 3, stability: 8 })], "transferring", "plateau"],
    [[mk(8, { effort: 3, stability: 8 }), mk(8, { effort: 3, stability: 8 }), mk(8, { effort: 3, stability: 8 }), mk(9, { effort: 2, stability: 8, ctx: true })], "immune", "improving"]
  ];
  for (const [hist, phase, trend] of cases) {
    adaptationHistory = normalizeHistory(hist);
    const st = computeAdaptation("pencil");
    if (st.phase !== phase) throw new Error("expected phase " + phase + " got " + st.phase);
    if (st.trend !== trend) throw new Error("expected trend " + trend + " got " + st.trend);
  }

  // Anti-overfit: a single lucky sample must never conclude mastery.
  adaptationHistory = normalizeHistory([mk(9, { effort: 2, stability: 9 })]);
  const st2 = computeAdaptation("pencil");
  if (st2.phase === "transferring" || st2.phase === "immune") throw new Error("single sample overfit: " + st2.phase);

  // Per-target isolation.
  adaptationHistory = normalizeHistory([mk(3), mk(4), mk(5)]);
  const other = computeAdaptation("guitar");
  if (other.phase !== "first-hit") throw new Error("target isolation failed");

  // next-step returns a real instruction for every phase.
  for (const phase of ["first-hit", "calibrating", "drilling", "refining", "transferring", "immune", "stuck"]) {
    const s = nextStepFor({ phase, target: "pencil", spinCount: 4, lastQuality: 8, transferPassed: 0, checkIns: [] }, ["grip", "pressure"]);
    if (!s || s.length < 10) throw new Error("nextStep empty for " + phase);
  }
  console.log("  engine: phases, trends, anti-overfit, isolation, next-step OK");
`;

const page = standardPage();
loadClient({ document: page.document, localStorage: page.localStorage, body });
