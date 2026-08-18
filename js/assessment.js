// ============================================================
// Local assessment + roadmap + complete-packet generation
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

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
  const keyVariable = (assessment.variables || [])[0] || "n/a";
  output.innerHTML = `
    <details class="assessment-details">
      <summary>
        <span class="assessment-summary-line">Assessment: ${escapeHtml(assessment.material || "under-specified")} · First variable to isolate: <strong>${escapeHtml(keyVariable)}</strong></span>
        <span class="assessment-toggle">Details</span>
      </summary>
      <dl class="assessment-list">
        <dt>Material / structure</dt><dd>${escapeHtml(assessment.material)}</dd>
        <dt>Durability</dt><dd>${escapeHtml(assessment.durability)}</dd>
        <dt>Vibration / frequency</dt><dd>${escapeHtml(assessment.frequency)}</dd>
        <dt>Control variables</dt><dd>${escapeHtml(assessment.variables.join(", "))}</dd>
        <dt>Risks</dt><dd>${escapeHtml(assessment.risks.join(" "))}</dd>
        <dt>Uncertainty flags</dt><dd>${escapeHtml(assessment.uncertainty.join(" "))}</dd>
        <dt>Detailed guidance</dt><dd>${escapeHtml(assessment.detailedGuidance || "Regenerate assessment for detailed guidance.")}</dd>
      </dl>
    </details>
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
  const adaptState = computeAdaptation(currentSession.target);
  const adaptPhase = PHASE_META[adaptState.phase];
  const adaptTrend = TREND_META[adaptState.trend];
  const adaptNext = nextStepFor(adaptState, assessment.variables);

  return [
    `[ADAPTIVE STATE] ${adaptPhase.icon} ${adaptPhase.label} — ${adaptTrend.icon} ${adaptTrend.label} (spin ${adaptState.spinCount})`,
    `NEXT SPIN: ${adaptNext}`,
    "",
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
