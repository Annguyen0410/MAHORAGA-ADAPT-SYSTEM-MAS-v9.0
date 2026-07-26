const STORAGE_KEYS = {
  session: "mas.currentSession.v2",
  legacySession: "mas.currentSession.v1",
  templates: "mas.templates.v2",
  legacyTemplates: "mas.templates.v1"
};

const API_BASE = "";
let apiAvailable = false;
let geminiAvailable = false;
let rateLimitInfo = { limit: 20, remaining: 20, hits: 0 };
let isAiCalling = false;

let _saveTimers = {};

function debounceSave(key, fn, ms) {
  clearTimeout(_saveTimers[key]);
  _saveTimers[key] = setTimeout(fn, ms || 600);
}

function sessionApiId() {
  return currentSession?.serverId || currentSession?.id || null;
}

async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(5000) });
    return { ok: res.ok, data: res.ok ? await res.json() : await res.json().catch(() => ({ error: res.statusText })), status: res.status };
  } catch (e) { return { ok: false, data: { error: "Server unreachable" }, status: 0 }; }
}

async function apiPost(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(30000)
    });
    return { ok: res.ok, data: res.ok ? await res.json() : await res.json().catch(() => ({ error: res.statusText })), status: res.status };
  } catch (e) { return { ok: false, data: { error: "Server unreachable" }, status: 0 }; }
}

async function apiPut(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(5000)
    });
    return { ok: res.ok, data: res.ok ? await res.json() : await res.json().catch(() => ({ error: res.statusText })), status: res.status };
  } catch (e) { return { ok: false, data: { error: "Server unreachable" }, status: 0 }; }
}

let currentAiModelName = "";

async function checkApiHealth() {
  const result = await apiGet("/api/health");
  apiAvailable = result.ok;
  if (result.ok) {
    geminiAvailable = !!result.data.deepAnalysisAvailable;
    apiAvailable = result.ok;
    currentAiModelName = result.data.aiModel || "";
  }
  updateDeepBadge();
  return result.ok ? result.data : null;
}

function updateDeepBadge() {
  const badge = document.querySelector("#deep-badge");
  if (!badge) return;
  if (geminiAvailable) {
    const label = currentAiModelName ? `${currentAiModelName} ready` : "AI Analysis ready";
    badge.textContent = label;
    badge.className = "deep-badge online";
  } else {
    badge.textContent = "AI offline";
    badge.className = "deep-badge offline";
  }
}

async function pollRateLimit() {
  const result = await apiGet("/api/rate-limit");
  if (result.ok) {
    rateLimitInfo = {
      limit: result.data.limit,
      remaining: result.data.remaining,
      hits: result.data.hits,
      windowSeconds: result.data.windowSeconds,
      resetAt: result.data.resetAt
    };
  }
  updateRateLimitUI();
}

function formatResetTime(resetAt) {
  if (!resetAt) return "";
  const diff = new Date(resetAt) - new Date();
  if (diff <= 0) return "resets now";
  const mins = Math.ceil(diff / 60000);
  if (mins >= 60) return `resets in ${Math.floor(mins / 60)}h ${mins % 60}m`;
  return `resets in ${mins}m`;
}

function updateRateLimitUI() {
  const badge = document.querySelector("#rate-limit-badge");
  const remainingEl = document.querySelector("#rate-limit-remaining");
  const fillEl = document.querySelector("#rate-limit-fill");
  const statusEl = document.querySelector("#api-status-indicator");
  const limitTextEl = document.querySelector("#rate-limit-text");
  if (!remainingEl || !fillEl || !statusEl) return;

  if (apiAvailable) {
    statusEl.className = "rate-limit-status online";
    statusEl.title = "AI server connected";
    const remaining = rateLimitInfo.remaining ?? 0;
    const limit = rateLimitInfo.limit || 20;
    remainingEl.textContent = remaining;
    const pct = Math.max(0, (remaining / limit) * 100);
    fillEl.style.width = `${pct}%`;
    fillEl.className = "rate-limit-fill" + (pct < 20 ? " danger" : pct < 40 ? " warning" : "");
    if (limitTextEl) {
      const resetStr = formatResetTime(rateLimitInfo.resetAt);
      limitTextEl.textContent = `of ${limit} AI calls — ${resetStr}`;
    }
  } else {
    statusEl.className = "rate-limit-status offline";
    statusEl.title = "AI server offline — running in local mode";
    remainingEl.textContent = "∞";
    fillEl.style.width = "100%";
    fillEl.className = "rate-limit-fill";
    if (limitTextEl) limitTextEl.textContent = "Local mode (no limit)";
  }
}

function showLoading(text) {
  if (isAiCalling) return;
  isAiCalling = true;
  const overlay = document.querySelector("#loading-overlay");
  const textEl = document.querySelector("#loading-text");
  if (textEl) textEl.textContent = text || "Spinning the wheel...";
  if (overlay) overlay.hidden = false;
}

function hideLoading() {
  isAiCalling = false;
  const overlay = document.querySelector("#loading-overlay");
  if (overlay) overlay.hidden = true;
}

const sources = [
  {
    title: "Master Codex v8.5",
    path: "core/MAS_MASTER_CODEX_v8_5.md",
    role: "Defines the human-AI loop and roadmap to mastery."
  },
  {
    title: "Ontological Adaptation",
    path: "core/MAS_v8_5_Ontological_Adaptation.md",
    role: "Primary standard for human sensing, AI structuring, diagnosis, body calibration, and template reuse."
  },
  {
    title: "Genesis and Logic System",
    path: "core/MAS_Genesis_and_Logic_System.md",
    role: "Grounds material, atomic pattern, frequency, and human-AI resonance analysis."
  },
  {
    title: "Operational Mechanisms",
    path: "analysis/MAS_Operational_Mechanisms.md",
    role: "Predictive embodied meta-learning, active inference, error minimization, and template reuse."
  },
  {
    title: "Deep Analysis",
    path: "analysis/MAS_v8_5_Deep_Analysis.md",
    role: "Failure taxonomy and guardrails against false models."
  },
  {
    title: "Expert Review",
    path: "analysis/MAS_Expert_Review_v8_5.md",
    role: "Phase transition rules, self-diagnostic precision, and empirical implementation guidance."
  },
  {
    title: "Mahoraga Edition",
    path: "mythos/MAS_v8_5_Mahoraga_Edition.md",
    role: "Metaphor for first hit, wheel spin, counter, and immunity."
  },
  {
    title: "An's Decade of Mahoraga",
    path: "case_studies/An_Decade_of_Mahoraga.md",
    role: "Long-term example of adapting to self, nature, people, society, and abstract systems."
  }
];

const nodes = [
  {
    id: "observe",
    label: "Observe",
    type: "human",
    x: 15,
    y: 28,
    source: "README.md",
    definition: "Human-first capture of direct sensory invariants before any AI-style interpretation.",
    practice: "Record what the body directly notices: texture, sound, pressure, heat, wobble, posture, timing, and emotional context.",
    related: ["evaluate", "perception-guard"]
  },
  {
    id: "evaluate",
    label: "Evaluate",
    type: "human",
    x: 30,
    y: 28,
    source: "core/MAS_v8_5_Ontological_Adaptation.md",
    definition: "The human judges stability, resistance, risk, effort, and controllability from direct interaction.",
    practice: "Name what seems stable, weak, noisy, durable, fragile, or hard to control.",
    related: ["describe", "constraint-guard"]
  },
  {
    id: "describe",
    label: "Describe",
    type: "human",
    x: 45,
    y: 28,
    source: "core/MAS_Genesis_and_Logic_System.md",
    definition: "The human turns experience into language the AI assessment layer can structure.",
    practice: "Use plain words first. The roadmap generator can only work with the signal you give it.",
    related: ["test", "assess-properties"]
  },
  {
    id: "test",
    label: "Test",
    type: "human",
    x: 60,
    y: 28,
    source: "core/MAS_MASTER_CODEX_v8_5.md",
    definition: "The human performs an initial operational test to produce concrete evidence.",
    practice: "Test one change at a time and write down the result before asking for a roadmap.",
    related: ["assess-properties", "measurement"]
  },
  {
    id: "assess-properties",
    label: "Assess Properties",
    type: "ai",
    x: 25,
    y: 50,
    source: "core/MAS_Genesis_and_Logic_System.md",
    definition: "AI-style analysis of likely material, durability, resistance, vibration/frequency, constraints, and control variables.",
    practice: "Feed in human capture data. Treat inferred properties as hypotheses unless measured.",
    related: ["infer-structure", "frequency"]
  },
  {
    id: "infer-structure",
    label: "Infer Structure",
    type: "ai",
    x: 65,
    y: 50,
    source: "analysis/MAS_v8_5_Deep_Analysis.md",
    definition: "Converts human descriptions into a structured model of what matters for adaptation.",
    practice: "Identify the small set of variables that probably change the result most.",
    related: ["diagnose-constraints", "generate-roadmap"]
  },
  {
    id: "diagnose-constraints",
    label: "Diagnose Constraints",
    type: "ai",
    x: 85,
    y: 50,
    source: "analysis/MAS_Expert_Review_v8_5.md",
    definition: "Classifies failure and uncertainty so the roadmap does not chase false patterns.",
    practice: "Separate perception, model, execution, context, and material/property constraints.",
    related: ["constraint-guard", "generate-roadmap"]
  },
  {
    id: "generate-roadmap",
    label: "Generate Roadmap",
    type: "ai",
    x: 10,
    y: 75,
    source: "core/MAS_MASTER_CODEX_v8_5.md",
    definition: "Creates a fast, detailed adaptation sequence from human capture and AI-style assessment.",
    practice: "Roadmap steps should be short enough to start immediately and precise enough to measure.",
    related: ["calibration", "drill-loop"]
  },
  {
    id: "calibration",
    label: "Calibration",
    type: "roadmap",
    x: 25,
    y: 75,
    source: "core/MAS_v8_5_Ontological_Adaptation.md",
    definition: "Body and attention alignment before intensive adaptation.",
    practice: "Set posture, grip, pressure, distance, timing, and baseline signal before drilling.",
    related: ["drill-loop", "measurement"]
  },
  {
    id: "drill-loop",
    label: "Drill Loop",
    type: "roadmap",
    x: 40,
    y: 75,
    source: "analysis/MAS_Operational_Mechanisms.md",
    definition: "Repeated short practice loop that turns roadmap hypotheses into evidence.",
    practice: "Run small repetitions, record the result, and update the next repetition.",
    related: ["measurement", "refinement"]
  },
  {
    id: "measurement",
    label: "Measurement",
    type: "roadmap",
    x: 55,
    y: 75,
    source: "analysis/MAS_Operational_Mechanisms.md",
    definition: "Tracking signals that show whether adaptation is improving.",
    practice: "Use numbers when available; otherwise track wobble, smoothness, latency, fatigue, error rate, tone, or consistency.",
    related: ["refinement", "template-memory"]
  },
  {
    id: "refinement",
    label: "Refinement",
    type: "roadmap",
    x: 70,
    y: 75,
    source: "core/MAS_v8_5_Ontological_Adaptation.md",
    definition: "Adjustment of technique, model, or context after measured feedback.",
    practice: "Change only the variable most likely to reduce error or cognitive load.",
    related: ["template-memory", "overfit-guard"]
  },
  {
    id: "template-memory",
    label: "Template Memory",
    type: "roadmap",
    x: 85,
    y: 75,
    source: "core/MAS_v8_5_Ontological_Adaptation.md",
    definition: "Saved roadmaps, invariants, and constraints that accelerate similar future adaptations.",
    practice: "Save the roadmap only with context, limits, and success criteria attached.",
    related: ["refinement", "immunity"]
  },
  {
    id: "perception-guard",
    label: "Perception Guard",
    type: "guardrail",
    x: 5,
    y: 50,
    source: "analysis/MAS_v8_5_Deep_Analysis.md",
    definition: "Prevents the system from analyzing bad or incomplete human sensory data.",
    practice: "If capture is vague, return to observation rather than generating a confident roadmap.",
    related: ["observe", "constraint-guard"]
  },
  {
    id: "constraint-guard",
    label: "Constraint Guard",
    type: "guardrail",
    x: 95,
    y: 50,
    source: "analysis/MAS_Expert_Review_v8_5.md",
    definition: "Prevents confusing physical limits, context shifts, or material limits with personal failure.",
    practice: "Mark which parts are uncertain, inferred, or actually measured.",
    related: ["diagnose-constraints", "overfit-guard"]
  },
  {
    id: "overfit-guard",
    label: "Overfit Guard",
    type: "guardrail",
    x: 50,
    y: 92,
    source: "core/MAS_v8_5_Ontological_Adaptation.md",
    definition: "Prevents one successful test from becoming a fake universal rule.",
    practice: "Validate the roadmap in a second context before treating it as a template.",
    related: ["measurement", "template-memory"]
  },
  {
    id: "frequency",
    label: "Frequency / Vibration",
    type: "ai",
    x: 45,
    y: 50,
    source: "core/MAS_Genesis_and_Logic_System.md",
    definition: "A practical assessment category for resonance-like signals: vibration, rhythm, oscillation, timing, sound, flex, or feedback.",
    practice: "Record only what can be sensed or measured. Treat exact frequency as unknown unless a device provides it.",
    related: ["assess-properties", "measurement"]
  },
  {
    id: "first-hit",
    label: "First Hit",
    type: "mythos",
    x: 35,
    y: 8,
    source: "mythos/MAS_v8_5_Mahoraga_Edition.md",
    definition: "The metaphor for the first useful contact with resistance or failure.",
    practice: "Convert the first miss into capture data instead of trying to skip it.",
    related: ["test", "wheel-spin"]
  },
  {
    id: "wheel-spin",
    label: "Wheel Spin",
    type: "mythos",
    x: 50,
    y: 8,
    source: "mythos/Mahoraga_Character_Intro.md",
    definition: "The metaphor for moving from human evidence into structured adaptation.",
    practice: "A spin is complete when the roadmap changes what the human does next.",
    related: ["generate-roadmap", "immunity"]
  },
  {
    id: "immunity",
    label: "Immunity",
    type: "mythos",
    x: 65,
    y: 8,
    source: "mythos/Mahoraga_Naming_Revelation.md",
    definition: "Metaphor for consistent low-effort performance, not literal invulnerability.",
    practice: "Use measurable criteria: lower error, lower effort, faster correction, and better transfer.",
    related: ["template-memory", "overfit-guard"]
  }
];

const nodeById = new Map(nodes.map((node) => [node.id, node]));
const edges = [
  ["observe", "evaluate"],
  ["evaluate", "describe"],
  ["describe", "test"],
  ["test", "assess-properties"],
  ["assess-properties", "frequency"],
  ["frequency", "measurement"],
  ["assess-properties", "infer-structure"],
  ["infer-structure", "diagnose-constraints"],
  ["diagnose-constraints", "generate-roadmap"],
  ["generate-roadmap", "calibration"],
  ["calibration", "drill-loop"],
  ["drill-loop", "measurement"],
  ["measurement", "refinement"],
  ["refinement", "template-memory"],
  ["observe", "perception-guard"],
  ["diagnose-constraints", "constraint-guard"],
  ["measurement", "overfit-guard"],
  ["first-hit", "wheel-spin"],
  ["wheel-spin", "generate-roadmap"],
  ["template-memory", "immunity"]
];

let activeFilter = "all";
let activeNodeId = "observe";
let currentSession = normalizeSession(readJson(STORAGE_KEYS.session, null) || readJson(STORAGE_KEYS.legacySession, null));
let templates = normalizeTemplates(readJson(STORAGE_KEYS.templates, null) || readJson(STORAGE_KEYS.legacyTemplates, []));

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function normalizeSession(session) {
  if (!session) return null;
  return {
    id: session.id || `session-${Date.now()}`,
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
    createdAt: item.createdAt || new Date().toISOString()
  }));
}

function createSession(target, domain, goal) {
  return {
    id: `${Date.now()}-${target.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    target,
    domain,
    goal,
    baseline: normalizeBaseline(),
    createdAt: new Date().toISOString(),
    humanCapture: emptyCapture(),
    aiAssessment: null,
    roadmap: "",
    deepAnalysis: null,
    turns: []
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function visibleNodes() {
  return nodes.filter((node) => activeFilter === "all" || node.type === activeFilter);
}

function renderGraph() {
  const nodeLayer = document.querySelector("#node-layer");
  const edgePaths = document.querySelector("#edge-paths");
  const shown = new Set(visibleNodes().map((node) => node.id));

  edgePaths.innerHTML = edges
    .filter(([from, to]) => shown.has(from) && shown.has(to))
    .map(([from, to]) => {
      const a = nodeById.get(from);
      const b = nodeById.get(to);
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"></line>`;
    })
    .join("");

  nodeLayer.innerHTML = visibleNodes()
    .map((node) => {
      const active = node.id === activeNodeId ? " active" : "";
      return `<button class="graph-node ${node.type}${active}" type="button" data-node="${node.id}" style="left:${node.x}%;top:${node.y}%">${escapeHtml(node.label)}</button>`;
    })
    .join("");

  nodeLayer.querySelectorAll("[data-node]").forEach((button) => {
    button.addEventListener("click", () => selectNode(button.dataset.node));
  });
}

function selectNode(nodeId) {
  activeNodeId = nodeId;
  const node = nodeById.get(nodeId);
  document.querySelector("#node-category").textContent = node.type;
  document.querySelector("#node-title").textContent = node.label;
  document.querySelector("#node-definition").textContent = node.definition;
  document.querySelector("#node-practice").textContent = node.practice;
  document.querySelector("#node-source").textContent = `Source: ${node.source}`;

  const relations = document.querySelector("#node-relations");
  relations.innerHTML = node.related
    .map((id) => {
      const related = nodeById.get(id);
      return related ? `<button type="button" data-relation="${id}">${escapeHtml(related.label)}</button>` : "";
    })
    .join("");

  relations.querySelectorAll("[data-relation]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = "all";
      setActiveFilterButton();
      selectNode(button.dataset.relation);
    });
  });

  renderGraph();
}

function setActiveFilterButton() {
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === activeFilter);
  });
}

function setView(viewName) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelector(`#${viewName}-view`).classList.add("active");
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  if (viewName === "templates") renderTemplates();
  if (viewName === "sources") renderSources();
}

function saveSession() {
  if (currentSession) writeJson(STORAGE_KEYS.session, currentSession);
}

function formValue(id) {
  return document.querySelector(id).value.trim();
}

function renderSession() {
  const summary = document.querySelector("#session-summary");
  const status = document.querySelector("#capture-save-status");
  if (!currentSession) {
    summary.innerHTML = `<div class="empty-state">Define a target above to start.</div>`;
    if (status) status.textContent = "● No capture";
    const scoreEl = document.querySelector("#capture-score");
    if (scoreEl) scoreEl.textContent = "";
    fillSessionForm(null);
    fillCaptureForm(emptyCapture());
    renderAssessment();
    renderRoadmap();
    renderCompleteOutput();
    return;
  }

  fillSessionForm(currentSession);
  fillCaptureForm(currentSession.humanCapture || emptyCapture());
  const captureScore = captureCompleteness(currentSession.humanCapture);
  if (status) status.textContent = `${captureScore}/7 capture fields saved`;
  summary.innerHTML = `
    <div class="summary-metric"><span>Target</span><strong>${escapeHtml(currentSession.target)}</strong></div>
    <div class="summary-metric"><span>Domain</span><strong>${escapeHtml(domainLabel(currentSession.domain))}</strong></div>
    <div class="summary-metric"><span>Started</span><strong>${new Date(currentSession.createdAt).toLocaleString()}</strong></div>
    <div class="summary-metric"><span>Capture completeness</span><strong>${captureScore}/7</strong></div>
    <p>${escapeHtml(currentSession.goal || "No adaptation goal recorded.")}</p>
  `;
  renderAssessment();
  renderRoadmap();
  renderCompleteOutput();
  renderDeepAnalysis(currentSession?.deepAnalysis || null);
  updateStepProgress();
  const scoreEl = document.querySelector("#capture-score");
  if (scoreEl) scoreEl.textContent = `${captureScore}/7 capture fields filled`;
}

function updateStepProgress() {
  const dots = document.querySelectorAll(".step-dot");
  if (!dots.length) return;
  let step = 1;
  if (currentSession) step = 2;
  if (currentSession?.humanCapture && captureCompleteness(currentSession.humanCapture) > 0) step = 3;
  if (currentSession?.aiAssessment || currentSession?.roadmap) step = 4;
  dots.forEach((d, i) => d.classList.toggle("active", i < step));
}

function fillSessionForm(session) {
  document.querySelector("#target-name").value = session?.target || "";
  document.querySelector("#target-domain").value = session?.domain || "object";
  document.querySelector("#target-goal").value = session?.goal || "";
  document.querySelector("#skill-level").value = session?.baseline?.skillLevel || "";
  document.querySelector("#historical-patterns").value = session?.baseline?.historicalPatterns || "";
  document.querySelector("#previous-attempts").value = session?.baseline?.previousAttempts || "";
}

function fillCaptureForm(capture) {
  document.querySelector("#observed-properties").value = capture.observedProperties || "";
  document.querySelector("#evaluation").value = capture.evaluation || "";
  document.querySelector("#description").value = capture.description || "";
  document.querySelector("#test-performed").value = capture.testPerformed || "";
  document.querySelector("#test-result").value = capture.testResult || "";
  document.querySelector("#environment").value = capture.environment || "";
  document.querySelector("#measured-signals").value = capture.measuredSignals || "";
  document.querySelector("#failure-type").value = capture.failureType || "";
}

function captureFromForm() {
  return {
    observedProperties: formValue("#observed-properties"),
    evaluation: formValue("#evaluation"),
    description: formValue("#description"),
    testPerformed: formValue("#test-performed"),
    testResult: formValue("#test-result"),
    environment: formValue("#environment"),
    measuredSignals: formValue("#measured-signals"),
    failureType: document.querySelector("#failure-type").value
  };
}

function captureCompleteness(capture = emptyCapture()) {
  return [
    capture.observedProperties,
    capture.evaluation,
    capture.description,
    capture.testPerformed,
    capture.testResult,
    capture.environment,
    capture.measuredSignals
  ].filter(Boolean).length;
}

function domainLabel(domain) {
  return {
    object: "Physical object",
    environment: "Environment",
    concept: "Concept or mental model",
    tool: "Tool or instrument",
    social: "Human or social system"
  }[domain] || "Physical object";
}

function failureLabel(value) {
  if (!value) return "Not specified";
  return value;
}

function analyzeText(...parts) {
  const text = parts.join(" ").toLowerCase();
  return {
    mentionsHardness: /\b(hard|rigid|stiff|brittle|metal|stone|glass|dense)\b/.test(text),
    mentionsFlex: /\b(flex|bend|soft|rubber|elastic|spring|yield)\b/.test(text),
    mentionsVibration: /\b(vibration|vibrate|buzz|frequency|rhythm|sound|tone|wobble|oscillat)\b/.test(text),
    mentionsHeat: /\b(heat|hot|cold|temperature|thermal|burn)\b/.test(text),
    mentionsFriction: /\b(friction|grip|slip|drag|surface|texture|rough|smooth)\b/.test(text),
    mentionsPeople: /\b(person|people|human|voice|tone|emotion|group|social|relationship)\b/.test(text),
    mentionsAbstract: /\b(concept|idea|belief|logic|model|system|meaning|time|attention)\b/.test(text)
  };
}

function generateAssessment() {
  if (!currentSession) return null;
  const capture = currentSession.humanCapture || emptyCapture();
  const flags = analyzeText(
    currentSession.target,
    currentSession.goal,
    capture.observedProperties,
    capture.evaluation,
    capture.description,
    capture.testPerformed,
    capture.testResult,
    capture.environment,
    capture.measuredSignals
  );

  const material = materialAssessment(currentSession.domain, flags);
  const durability = durabilityAssessment(flags, capture);
  const frequency = frequencyAssessment(flags, capture);
  const variables = controlVariables(currentSession.domain, flags);
  const uncertainty = uncertaintyFlags(capture);
  const selfDiagnosis = capture.failureType || "Not specified";
  const detailedGuidance = detailedAssessmentGuidance(currentSession, capture, {
    material,
    durability,
    frequency,
    variables,
    risks: [
      `Self-diagnosis: ${selfDiagnosis}`,
      flags.mentionsHeat ? "Thermal feedback may change behavior or safety margin." : "No explicit thermal risk recorded.",
      capture.environment ? "Context is recorded; validate roadmap outside this context before templating." : "Context is missing; roadmap confidence is limited."
    ],
    uncertainty
  });

  return {
    material,
    durability,
    frequency,
    variables,
    risks: [
      `Self-diagnosis: ${selfDiagnosis}`,
      flags.mentionsHeat ? "Thermal feedback may change behavior or safety margin." : "No explicit thermal risk recorded.",
      capture.environment ? "Context is recorded; validate roadmap outside this context before templating." : "Context is missing; roadmap confidence is limited."
    ],
    uncertainty,
    detailedGuidance
  };
}

function detailedAssessmentGuidance(session, capture, assessment) {
  const variables = assessment.variables.slice(0, 6);
  return [
    "AI-style interpretation:",
    `The current target is ${session.target}. The human data should be treated as the authority. The assessment is not magic and not a lab measurement; it is a structured MAS hypothesis built from the user's capture.`,
    "",
    "What appears to matter most:",
    ...variables.map((variable, index) => `${index + 1}. ${variable}: isolate this variable and test it separately before combining it with other changes.`),
    "",
    "How to read the captured evidence:",
    `- Observed properties show the raw interface between body and target: ${capture.observedProperties || "not enough raw property data was recorded."}`,
    `- Evaluation shows the user's current model of the problem: ${capture.evaluation || "the evaluation is missing, so the model is incomplete."}`,
    `- Test result is the strongest evidence for the next roadmap: ${capture.testResult || "no test result was recorded, so the first roadmap must stay conservative."}`,
    `- Measured signals are the feedback channel: ${capture.measuredSignals || "no measured signals were recorded; use qualitative signals until better metrics exist."}`,
    "",
    "Immediate AI recommendation:",
    `Start with ${variables[0] || "one control variable"} as the first variable. Keep every other variable as constant as possible. Record what changes in output quality, effort, and sensory feedback. If improvement appears, repeat three times before trusting it. If improvement does not appear, switch to ${variables[1] || "a different control variable"} rather than pushing harder.`
  ].join("\n");
}

function materialAssessment(domain, flags) {
  if (domain === "social") return "Primary substrate is behavioral: tone, timing, attention, status pressure, and emotional feedback.";
  if (domain === "concept") return "Primary substrate is conceptual: definitions, assumptions, logical boundaries, and transfer conditions.";
  if (domain === "environment") return "Primary substrate is environmental: surfaces, constraints, timing, sensory load, and available paths.";
  if (flags.mentionsHardness) return "Likely hard or rigid structure. Prioritize force control, impact limits, and surface feedback.";
  if (flags.mentionsFlex) return "Likely flexible or compliant structure. Prioritize deformation, rebound, delay, and tolerance.";
  if (flags.mentionsFriction) return "Surface interaction appears important. Prioritize grip, drag, pressure, and contact angle.";
  return "Material/property class is under-specified. Treat structure as unknown until more human tests are recorded.";
}

function durabilityAssessment(flags, capture) {
  if (flags.mentionsHardness && /brittle|glass|crack|break/i.test(capture.observedProperties + capture.evaluation)) {
    return "Durability risk: hard but possibly brittle. Start with low-force tests and increase gradually.";
  }
  if (flags.mentionsFlex) return "Durability depends on repeated deformation. Watch for fatigue, rebound loss, and delayed response.";
  if (capture.failureType === "material") return "Material/property constraint is already suspected. Roadmap should adapt around limits instead of overpowering them.";
  return "Durability unknown. Use conservative first drills and record wear, deformation, heat, or loss of consistency.";
}

function frequencyAssessment(flags, capture) {
  if (flags.mentionsVibration) return "Vibration/frequency is a relevant signal. Track rhythm, sound, wobble, pulse rate, or oscillation before changing technique.";
  if (capture.measuredSignals) return "Measured signals exist. Use them as the timing baseline for drills and roadmap success criteria.";
  return "No direct frequency signal recorded. Use qualitative rhythm, latency, smoothness, and repeatability until instruments are available.";
}

function controlVariables(domain, flags) {
  const common = ["attention target", "repetition count", "error threshold"];
  if (domain === "social") return ["tone", "pace", "distance", "timing", "question framing", ...common];
  if (domain === "concept") return ["definition boundary", "example set", "counterexample", "abstraction level", ...common];
  if (domain === "environment") return ["path", "surface", "lighting", "noise", "timing window", ...common];
  const variables = ["pressure", "angle", "speed", "contact duration", "posture", ...common];
  if (flags.mentionsFriction) variables.unshift("grip/friction");
  if (flags.mentionsVibration) variables.unshift("rhythm/frequency");
  if (flags.mentionsHeat) variables.unshift("temperature exposure");
  return variables;
}

function uncertaintyFlags(capture) {
  const flags = [];
  if (!capture.observedProperties) flags.push("Observed properties missing.");
  if (!capture.testPerformed || !capture.testResult) flags.push("Initial test evidence incomplete.");
  if (!capture.measuredSignals) flags.push("No measured signals; roadmap uses qualitative indicators.");
  if (!capture.environment) flags.push("Context missing; transfer confidence is limited.");
  return flags.length ? flags : ["Capture is sufficient for a first roadmap; still validate through repeated tests."];
}

function renderAssessment() {
  const output = document.querySelector("#assessment-output");
  if (!currentSession?.aiAssessment) {
    output.innerHTML = `<div class="empty-state">Generate assessment after saving human capture. This is a local MAS-based assessment, not an external AI call.</div>`;
    return;
  }
  const assessment = currentSession.aiAssessment;
  output.innerHTML = `
    <dl class="assessment-list">
      <dt>Material / structure</dt><dd>${escapeHtml(assessment.material)}</dd>
      <dt>Durability</dt><dd>${escapeHtml(assessment.durability)}</dd>
      <dt>Vibration / frequency</dt><dd>${escapeHtml(assessment.frequency)}</dd>
      <dt>Control variables</dt><dd>${escapeHtml(assessment.variables.join(", "))}</dd>
      <dt>Risks</dt><dd>${escapeHtml(assessment.risks.join(" "))}</dd>
      <dt>Uncertainty flags</dt><dd>${escapeHtml(assessment.uncertainty.join(" "))}</dd>
      <dt>Detailed guidance</dt><dd>${escapeHtml(assessment.detailedGuidance || "Regenerate assessment for detailed guidance.")}</dd>
    </dl>
  `;
}

function assessmentText(assessment) {
  if (!assessment) return "No AI-style assessment generated yet.";
  return [
    `Material / structure: ${assessment.material}`,
    `Durability: ${assessment.durability}`,
    `Vibration / frequency: ${assessment.frequency}`,
    `Control variables: ${assessment.variables.join(", ")}`,
    `Risks: ${assessment.risks.join(" ")}`,
    `Uncertainty flags: ${assessment.uncertainty.join(" ")}`,
    "",
    assessment.detailedGuidance || "Detailed guidance not generated yet."
  ].join("\n");
}

function generateRoadmapText() {
  if (!currentSession) return "";
  const assessment = currentSession.aiAssessment || generateAssessment();
  const capture = currentSession.humanCapture || emptyCapture();
  const variables = assessment.variables.slice(0, 4).join(", ");
  const firstVariable = assessment.variables[0] || "attention target";
  const measured = capture.measuredSignals || "qualitative smoothness, error rate, effort, and repeatability";
  const context = capture.environment || "the same context as the first human test";
  const invariant = inferTemplateCandidate(currentSession, assessment);

  return [
    `MAS Roadmap: ${currentSession.target}`,
    `Mode: Mahoraga metaphor + Manufacturing Adaptive Programming`,
    `Goal: ${currentSession.goal || "Improve reliable use through human capture, assessment, and refinement."}`,
    "",
    "1. Baseline calibration",
    `Set up ${context}. Keep the first drill conservative and focus attention on ${firstVariable}.`,
    `Before starting, write down the baseline result using this signal: ${measured}. Do not attempt to improve yet. The first pass is only to establish what normal failure looks like.`,
    "Do three baseline repetitions. After each one, record output quality, body tension, speed, and whether the original failure appeared.",
    "",
    "2. First drill",
    `Run 5 slow repetitions using only one deliberate change. Primary variable set: ${variables}.`,
    `Keep the first change focused on ${firstVariable}. Do not combine multiple fixes. MAS needs a clean cause-effect signal.`,
    "After each repetition, write one sentence: what changed, what got worse, what felt easier, and what sensory signal became clearer.",
    "",
    "3. Measurement target",
    `Track ${measured}. Mark the smallest change that improves consistency without increasing effort.`,
    "Use a simple score after every repetition: output quality 1-10, effort 1-10, stability 1-10, and discomfort 0-10. Improvement only counts if quality rises without discomfort rising.",
    "",
    "4. Property-aware adjustment",
    `${assessment.durability} ${assessment.frequency}`,
    `If the target responds like a rigid structure, reduce force and increase angle control. If it responds like a flexible structure, slow down and wait for rebound/delay. If rhythm or vibration appears, make timing the main variable instead of brute force.`,
    "",
    "5. Constraint check",
    `Self-diagnosed problem: ${failureLabel(capture.failureType) || "Not specified yet — observe what keeps going wrong."} If the same miss repeats twice, change your approach instead of forcing more effort.`,
    `Quick rule: unclear sensing → slow down and look closer. Wrong idea → question your assumption. Body won't cooperate → simplify the movement. Works here but not there → compare the two situations. The thing has limits → work around them instead of through them.`,
    "",
    "6. Refinement loop",
    "Repeat: capture result -> adjust one variable -> measure again -> keep only changes that reduce error or cognitive load.",
    "Each loop should take 2-5 minutes. If the loop becomes vague, stop and rewrite the next test as a single observable action.",
    "",
    "7. Transfer test",
    "Repeat the drill in one changed context. If performance collapses, label it as context-specific instead of saving it as universal.",
    "Change only one context variable: tool, surface, posture, speed, lighting, audience, paper, time pressure, or example type. Transfer success means the method still works at roughly 80% of the original quality.",
    "",
    "8. Template candidate",
    invariant,
    "Do not mark this as learned yet. It is only a candidate until it survives repeated measurement and at least one transfer test.",
    "",
    "9. Embodiment validation",
    "Run the task while attention is partially occupied. If performance drops sharply, the skill is still in conscious-control phase. Continue slow calibration until the body can keep the pattern with less supervision.",
    "Embodiment target: the user can intentionally vary the result, maintain relaxed execution, and recover from small errors without stopping the whole task."
  ].join("\n");
}

function inferTemplateCandidate(session, assessment) {
  const capture = session.humanCapture || emptyCapture();
  const coreSignal = capture.measuredSignals || capture.testResult || capture.evaluation || "the clearest measured signal";
  return `When adapting to ${session.target}, begin with ${assessment.variables[0] || "the strongest control variable"} and verify against ${coreSignal}.`;
}

function renderRoadmap() {
  document.querySelector("#roadmap-editor").value = currentSession?.roadmap || "";
  renderCompleteOutput();
}

function humanCaptureText(capture) {
  if (!capture) return "No human operational capture saved yet.";
  return [
    `Observed properties: ${capture.observedProperties || "Not recorded"}`,
    `Evaluation: ${capture.evaluation || "Not recorded"}`,
    `Description: ${capture.description || "Not recorded"}`,
    `Test performed: ${capture.testPerformed || "Not recorded"}`,
    `Test result: ${capture.testResult || "Not recorded"}`,
    `Environment/context: ${capture.environment || "Not recorded"}`,
    `Measured signals: ${capture.measuredSignals || "Not recorded"}`,
    `Failure or constraint type: ${failureLabel(capture.failureType)}`
  ].join("\n");
}

function baselineText() {
  const baseline = normalizeBaseline(currentSession?.baseline);
  return [
    `Skill level self-assessment: ${baseline.skillLevel ? `${baseline.skillLevel}/10` : "Not recorded"}`,
    `Historical patterns: ${baseline.historicalPatterns || "Not recorded"}`,
    `Previous adaptation attempts: ${baseline.previousAttempts || "Not recorded"}`
  ].join("\n");
}

function embodimentValidationText() {
  return [
    "Test for competent unconscious:",
    "- Perform the task while lightly distracted, such as listening to audio or holding a simple conversation.",
    "- If performance holds, embodiment is progressing.",
    "- If performance collapses, the skill is still in cognitive-control phase.",
    "",
    "Body check:",
    "- Close the eyes briefly before/after execution and scan for unnecessary tension.",
    "- Ideal direction: the action happens with lower effort, lower hesitation, and less conscious pressure.",
    "",
    "Signs of embodied state:",
    "- No constant conscious thought about the main control variable.",
    "- Body remains relaxed through longer practice.",
    "- User can intentionally vary the result on command.",
    "- Results stay consistent across at least two contexts."
  ].join("\n");
}

function failureMapText() {
  const capture = currentSession?.humanCapture || emptyCapture();
  const flags = analyzeText(
    currentSession?.target || "",
    currentSession?.goal || "",
    capture.observedProperties,
    capture.evaluation,
    capture.description,
    capture.testPerformed,
    capture.testResult,
    capture.environment,
    capture.measuredSignals
  );
  const known = [
    `Your description of the problem: ${failureLabel(capture.failureType)}`,
    `Primary symptom evidence: ${capture.testResult || capture.evaluation || capture.measuredSignals || "Not recorded"}`,
    `Likely fix direction: ${failureFix(capture.failureType)}`
  ];
  return [
    "What you've noticed so far:",
    ...known.map((item, index) => `${index + 1}. ${item}`),
    "",
    "Things to watch for next:",
    "1. Does it work in one setup but fail in another? That's a context problem.",
    "2. Does speed make it worse? Try slower first, then build up.",
    "3. Does it only work with one specific tool or person? That's a dependency.",
    "4. Does trying hard make it worse? Relax and reduce effort.",
    "5. Does quality drop after a while? That's fatigue — take breaks."
  ].join("\n");
}

function failureFix(type) {
  if (!type) return "Describe what's going wrong, then try one small change at a time.";
  return "Keep observing and testing. Try changing one thing at a time to see what helps.";
}

function successCriteriaText() {
  const domain = currentSession?.domain || "object";
  if (domain === "concept") {
    return [
      "Primary metric: Explain the concept clearly without notes and handle at least three examples.",
      "Secondary metric: Correctly answer counterexamples or edge cases without changing the definition randomly.",
      "Body/cognitive cost: Can reason through it without high mental strain or confusion spiral.",
      "Transfer test: Apply the concept to two different domains with at least 80% correctness.",
      "Embodiment marker: The concept becomes available during real work, not only during review."
    ].join("\n");
  }
  if (domain === "social") {
    return [
      "Primary metric: Tone, timing, and response quality remain stable during the interaction.",
      "Secondary metric: Recovery from misunderstanding happens within one or two turns.",
      "Body cost: Emotional tension returns to baseline quickly after the exchange.",
      "Transfer test: Skill works with at least two different people or group contexts.",
      "Embodiment marker: The user can stay attentive without over-scripting every sentence."
    ].join("\n");
  }
  if (domain === "environment") {
    return [
      "Primary metric: Navigation or operation error decreases in the environment.",
      "Secondary metric: Reaction time improves without rushing.",
      "Body cost: Fatigue, hesitation, or sensory overload decreases.",
      "Transfer test: Performance holds after changing one environmental variable.",
      "Embodiment marker: The user responds to the environment fluidly without constant conscious mapping."
    ].join("\n");
  }
  return [
    "Primary metric: Output quality stays consistent across repeated trials.",
    "Secondary metric: Error rate, wobble, breakage, or unwanted variation decreases.",
    "Body cost: Fatigue onset is delayed and discomfort stays low.",
    "Cognitive load: User can maintain performance while attention is partially shared.",
    "Transfer test: Performance remains at least 80% stable across two changed contexts.",
    "Embodiment marker: The intended variation can be produced on command with low effort."
  ].join("\n");
}

function aaiRoleText() {
  return [
    "What AAI should do:",
    "1. Analyze Step 1 data for patterns the user may have missed.",
    "2. Cross-reference Step 2 assessment with relevant domain knowledge.",
    "3. Generate specific drill protocols for each roadmap step.",
    "4. Adjust difficulty based on the user's reported results.",
    "5. Detect repeated failure loops and suggest a pivot.",
    "6. Track progress across sessions when memory/context is available.",
    "7. Validate template candidates before calling them learned.",
    "",
    "What AAI should not do:",
    "- Do not give generic advice that ignores sensory data.",
    "- Do not skip baseline mastery for advanced technique.",
    "- Do not override direct user evidence with theory.",
    "- Do not encourage pushing through pain or fatigue signals.",
    "",
    "Interaction style:",
    "- Ask clarifying questions before major changes.",
    "- Request specific measurements when useful.",
    "- Reinforce small improvements.",
    "- Call out regression or overconfidence directly.",
    "- Focus on embodiment, not just surface performance."
  ].join("\n");
}

function sessionLogText() {
  return [
    "Date:",
    "Exercises completed:",
    "Results observed:",
    "Failures encountered:",
    "Adjustments made for next session:",
    "Template status: [ ] Not started [ ] In development [ ] Candidate [ ] Validated [ ] Embodied"
  ].join("\n");
}

function completeOutputText() {
  if (!currentSession) return "";
  return [
    `# MAS COMPLETE PACKET v2.0`,
    "",
    `## METADATA`,
    `Target: ${currentSession.target}`,
    `Domain: ${domainLabel(currentSession.domain)}`,
    `Goal: ${currentSession.goal || "Not recorded"}`,
    `Mode: Mahoraga Adapt System metaphor + Manufacturing Adaptive Programming workflow`,
    `Session: 1 of estimated 5-10 sessions needed for full adaptation`,
    `Date: ${new Date().toLocaleString()}`,
    "",
    `## SECTION 0: PRE-ADAPTATION BASELINE`,
    baselineText(),
    "",
    `## STEP 1: HUMAN OPERATIONAL CAPTURE`,
    humanCaptureText(currentSession.humanCapture),
    "",
    `## STEP 2: AI PROPERTY ASSESSMENT`,
    assessmentText(currentSession.aiAssessment),
    "",
    `## STEP 3: ADAPTIVE ROADMAP`,
    currentSession.roadmap || "No roadmap generated yet.",
    "",
    `### STEP 9: EMBODIMENT VALIDATION`,
    embodimentValidationText(),
    "",
    `## SECTION 4: FAILURE MAP`,
    failureMapText(),
    "",
    `## SECTION 5: SUCCESS CRITERIA (SPECIFIC)`,
    successCriteriaText(),
    "",
    `## SECTION 6: AAI OPERATIONAL ROLE`,
    aaiRoleText(),
    "",
    `## SESSION LOG`,
    sessionLogText()
  ].join("\n");
}

function renderCompleteOutput() {
  // complete-output display was removed; function kept for compatibility
}

function renderTemplates() {
  const list = document.querySelector("#template-list");
  if (templates.length === 0) {
    list.innerHTML = `<div class="empty-state">Template memory is empty. Save an edited roadmap after assessment.</div>`;
    return;
  }
  list.innerHTML = templates
    .slice()
    .reverse()
    .map((template) => `
      <article class="template-card roadmap-template">
        <h3>${escapeHtml(template.target)}</h3>
        <p><strong>Domain:</strong> ${escapeHtml(domainLabel(template.domain))}</p>
        <p><strong>Template candidate:</strong> ${escapeHtml(template.invariant)}</p>
        <p><strong>Assessment:</strong> ${escapeHtml(template.assessmentSummary)}</p>
        <p><strong>Saved:</strong> ${escapeHtml(new Date(template.createdAt).toLocaleString())}</p>
        <pre>${escapeHtml(template.roadmap)}</pre>
      </article>
    `)
    .join("");
}

function renderSources() {
  document.querySelector("#source-list").innerHTML = sources
    .map((source) => `
      <article class="source-card">
        <h3>${escapeHtml(source.title)}</h3>
        <p>${escapeHtml(source.role)}</p>
        <span class="tag">${escapeHtml(source.path)}</span>
      </article>
    `)
    .join("");
}

function renderDeepAnalysis(deepData) {
  const output = document.querySelector("#deep-analysis-output");
  if (!deepData) {
    output.innerHTML = `<div class="empty-state">Save human capture and run Deep Analysis to see 9 thinking perspectives and their synthesis.</div>`;
    return;
  }

  const { perspectives, synthesis } = deepData;

  const cardsHtml = perspectives.map((p, i) => `
    <div class="perspective-card ${p.error ? "error" : ""}" data-perspective="${p.id}">
      <div class="perspective-card-header" role="button" tabindex="0" aria-expanded="false">
        <span class="perspective-icon">${p.icon}</span>
        <span class="perspective-name">${escapeHtml(p.label)}<br><span style="color:var(--muted);font-weight:400;font-size:11px">${escapeHtml(p.labelVi)}</span></span>
        <span class="perspective-toggle">▼</span>
      </div>
      <div class="perspective-body">${escapeHtml(p.analysis)}</div>
    </div>
  `).join("");

  const synthesisHtml = synthesis ? `
    <div class="synthesis-section">
      <div class="synthesis-label">✦ 10th Synthesis — Optimal MAS Path</div>
      <div class="synthesis-content">${escapeHtml(synthesis)}</div>
    </div>
  ` : "";

  output.innerHTML = `
    <div class="perspective-grid">${cardsHtml}</div>
    ${synthesisHtml}
  `;

  output.querySelectorAll(".perspective-card-header").forEach((header) => {
    header.addEventListener("click", () => {
      const card = header.closest(".perspective-card");
      card.classList.toggle("open");
      header.setAttribute("aria-expanded", card.classList.contains("open"));
    });
  });
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.querySelectorAll("[data-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    const firstVisible = visibleNodes()[0];
    if (firstVisible && !visibleNodes().some((node) => node.id === activeNodeId)) {
      activeNodeId = firstVisible.id;
    }
    setActiveFilterButton();
    selectNode(activeNodeId);
  });
});

document.querySelector("#open-background").addEventListener("click", () => {
  document.querySelector("#background-modal").hidden = false;
});

document.querySelector("#close-background").addEventListener("click", () => {
  document.querySelector("#background-modal").hidden = true;
});

document.querySelector("#background-modal").addEventListener("click", (event) => {
  if (event.target.id === "background-modal") {
    event.currentTarget.hidden = true;
  }
});

function saveSessionTarget() {
  const target = formValue("#target-name");
  const domain = document.querySelector("#target-domain").value;
  const goal = formValue("#target-goal");
  const baseline = {
    skillLevel: formValue("#skill-level"),
    historicalPatterns: formValue("#historical-patterns"),
    previousAttempts: formValue("#previous-attempts")
  };
  if (!target) return;
  if (!currentSession) {
    currentSession = createSession(target, domain, goal);
    currentSession.baseline = baseline;
    if (apiAvailable) {
      apiPost("/api/sessions", { target, domain, goal, baseline }).then((r) => {
        if (r.ok) { currentSession.serverId = r.data.id; currentSession.id = r.data.id; }
      });
    }
  } else {
    currentSession.target = target;
    currentSession.domain = domain;
    currentSession.goal = goal;
    currentSession.baseline = baseline;
    const sId = sessionApiId();
    if (apiAvailable && sId) apiPut(`/api/sessions/${sId}`, { target, domain, goal, baseline });
  }
  saveSession();
  renderSession();
}

const EXAMPLES = {
  pencil: {
    target: "pencil pressure control",
    domain: "tool",
    goal: "Write smoothly without gripping too hard, so my hand doesn't cramp after 10 minutes",
    baseline: { skillLevel: "3", historicalPatterns: "When I focus on precision, my grip tightens automatically", previousAttempts: "Tried thicker grip, softer pencil, relaxing hand between words" },
    capture: {
      observedProperties: "Hexagonal wood body, hard graphite tip (#2), smooth paper surface, slight resistance when writing",
      evaluation: "Grip feels unstable — I compensate by squeezing harder. Writing is legible but inconsistent thickness",
      description: "Standard wooden pencil on copy paper. The harder I concentrate on neatness, the tighter my fingers get",
      testPerformed: "Wrote a paragraph at normal speed, then a paragraph at half speed focusing on loose grip",
      testResult: "Half speed gave more consistent line thickness but my thumb joint still ached. Normal speed produced shakier lines",
      environment: "Desk with good lighting, quiet room, no time pressure",
      measuredSignals: "Hand cramp onset at ~8 min. Line wobble increases after 5 min. Grip pressure feels 2x normal",
      failureType: "My body tenses up and grip gets too tight"
    }
  },
  "public-speaking": {
    target: "public speaking nerves",
    domain: "social",
    goal: "Speak clearly and stay calm when presenting to a group of 10+ people",
    baseline: { skillLevel: "2", historicalPatterns: "Voice shakes when I start, I rush through slides, forget what I planned to say", previousAttempts: "Practiced in mirror, deep breathing before, memorized script" },
    capture: {
      observedProperties: "Dry mouth, racing heart, hands tremble slightly, voice sounds higher than normal",
      evaluation: "The first 2 minutes are the worst. After that I settle somewhat but still rush",
      description: "Presenting to colleagues in a meeting room. Everyone is friendly but I still feel judged",
      testPerformed: "Presented a 5-minute update to 3 coworkers instead of the full team",
      testResult: "Still felt nervous but less than usual. Forgot one point but recovered. Voice shook only at the very start",
      environment: "Small meeting room, familiar faces, afternoon, sitting down",
      measuredSignals: "Heart rate spikes at start (estimated 100+ bpm). Speaking pace too fast — finish 30% early. Hands visible shaking on paper",
      failureType: "I can't sense my own anxiety until I'm already speaking"
    }
  }
};

document.querySelectorAll(".example-chip").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const key = btn.dataset.example;
    const ex = EXAMPLES[key];
    if (!ex) return;
    currentSession = createSession(ex.target, ex.domain, ex.goal);
    currentSession.baseline = ex.baseline;
    currentSession.humanCapture = ex.capture;
    if (apiAvailable) {
      const result = await apiPost("/api/sessions", { target: ex.target, domain: ex.domain, goal: ex.goal, baseline: ex.baseline, humanCapture: ex.capture });
      if (result.ok) {
        currentSession.serverId = result.data.id;
        currentSession.id = result.data.id;
      }
    }
    saveSession();
    renderSession();
  });
});

document.querySelector("#session-form").addEventListener("input", () => {
  debounceSave("session", saveSessionTarget, 400);
});
document.querySelector("#session-form").addEventListener("change", () => {
  debounceSave("session", saveSessionTarget, 100);
});

function saveCapture() {
  if (!currentSession) return;
  const capture = captureFromForm();
  const hasData = capture.observedProperties || capture.description || capture.testResult || capture.evaluation || capture.testPerformed || capture.environment || capture.measuredSignals;
  currentSession.humanCapture = hasData ? capture : null;
  currentSession.aiAssessment = null;
  currentSession.roadmap = "";
  saveSession();
  const sId = sessionApiId();
  if (apiAvailable && sId && hasData) apiPut(`/api/sessions/${sId}`, { humanCapture: capture });
  renderSession();
}

document.querySelector("#capture-form").addEventListener("input", () => {
  debounceSave("capture", saveCapture, 400);
});
document.querySelector("#capture-form").addEventListener("change", () => {
  debounceSave("capture", saveCapture, 100);
});

document.querySelector("#generate-full").addEventListener("click", async () => {
  if (!currentSession) {
    alert("Define a target first.");
    return;
  }
  if (captureCompleteness(currentSession.humanCapture) === 0) {
    alert("Add at least some capture data before generating.");
    return;
  }

  let aiOk = apiAvailable && rateLimitInfo.remaining > 0;
  const sId = sessionApiId();
  if (aiOk && !sId) { aiOk = false; }

  if (aiOk) {
    showLoading("AI analyzing capture & building roadmap...");
    const assessResult = await apiPost(`/api/sessions/${sId}/assessment`, {});
    if (assessResult.ok) {
      currentSession.aiAssessment = assessResult.data.assessment;
      if (assessResult.data.rateLimit?.remaining !== undefined) {
        rateLimitInfo.remaining = assessResult.data.rateLimit.remaining;
        updateRateLimitUI();
      }
      const roadmapResult = await apiPost(`/api/sessions/${sId}/roadmap`, {});
      if (roadmapResult.ok) {
        currentSession.roadmap = roadmapResult.data.roadmap;
        if (roadmapResult.data.rateLimit?.remaining !== undefined) {
          rateLimitInfo.remaining = roadmapResult.data.rateLimit.remaining;
          updateRateLimitUI();
        }
      } else if (roadmapResult.status === 429) {
        currentSession.roadmap = generateRoadmapText();
      } else {
        currentSession.roadmap = generateRoadmapText();
      }
    } else if (assessResult.status === 429) {
      currentSession.aiAssessment = generateAssessment();
      currentSession.roadmap = generateRoadmapText();
    } else {
      aiOk = false;
    }
    hideLoading();
  }

  if (!aiOk) {
    currentSession.aiAssessment = generateAssessment();
    currentSession.roadmap = generateRoadmapText();
  }

  saveSession();
  renderAssessment();
  renderRoadmap();
  renderCompleteOutput();
});

document.querySelector("#roadmap-editor").addEventListener("input", () => {
  if (!currentSession) return;
  currentSession.roadmap = document.querySelector("#roadmap-editor").value;
  saveSession();
  renderCompleteOutput();
  updateStepProgress();
});

document.querySelector("#run-deep-analysis").addEventListener("click", async () => {
  if (!currentSession) {
    alert("Start a session first.");
    return;
  }
  if (captureCompleteness(currentSession.humanCapture) === 0) {
    alert("Save human operational capture before running deep analysis.");
    return;
  }
  if (!geminiAvailable) {
    alert("AI is not configured. Add a valid GEMINI_API_KEY to server/.env");
    return;
  }

  const sId = sessionApiId();
  if (!sId) { alert("Session not synced to server."); return; }
  showLoading("9 perspectives spinning in parallel...");
  const result = await apiPost(`/api/sessions/${sId}/deep-analysis`, {});
  hideLoading();

  if (result.ok) {
    currentSession.deepAnalysis = { perspectives: result.data.perspectives, synthesis: result.data.synthesis };
    if (result.data.rateLimit?.remaining !== undefined) {
      rateLimitInfo.remaining = result.data.rateLimit.remaining;
      updateRateLimitUI();
    }
    saveSession();
    renderDeepAnalysis(currentSession.deepAnalysis);
  } else {
    if (result.status === 429) {
      alert(result.data.error || "Rate limit reached.");
    } else if (result.status === 503) {
      geminiAvailable = false;
      updateDeepBadge();
      alert("AI not configured. Add a valid GEMINI_API_KEY to server/.env");
    } else {
      alert(result.data.error || "Deep analysis failed. Check server logs.");
    }
  }
});

document.querySelector("#copy-complete-output").addEventListener("click", async () => {
  const value = completeOutputText();
  if (!value) {
    alert("Start a session first.");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    alert("Complete packet copied to clipboard.");
  } catch {
    alert("Could not copy automatically. Select and copy from the plan text area.");
  }
});

document.querySelector("#save-roadmap-template").addEventListener("click", () => {
  if (!currentSession) {
    alert("Start a session first.");
    return;
  }
  const roadmap = document.querySelector("#roadmap-editor").value.trim();
  if (!roadmap) {
    alert("Generate or write a roadmap before saving a template.");
    return;
  }
  currentSession.roadmap = roadmap;
  saveSession();
  const assessment = currentSession.aiAssessment || generateAssessment();
  const packet = completeOutputText();
  const template = {
    id: `${Date.now()}-${currentSession.target.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    target: currentSession.target,
    domain: currentSession.domain,
    invariant: inferTemplateCandidate(currentSession, assessment),
    assessmentSummary: assessment.material,
    roadmap: packet,
    createdAt: new Date().toISOString()
  };
  templates.push(template);
  writeJson(STORAGE_KEYS.templates, templates);
  renderTemplates();
  setView("templates");
  alert("Roadmap template saved to Template Memory.");
});

document.querySelector("#clear-session").addEventListener("click", () => {
  if (!currentSession) return;
  if (!confirm("Clear the current session from this browser?")) return;
  currentSession = null;
  localStorage.removeItem(STORAGE_KEYS.session);
  localStorage.removeItem(STORAGE_KEYS.legacySession);
  renderSession();
});

document.querySelector("#clear-templates").addEventListener("click", () => {
  if (templates.length === 0) return;
  if (!confirm("Clear all saved templates from this browser?")) return;
  templates = [];
  writeJson(STORAGE_KEYS.templates, templates);
  localStorage.removeItem(STORAGE_KEYS.legacyTemplates);
  renderTemplates();
});

async function initApi() {
  const health = await checkApiHealth();
  if (health) {
    await pollRateLimit();
    updateRateLimitUI();
  } else {
    updateRateLimitUI();
  }
}

initApi();
setInterval(async () => {
  if (apiAvailable) await pollRateLimit();
  else await checkApiHealth().then(() => { if (apiAvailable) pollRateLimit(); });
}, 15000);

selectNode(activeNodeId);
renderSession();
renderTemplates();
renderSources();
