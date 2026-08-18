// Assessment robustness tests: malformed AI JSON must never crash the
// renderers — normalizeAssessment fills defaults for missing fields.
const { standardPage, loadClient } = require("./harness");

const body = `
  currentSession = createSession("pencil", "tool", "write smoothly");
  currentSession.humanCapture = {
    observedProperties: "hexagonal body", evaluation: "grip unstable",
    description: "standard pencil", testPerformed: "wrote a paragraph",
    testResult: "shaky lines", environment: "desk",
    measuredSignals: "cramp at 8 min", failureType: "grip too tight"
  };

  // Simulate Gemini returning valid JSON but missing the array fields.
  currentSession.aiAssessment = {
    material: "hard", durability: "unknown", frequency: "unknown"
  };

  // These must not throw even though variables/risks/uncertainty are absent.
  renderAssessment();
  const text = assessmentText(currentSession.aiAssessment);
  if (!text.includes("Control variables:")) throw new Error("assessmentText missing variables line");

  const roadmap = generateRoadmapText();
  if (!roadmap.includes("[ADAPTIVE STATE]")) throw new Error("generateRoadmapText failed");

  const inv = inferTemplateCandidate(currentSession, currentSession.aiAssessment);
  if (!inv.includes("strongest control variable")) throw new Error("inferTemplateCandidate failed");

  const packet = completeOutputText();
  if (!packet.includes("MAS COMPLETE PACKET")) throw new Error("completeOutputText failed");

  // null/undefined assessment also safe.
  if (normalizeAssessment(null).variables.length !== 0) throw new Error("normalizeAssessment(null) failed");
  if (normalizeAssessment(undefined).risks.length !== 0) throw new Error("normalizeAssessment(undefined) failed");

  // Field filtering: non-string entries dropped, strings kept.
  const norm = normalizeAssessment({ variables: [1, "grip", null], risks: ["a", {}], material: "m" });
  if (norm.variables.join() !== "grip") throw new Error("variables filtering failed: " + norm.variables);
  if (norm.risks.join() !== "a") throw new Error("risks filtering failed: " + norm.risks);
  if (norm.material !== "m") throw new Error("material passthrough failed");

  console.log("  assessment: malformed AI JSON handled, defaults filled OK");
`;

const page = standardPage();
loadClient({ document: page.document, localStorage: page.localStorage, body });
