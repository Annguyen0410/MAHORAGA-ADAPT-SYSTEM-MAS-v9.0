// ============================================================
// Event wiring, examples, init
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

// Wizard navigation: step dots + next/back buttons.
document.querySelectorAll(".step-dot").forEach((dot) => {
  dot.addEventListener("click", () => goToWizardStep(Number(dot.dataset.step)));
});
document.querySelectorAll("[data-next-step]").forEach((btn) => {
  btn.addEventListener("click", () => goToWizardStep(Number(btn.dataset.nextStep)));
});
document.querySelectorAll("[data-prev-step]").forEach((btn) => {
  btn.addEventListener("click", () => goToWizardStep(Number(btn.dataset.prevStep)));
});

// Check-in form is static HTML; wire it once (never rebuilt).
document.querySelector("#log-checkin").addEventListener("click", logCheckIn);
document.querySelector("#checkin-form").addEventListener("submit", (e) => e.preventDefault());

// Data backup: export downloads JSON; import replaces local state.
document.querySelector("#export-data").addEventListener("click", exportData);
document.querySelector("#import-data").addEventListener("click", () => {
  document.querySelector("#import-file").click();
});
document.querySelector("#import-file").addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  try {
    if (!confirm("Importing will replace the current session, templates and history in this browser. Continue?")) {
      e.target.value = "";
      return;
    }
    const result = await importData(file);
    alert(`Imported: ${result.session ? "session, " : ""}${result.templates} templates, ${result.history} check-ins.`);
  } catch (err) {
    alert("Import failed: " + err.message);
  }
  e.target.value = "";
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
  const newHash = captureHash(capture);
  // Only invalidate the plan when the capture actually changed since it was generated.
  if (currentSession.captureHash && newHash !== currentSession.captureHash) {
    currentSession.aiAssessment = null;
    currentSession.roadmap = "";
    currentSession.captureHash = null;
  }
  currentSession.humanCapture = hasData ? capture : emptyCapture();
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
      currentSession.aiAssessment = normalizeAssessment(assessResult.data.assessment);
      if (assessResult.data.rateLimit?.remaining !== undefined) {
        rateLimitInfo.remaining = assessResult.data.rateLimit.remaining;
        updateRateLimitUI();
      }
      const roadmapResult = await apiPost(`/api/sessions/${sId}/roadmap`, { adaptation: currentAdaptationPayload() });
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

  currentSession.captureHash = captureHash(currentSession.humanCapture);
  saveSession();
  renderAssessment();
  renderRoadmap();
  renderCompleteOutput();
  updateWizard();
});

document.querySelector("#roadmap-editor").addEventListener("input", () => {
  if (!currentSession) return;
  currentSession.roadmap = document.querySelector("#roadmap-editor").value;
  saveSession();
  renderCompleteOutput();
  updateWizard();
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
  const remaining = rateLimitInfo.remaining ?? 0;
  const willFallback = (deepMode === "full" || deepMode === "auto") && remaining < 12;
  showLoading(willFallback
    ? "Budget low — running 9 agents in Fast mode (1-2 calls)..."
    : (deepMode === "full" ? "9 independent agents analyzing in parallel..." : "9 agents analyzing in one pass..."));
  const result = await apiPost(`/api/sessions/${sId}/deep-analysis`, { mode: deepMode }, 120000);
  hideLoading();

  if (result.ok) {
    currentSession.deepAnalysis = {
      perspectives: result.data.perspectives,
      synthesis: result.data.synthesis,
      modeUsed: result.data.modeUsed,
      cached: result.data.cached,
      hash: result.data.hash
    };
    if (result.data.rateLimit?.remaining !== undefined) {
      rateLimitInfo.remaining = result.data.rateLimit.remaining;
      updateRateLimitUI();
    }
    saveSession();
    renderDeepAnalysis(currentSession.deepAnalysis);
    const modeLabel = result.data.cached ? "cached (0 AI calls)" : result.data.modeUsed;
    alert(`Deep analysis complete — mode: ${modeLabel}.`);
  } else {
    if (result.status === 429) {
      alert(`Rate limit reached (${result.data.rateLimit?.remaining ?? 0} remaining, resets ${result.data.rateLimit?.resetAt ? new Date(result.data.rateLimit.resetAt).toLocaleTimeString() : "later"}). Switch to Fast mode or wait.`);
      pollRateLimit();
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
  const assessment = normalizeAssessment(currentSession.aiAssessment || generateAssessment());
  const packet = completeOutputText();
  const adaptState = computeAdaptation(currentSession.target);
  const status = adaptState.phase === "immune"
    ? "embodied"
    : (adaptState.phase === "transferring" || (adaptState.avgQuality >= 8 && adaptState.spinCount >= 3))
      ? "validated"
      : "candidate";
  const template = {
    id: `${Date.now()}-${currentSession.target.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    target: currentSession.target,
    domain: currentSession.domain,
    invariant: inferTemplateCandidate(currentSession, assessment),
    assessmentSummary: assessment.material,
    roadmap: packet,
    createdAt: new Date().toISOString(),
    status,
    evidence: adaptState.spinCount
  };
  templates.push(template);
  writeJson(STORAGE_KEYS.templates, templates);
  renderTemplates();
  setView("templates");
  alert(`Roadmap template saved to Template Memory (status: ${status}, ${adaptState.spinCount} spins of evidence).`);
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
  // Skip network polling while the tab is hidden so a background MAS tab
  // never wakes the CPU/network every 15s for nothing.
  if (document.hidden) return;
  if (apiAvailable) await pollRateLimit();
  else await checkApiHealth().then(() => { if (apiAvailable) pollRateLimit(); });
}, 15000);

selectNode(activeNodeId);
renderSession();
renderTemplates();
renderSources();
renderAdaptationPanel();
