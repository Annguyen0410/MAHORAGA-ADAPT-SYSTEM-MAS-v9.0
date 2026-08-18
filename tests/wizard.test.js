// Wizard tests: unlock rules, active/done states, Next-button mirroring.
const { standardPage, loadClient } = require("./harness");

const body = `
  if (wizardStepEnabled(1) !== true || wizardStepEnabled(2) !== false) throw new Error("initial locks wrong");
  goToWizardStep(1);
  if (!window.__dots[0]._classes.has("active")) throw new Error("step1 not active");

  currentSession = {
    id: "t1", target: "pencil", domain: "tool", goal: "g",
    baseline: { skillLevel: "", historicalPatterns: "", previousAttempts: "" },
    createdAt: new Date().toISOString(),
    humanCapture: { observedProperties: "x", evaluation: "", description: "", testPerformed: "", testResult: "", environment: "", measuredSignals: "", failureType: "" },
    aiAssessment: null, roadmap: "", deepAnalysis: null, turns: []
  };
  if (wizardStepEnabled(2) !== true) throw new Error("step2 should unlock with capture");
  goToWizardStep(2);
  if (!window.__dots[0]._classes.has("done")) throw new Error("step1 not marked done");
  if (!window.__dots[1]._classes.has("active")) throw new Error("step2 not active");

  currentSession.roadmap = "plan";
  if (wizardStepEnabled(3) !== true) throw new Error("step3 should unlock with roadmap");
  goToWizardStep(3);
  if (!window.__dots[2]._classes.has("active")) throw new Error("step3 not active");

  // Next buttons mirror the lock state.
  updateWizard();
  const next2 = window.__next.find((b) => b.dataset.nextStep === "2");
  const next3 = window.__next.find((b) => b.dataset.nextStep === "3");
  if (next2.disabled !== false) throw new Error("Next->2 should be enabled");
  if (next3.disabled !== false) throw new Error("Next->3 should be enabled with roadmap");

  // Locked steps are not navigable.
  currentSession.roadmap = "";
  updateWizard();
  goToWizardStep(3);
  if (window.__dots[2]._classes.has("active")) throw new Error("locked step3 became active");
  console.log("  wizard: unlock, active, done, Next-mirror, lock-guard OK");
`;

const page = standardPage();
loadClient({
  document: page.document,
  localStorage: page.localStorage,
  windowExtras: { __dots: page.selectors[".step-dot"], __next: page.selectors["[data-next-step]"] },
  body
});
