// Backup tests: export builds a valid payload; import restores local state.
const { standardPage, loadClient } = require("./harness");

const body = `
  // Seed data.
  currentSession = {
    id: "s1", target: "pencil", domain: "tool", goal: "g",
    baseline: { skillLevel: "3", historicalPatterns: "", previousAttempts: "" },
    createdAt: new Date().toISOString(),
    humanCapture: { observedProperties: "x", evaluation: "", description: "", testPerformed: "", testResult: "", environment: "", measuredSignals: "", failureType: "" },
    aiAssessment: null, roadmap: "plan", deepAnalysis: null, turns: []
  };
  templates = [{ id: "t1", target: "guitar", domain: "tool", invariant: "i", assessmentSummary: "a", roadmap: "r", createdAt: new Date().toISOString(), status: "candidate", evidence: 2 }];
  adaptationHistory = [{ id: "c1", target: "pencil", date: new Date().toISOString(), quality: 6, effort: 4, stability: 5, discomfort: 2, note: "n", contextChanged: false }];

  // Export payload shape.
  const payload = buildBackupPayload();
  if (payload.app !== "mas-backup") throw new Error("wrong app tag");
  if (payload.version !== "9.0.0") throw new Error("wrong version");
  if (!payload.session || payload.templates.length !== 1 || payload.history.length !== 1) throw new Error("payload missing data");

  // Simulate import onto an empty page.
  currentSession = null;
  templates = [];
  adaptationHistory = [];
  const payloadStr = JSON.stringify(payload);
  const RealFileReader = globalThis.FileReader;
  globalThis.FileReader = function () {
    const self = this;
    this.onload = null;
    this.onerror = null;
    this.readAsText = () => {
      Object.defineProperty(self, "result", { value: payloadStr, writable: true });
      if (self.onload) self.onload({});
    };
  };
  try {
    const summary = await importData({ name: "backup.json" });
    if (!summary.session || summary.templates !== 1 || summary.history !== 1) throw new Error("import summary wrong");
    if (!currentSession || currentSession.target !== "pencil") throw new Error("session not restored");
    if (templates.length !== 1 || adaptationHistory.length !== 1) throw new Error("templates/history not restored");
    console.log("  backup: export payload + import round-trip OK");
  } finally {
    globalThis.FileReader = RealFileReader;
  }
`;

const page = standardPage();
loadClient({ document: page.document, localStorage: page.localStorage, body })
  .catch((e) => { console.error("  FAIL: " + e.message); process.exit(1); });
