// Adaptation panel tests: static form preserved across renders, logCheckIn, captureHash.
const { standardPage, loadClient } = require("./harness");

const page = standardPage({
  els: {
    "#ci-quality": { value: "5" },
    "#ci-effort": { value: "4" },
    "#ci-stability": { value: "6" },
    "#ci-discomfort": { value: "2" },
    "#ci-note": { value: "tried loosening grip" },
    "#ci-context": { checked: true }
  }
});

const body = `
  currentSession = {
    id: "t1", target: "pencil", domain: "tool", goal: "smooth",
    baseline: { skillLevel: "3", historicalPatterns: "", previousAttempts: "" },
    createdAt: new Date().toISOString(),
    humanCapture: {
      observedProperties: "hex wood", evaluation: "grip unstable", description: "pencil",
      testPerformed: "wrote", testResult: "shaky", environment: "desk",
      measuredSignals: "cramp 8min", failureType: "execution"
    },
    aiAssessment: null, roadmap: "", deepAnalysis: null, turns: []
  };

  // Re-render must NOT wipe in-progress form input (static form).
  renderAdaptationPanel();
  renderAdaptationPanel();
  if (window.__note.value !== "tried loosening grip") throw new Error("static form value was wiped!");
  if (!document.querySelector("#adaptation-metrics").innerHTML.includes("Spins")) throw new Error("metrics not rendered");
  if (!document.querySelector("#next-step").innerHTML.includes("Next spin")) throw new Error("next-step not rendered");

  // logCheckIn persists and clears the form after submit.
  logCheckIn();
  const hist = JSON.parse(localStorage.getItem("mas.adaptationHistory.v1"));
  if (!hist || hist.length !== 1) throw new Error("check-in not saved");
  if (hist[0].quality !== 5 || hist[0].note !== "tried loosening grip" || hist[0].contextChanged !== true) throw new Error("check-in data wrong");
  if (window.__note.value !== "") throw new Error("form not cleared after submit");
  if (window.__quality.value !== "") throw new Error("quality input not cleared after submit");

  // captureHash is stable for identical capture, different for changes.
  const hA = captureHash(currentSession.humanCapture);
  const hB = captureHash(currentSession.humanCapture);
  if (hA !== hB) throw new Error("captureHash unstable");
  const hC = captureHash({ ...currentSession.humanCapture, evaluation: "different" });
  if (hA === hC) throw new Error("captureHash should differ on change");
  console.log("  adaptation: static form preserved, logCheckIn, captureHash OK");
`;

loadClient({
  document: page.document,
  localStorage: page.localStorage,
  windowExtras: { __note: page.els["#ci-note"], __quality: page.els["#ci-quality"] },
  body
});
