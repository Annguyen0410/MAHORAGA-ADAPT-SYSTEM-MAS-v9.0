// ============================================================
// Storage keys + session/template normalization
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

const STORAGE_KEYS = {
  session: "mas.currentSession.v2",
  legacySession: "mas.currentSession.v1",
  templates: "mas.templates.v2",
  legacyTemplates: "mas.templates.v1",
  history: "mas.adaptationHistory.v1"
};

function sanitizeId(id) {
  return typeof id === "string" && /^[a-zA-Z0-9_-]+$/.test(id) ? id : null;
}

function normalizeSession(session) {
  if (!session) return null;
  return {
    // Only well-formed ids are trusted; a tampered backup cannot inject a
    // path-like id that would be interpolated into API URLs.
    id: sanitizeId(session.id) || `session-${Date.now()}`,
    serverId: sanitizeId(session.serverId),
    target: session.target || "Untitled target",
    domain: session.domain || "object",
    goal: session.goal || session.intent || "",
    baseline: normalizeBaseline(session.baseline),
    createdAt: session.createdAt || new Date().toISOString(),
    humanCapture: session.humanCapture || legacyCaptureFromTurns(session.turns || []),
    aiAssessment: session.aiAssessment || null,
    roadmap: session.roadmap || "",
    deepAnalysis: session.deepAnalysis || null,
    turns: Array.isArray(session.turns) ? session.turns : []
  };
}

function normalizeBaseline(baseline = {}) {
  return {
    skillLevel: baseline.skillLevel || "",
    historicalPatterns: baseline.historicalPatterns || "",
    previousAttempts: baseline.previousAttempts || ""
  };
}

function legacyCaptureFromTurns(turns) {
  const latest = turns[turns.length - 1];
  if (!latest) return emptyCapture();
  return {
    observedProperties: latest.observation || "",
    evaluation: latest.delta || "",
    description: latest.invariant || "",
    testPerformed: latest.action || "",
    testResult: latest.outcome || "",
    environment: "",
    measuredSignals: "",
    failureType: latest.failureType || "model"
  };
}

function emptyCapture() {
  return {
    observedProperties: "",
    evaluation: "",
    description: "",
    testPerformed: "",
    testResult: "",
    environment: "",
    measuredSignals: "",
    failureType: ""
  };
}

function normalizeTemplates(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => ({
    id: item.id || `template-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    target: item.target || "Untitled target",
    domain: item.domain || "object",
    invariant: item.invariant || item.adjustment || "Reusable adaptation template",
    assessmentSummary: item.assessmentSummary || item.delta || "",
    roadmap: item.roadmap || item.adjustment || "",
    createdAt: item.createdAt || new Date().toISOString(),
    status: item.status || "candidate",
    evidence: item.evidence || 0
  }));
}

// ============================================================
// ADAPTATION ENGINE — the Mahoraga wheel state machine
// The wheel spins with each measured check-in. Phase and trend
// are computed from real data, never from a fixed script.
// ============================================================
