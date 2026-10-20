// ============================================================
// Knowledge graph data + rendering
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

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
