const STORAGE_KEYS = {
  session: "mas.currentSession.v2",
  legacySession: "mas.currentSession.v1",
  templates: "mas.templates.v2",
  legacyTemplates: "mas.templates.v1"
};

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
    failureType: "perception"
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
  const status = document.querySelector("#capture-status");
  if (!currentSession) {
    summary.innerHTML = `<div class="empty-state">No active session. Define a target before capturing human operational data.</div>`;
    status.textContent = "No capture saved";
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
  status.textContent = `${captureScore}/7 capture fields saved`;
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
  document.querySelector("#failure-type").value = capture.failureType || "perception";
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
  return {
    perception: "Perception error",
    model: "Model error",
    execution: "Execution error",
    context: "Context shift error",
    material: "Material/property constraint"
  }[value] || "Unclassified";
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
  const detailedGuidance = detailedAssessmentGuidance(currentSession, capture, {
    material,
    durability,
    frequency,
    variables,
    risks: [
      failureLabel(capture.failureType),
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
      failureLabel(capture.failureType),
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
    `Current failure class: ${failureLabel(capture.failureType)}. If the same miss repeats twice, change the roadmap variable instead of forcing more effort.`,
    `Use this rule: perception error means gather better sensory data; model error means change the explanation; execution error means simplify the body action; context error means compare environments; material/property constraint means adapt around the limit.`,
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
    `Current selected failure: ${failureLabel(capture.failureType)}`,
    `Primary symptom evidence: ${capture.testResult || capture.evaluation || capture.measuredSignals || "Not recorded"}`,
    `Likely fix direction: ${failureFix(capture.failureType)}`
  ];
  const anticipated = [
    "Context transfer failure: works in the original setup but degrades in a new context.",
    "Speed-pressure coupling: faster execution automatically increases force or error.",
    "Tool dependency: the template only works with the original object/tool/setup.",
    "Over-control: conscious effort increases tension and reduces fluidity.",
    "Fatigue degradation: quality drops after repeated practice without recovery."
  ];
  if (flags.mentionsVibration) anticipated.unshift("Rhythm/frequency drift: vibration, sound, or timing changes under speed or fatigue.");
  if (flags.mentionsFriction) anticipated.unshift("Grip/friction mismatch: contact quality changes when surface, angle, or pressure changes.");
  return [
    "Known error modes:",
    ...known.map((item, index) => `${index + 1}. ${item}`),
    "",
    "Anticipated future failures to watch:",
    ...anticipated.map((item, index) => `${index + 1}. ${item}`)
  ].join("\n");
}

function failureFix(type) {
  return {
    perception: "Improve sensory capture before changing technique.",
    model: "Revise the causal model and test one variable at a time.",
    execution: "Reduce difficulty and train the body expression of the model.",
    context: "Identify which environmental condition changed the result.",
    material: "Adapt around the physical/property limit instead of forcing through it."
  }[type] || "Return to capture and isolate the first unstable variable.";
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
  const output = document.querySelector("#complete-output");
  if (!output) return;
  output.value = completeOutputText();
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

document.querySelector("#session-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const target = formValue("#target-name");
  const domain = document.querySelector("#target-domain").value;
  const goal = formValue("#target-goal");
  const baseline = {
    skillLevel: formValue("#skill-level"),
    historicalPatterns: formValue("#historical-patterns"),
    previousAttempts: formValue("#previous-attempts")
  };
  if (!target) {
    alert("Add a target before starting a session.");
    return;
  }
  if (!currentSession) {
    currentSession = createSession(target, domain, goal);
  } else {
    currentSession.target = target;
    currentSession.domain = domain;
    currentSession.goal = goal;
    currentSession.baseline = baseline;
  }
  currentSession.baseline = baseline;
  saveSession();
  renderSession();
});

document.querySelector("#capture-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!currentSession) {
    alert("Start a session before saving human capture.");
    return;
  }
  const capture = captureFromForm();
  if (!capture.observedProperties && !capture.description && !capture.testResult) {
    alert("Add at least observed properties, a description, or a test result before saving capture.");
    return;
  }
  currentSession.humanCapture = capture;
  currentSession.aiAssessment = null;
  currentSession.roadmap = "";
  saveSession();
  renderSession();
});

document.querySelector("#generate-assessment").addEventListener("click", () => {
  if (!currentSession) {
    alert("Start a session first.");
    return;
  }
  if (captureCompleteness(currentSession.humanCapture) === 0) {
    alert("Save human operational capture before generating assessment.");
    return;
  }
  currentSession.aiAssessment = generateAssessment();
  saveSession();
  renderAssessment();
  renderCompleteOutput();
});

document.querySelector("#generate-roadmap").addEventListener("click", () => {
  if (!currentSession) {
    alert("Start a session first.");
    return;
  }
  if (captureCompleteness(currentSession.humanCapture) === 0) {
    alert("Save human operational capture before generating a roadmap.");
    return;
  }
  currentSession.aiAssessment = currentSession.aiAssessment || generateAssessment();
  currentSession.roadmap = generateRoadmapText();
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
});

document.querySelector("#copy-complete-output").addEventListener("click", async () => {
  const value = document.querySelector("#complete-output").value.trim();
  if (!value) {
    alert("Generate or save session content before copying.");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    alert("Complete MAS packet copied.");
  } catch {
    const output = document.querySelector("#complete-output");
    output.focus();
    output.select();
    alert("Clipboard permission was unavailable. The packet is selected so you can copy it manually.");
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

selectNode(activeNodeId);
renderSession();
renderTemplates();
renderSources();
