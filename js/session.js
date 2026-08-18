// ============================================================
// Session state, capture forms, session rendering
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

let currentSession = normalizeSession(readJson(STORAGE_KEYS.session, null) || readJson(STORAGE_KEYS.legacySession, null));

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

function saveSession() {
  if (currentSession) writeJson(STORAGE_KEYS.session, currentSession);
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
    renderDeepAnalysis(null);
    renderAdaptationPanel();
    updateWizard();
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
  renderAdaptationPanel();
  updateWizard();
  const scoreEl = document.querySelector("#capture-score");
  if (scoreEl) scoreEl.textContent = `${captureScore}/7 capture fields filled`;
}

// ------------------------------------------------------------
// Wizard: 3 core steps + 1 advanced step. Steps unlock as the
// user provides data; only one step is visible at a time so the
// interface never overwhelms.
// ------------------------------------------------------------
let activeWizardStep = 1;

function wizardStepEnabled(step) {
  if (step === 1) return true;
  if (step === 4) return true; // advanced deep dive, always reachable
  if (step === 2) return !!currentSession && captureCompleteness(currentSession.humanCapture) > 0;
  if (step === 3) return !!currentSession && !!(currentSession.aiAssessment || currentSession.roadmap);
  return false;
}

function updateWizard() {
  const dots = document.querySelectorAll(".step-dot");
  if (!dots.length) return;

  // Never leave the user standing on a step that just became locked
  // (e.g. capture edit invalidated the roadmap). Fall back to the
  // highest still-unlocked step.
  if (!wizardStepEnabled(activeWizardStep)) {
    for (let s = 4; s >= 1; s--) {
      if (wizardStepEnabled(s)) {
        activeWizardStep = s;
        break;
      }
    }
  }

  dots.forEach((d) => {
    const step = Number(d.dataset.step);
    const enabled = wizardStepEnabled(step);
    d.disabled = !enabled;
    d.classList.toggle("active", step === activeWizardStep);
    d.classList.toggle("done", step < activeWizardStep && enabled);
  });
  document.querySelectorAll(".wizard-step").forEach((section) => {
    const on = Number(section.dataset.step) === activeWizardStep;
    section.classList.toggle("active", on);
  });
  // Mirror lock state on Next buttons so users get visual feedback.
  document.querySelectorAll("[data-next-step]").forEach((btn) => {
    btn.disabled = !wizardStepEnabled(Number(btn.dataset.nextStep));
  });
}

function goToWizardStep(step) {
  if (!wizardStepEnabled(step)) return;
  activeWizardStep = step;
  updateWizard();
  const progress = document.querySelector("#step-progress");
  if (progress) progress.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
  const c = capture || emptyCapture();
  return [
    c.observedProperties,
    c.evaluation,
    c.description,
    c.testPerformed,
    c.testResult,
    c.environment,
    c.measuredSignals
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

// Fingerprint of the capture data. The generated plan is only invalidated
// when this actually changes, so unrelated edits never wipe a good roadmap.
function captureHash(capture) {
  const c = capture || emptyCapture();
  return JSON.stringify([
    c.observedProperties, c.evaluation, c.description,
    c.testPerformed, c.testResult, c.environment,
    c.measuredSignals, c.failureType
  ]);
}
