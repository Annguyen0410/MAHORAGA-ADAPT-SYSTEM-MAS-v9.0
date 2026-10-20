// Storage and normalization. Classic script, loaded after utils.
const STORAGE_KEYS = {
  session: "mas.currentSession.v2", legacySession: "mas.currentSession.v1",
  templates: "mas.templates.v2", legacyTemplates: "mas.templates.v1",
  history: "mas.adaptationHistory.v1"
};
function sanitizeId(id) {
  return typeof id === "string" && /^[a-zA-Z0-9_-]+$/.test(id) ? id : null;
}
function textValue(value, fallback = "") { return typeof value === "string" ? value : fallback; }
function normalizeSession(session) {
  if (!session || typeof session !== "object" || Array.isArray(session)) return null;
  return {
    id: sanitizeId(session.id) || `session-${Date.now()}`,
    serverId: sanitizeId(session.serverId),
    target: textValue(session.target, "Untitled target"),
    domain: textValue(session.domain, "object"),
    goal: textValue(session.goal, textValue(session.intent)),
    baseline: normalizeBaseline(session.baseline),
    createdAt: textValue(session.createdAt, new Date().toISOString()),
    humanCapture: normalizeCapture(session.humanCapture || legacyCaptureFromTurns(session.turns)),
    aiAssessment: session.aiAssessment && typeof session.aiAssessment === "object" && !Array.isArray(session.aiAssessment) ? session.aiAssessment : null,
    roadmap: textValue(session.roadmap),
    deepAnalysis: session.deepAnalysis && typeof session.deepAnalysis === "object" && !Array.isArray(session.deepAnalysis) ? session.deepAnalysis : null,
    turns: Array.isArray(session.turns) ? session.turns.filter(turn => turn && typeof turn === "object" && !Array.isArray(turn)) : []
  };
}
function normalizeBaseline(baseline) {
  baseline = baseline && typeof baseline === "object" ? baseline : {};
  return {
    skillLevel: typeof baseline.skillLevel === "number" && Number.isFinite(baseline.skillLevel) ? String(baseline.skillLevel) : textValue(baseline.skillLevel),
    historicalPatterns: textValue(baseline.historicalPatterns),
    previousAttempts: textValue(baseline.previousAttempts)
  };
}
function emptyCapture() {
  return { observedProperties: "", evaluation: "", description: "", testPerformed: "", testResult: "", environment: "", measuredSignals: "", failureType: "" };
}
function normalizeCapture(capture) {
  const result = emptyCapture();
  if (capture && typeof capture === "object") {
    for (const key of Object.keys(result)) result[key] = textValue(capture[key]);
  }
  return result;
}
function legacyCaptureFromTurns(turns) {
  const latest = Array.isArray(turns) ? turns[turns.length - 1] : null;
  if (!latest || typeof latest !== "object") return emptyCapture();
  return { observedProperties: latest.observation, evaluation: latest.delta,
    description: latest.invariant, testPerformed: latest.action, testResult: latest.outcome,
    environment: "", measuredSignals: "", failureType: latest.failureType || "model" };
}
function normalizeTemplates(items) {
  if (!Array.isArray(items)) return [];
  return items.filter(item => item && typeof item === "object" && !Array.isArray(item)).map(item => ({
    id: sanitizeId(item.id) || `template-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    target: textValue(item.target, "Untitled target"), domain: textValue(item.domain, "object"),
    invariant: textValue(item.invariant, textValue(item.adjustment, "Reusable adaptation template")),
    assessmentSummary: textValue(item.assessmentSummary, textValue(item.delta)),
    roadmap: textValue(item.roadmap, textValue(item.adjustment)),
    createdAt: textValue(item.createdAt, new Date().toISOString()), status: textValue(item.status, "candidate"),
    evidence: typeof item.evidence === "number" && Number.isFinite(item.evidence) ? Math.max(0, item.evidence) : 0
  }));
}
