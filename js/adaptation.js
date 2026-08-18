// ============================================================
// Adaptation engine: wheel state machine, check-ins, next-step
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

let adaptationHistory = normalizeHistory(readJson(STORAGE_KEYS.history, []));

const PHASE_META = {
  "first-hit": { label: "First Hit", icon: "⚡", color: "var(--warning)" },
  calibrating: { label: "Calibrating", icon: "🎯", color: "var(--accent-2)" },
  drilling: { label: "Drilling", icon: "🔄", color: "var(--accent)" },
  refining: { label: "Refining", icon: "⚙️", color: "var(--warning)" },
  transferring: { label: "Transferring", icon: "🧭", color: "var(--accent-2)" },
  immune: { label: "Immune", icon: "🛡️", color: "var(--accent)" },
  stuck: { label: "Stuck", icon: "🧱", color: "var(--danger)" }
};

const TREND_META = {
  improving: { label: "Improving", icon: "📈", color: "var(--accent)" },
  plateau: { label: "Plateau", icon: "➖", color: "var(--warning)" },
  declining: { label: "Declining", icon: "📉", color: "var(--danger)" },
  unknown: { label: "Too early", icon: "🌱", color: "var(--muted)" }
};

function clamp01to10(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(10, n));
}

function normalizeHistory(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((c) => ({
      id: c.id || `ci-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      target: c.target || "Untitled target",
      date: c.date || new Date().toISOString(),
      quality: clamp01to10(c.quality),
      effort: clamp01to10(c.effort),
      stability: clamp01to10(c.stability),
      discomfort: clamp01to10(c.discomfort),
      note: c.note || "",
      contextChanged: !!c.contextChanged
    }))
    .sort((a, b) => new Date(a.date) - new Date(b.date));
}

function historyForTarget(target) {
  return adaptationHistory.filter((c) => c.target === target);
}

// Linear regression slope over quality scores: the engine's "pulse".
function qualitySlope(checkIns) {
  if (checkIns.length < 2) return 0;
  const n = checkIns.length;
  const meanX = (n - 1) / 2;
  const meanY = checkIns.reduce((a, c) => a + c.quality, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - meanX) * (checkIns[i].quality - meanY);
    den += (i - meanX) * (i - meanX);
  }
  return den === 0 ? 0 : num / den;
}

function detectTrend(checkIns) {
  if (checkIns.length < 2) return "unknown";
  const slope = qualitySlope(checkIns);
  const last = checkIns[checkIns.length - 1].quality - checkIns[checkIns.length - 2].quality;
  if (slope > 0.5 || last >= 1) return "improving";
  if (slope < -0.5 || last <= -1) return "declining";
  return "plateau";
}

function determinePhase(checkIns, trend) {
  const n = checkIns.length;
  if (n === 0) return "first-hit";
  const last = checkIns[n - 1];
  const avgQuality = checkIns.reduce((a, c) => a + c.quality, 0) / n;

  // Consistent high performance + low effort across at least 3 spins.
  // Anti-overfit: never conclude mastery from one or two lucky samples.
  if (n >= 3 && avgQuality >= 8 && last.stability >= 7 && last.effort <= 4) {
    return (last.contextChanged && last.quality >= 8) ? "immune" : "transferring";
  }

  // Sustained decline below mastery across several spins → stuck loop.
  if (trend === "declining" && n >= 3 && avgQuality < 8) return "stuck";

  // Flat quality across several spins → the current variable is exhausted.
  if (trend === "plateau" && n >= 3) return "refining";

  if (trend === "improving") return "drilling";

  // Early dip or flat start → change tactic, do not panic.
  if (trend === "declining" || trend === "plateau") return "refining";

  return n === 1 ? "calibrating" : "drilling";
}

function computeAdaptation(target) {
  const checkIns = historyForTarget(target);
  const trend = detectTrend(checkIns);
  const phase = determinePhase(checkIns, trend);
  const n = checkIns.length;
  const avgQuality = n ? checkIns.reduce((a, c) => a + c.quality, 0) / n : 0;
  const last = n ? checkIns[n - 1] : null;
  return {
    target,
    checkIns,
    spinCount: n,
    phase,
    trend,
    avgQuality: Math.round(avgQuality * 10) / 10,
    lastQuality: last ? last.quality : null,
    lastStability: last ? last.stability : null,
    lastEffort: last ? last.effort : null,
    transferPassed: checkIns.filter((c) => c.contextChanged && c.quality >= 8).length,
    slope: qualitySlope(checkIns)
  };
}

function currentAdaptationPayload() {
  if (!currentSession) return null;
  const state = computeAdaptation(currentSession.target);
  const assessment = currentSession.aiAssessment || generateAssessment();
  return {
    phase: state.phase,
    trend: state.trend,
    spinCount: state.spinCount,
    transferPassed: state.transferPassed,
    nextStep: nextStepFor(state, assessment.variables)
  };
}

// The wheel's answer: a focused next action, chosen from data.
function nextStepFor(state, variables) {
  const target = state.target;
  const vars = (variables && variables.length ? variables : ["a control variable"]);
  const firstVar = vars[0];
  const secondVar = vars[1] || "a different variable";
  switch (state.phase) {
    case "first-hit":
      return `First contact with "${target}". Run ONE baseline test at normal effort. Record the result as your first check-in — do not try to improve yet. The first miss is data, not failure.`;
    case "calibrating":
      return `Baseline established. Do 3 slow repetitions focusing on ${firstVar}. Keep everything else constant, then log a check-in. Compare quality and effort to your first spin.`;
    case "drilling":
      return `You are improving. Keep the winning variable (${firstVar}) and add 2-3 reps. Stop before quality drops — the moment fatigue appears, the drill is over. Log the result.`;
    case "refining":
      return `Quality has flattened across ${state.spinCount} spins. ${firstVar} is squeezed — CHANGE ONE variable (try ${secondVar}) instead of pushing harder. Keep the rest constant, then log a new check-in.`;
    case "transferring":
      return `Quality is high (${state.lastQuality}/10) with low effort. PROVE it generalizes: repeat in a changed context (different tool, place, person, or time pressure). If quality holds at 8+, you are near immunity.`;
    case "immune":
      return `You have adapted to "${target}" — consistent high quality across contexts. Save this as a validated template, then pick your next target. The wheel is ready to spin again.`;
    case "stuck":
      return `Quality is dropping. STOP pushing. Reduce difficulty, return to baseline, and change ONE variable. If the same failure repeats twice, your model of the problem is wrong — re-observe before re-drilling.`;
    default:
      return `Log a check-in to let the wheel read your data.`;
  }
}

function renderSparkline(checkIns) {
  const el = document.querySelector("#progress-sparkline");
  if (!el) return;
  if (checkIns.length < 2) {
    el.innerHTML = `<div class="empty-state">Log at least 2 check-ins to see your evolution curve.</div>`;
    return;
  }
  const w = 560, h = 120, pad = 10;
  const pts = checkIns.map((c, i) => {
    const x = pad + (i * (w - pad * 2)) / Math.max(1, checkIns.length - 1);
    const y = h - pad - (c.quality / 10) * (h - pad * 2);
    return [x, y];
  });
  const poly = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  el.innerHTML = `
    <svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" class="spark-axis"/>
      <polyline points="${poly}" class="spark-line"/>
      ${pts.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="3" class="spark-dot"/>`).join("")}
      <circle cx="${last[0]}" cy="${last[1]}" r="5" class="spark-dot-last"/>
    </svg>
  `;
}

function renderCheckinList(checkIns) {
  const el = document.querySelector("#checkin-list");
  if (!el) return;
  if (!checkIns.length) {
    el.innerHTML = `<div class="empty-state">No spins yet. Run the plan, then log your first check-in.</div>`;
    return;
  }
  const shown = checkIns.slice(-15).reverse();
  el.innerHTML = shown
    .map((c) => `
      <div class="checkin-item">
        <span class="checkin-date">${new Date(c.date).toLocaleDateString()}</span>
        <div class="checkin-scores">
          <span class="score-chip quality">Q ${c.quality}</span>
          <span class="score-chip effort">E ${c.effort}</span>
          <span class="score-chip stability">S ${c.stability}</span>
          <span class="score-chip discomfort">D ${c.discomfort}</span>
          ${c.contextChanged ? `<span class="score-chip transfer">Transfer</span>` : ""}
        </div>
        <p class="checkin-note">${escapeHtml(c.note)}</p>
      </div>
    `)
    .join("");
}

function renderAdaptationPanel() {
  const emptyEl = document.querySelector("#adaptation-empty");
  const layoutEl = document.querySelector("#adaptation-layout");
  const listEl = document.querySelector("#checkin-list");
  const badge = document.querySelector("#phase-badge");
  if (!layoutEl) return;

  const target = currentSession?.target;
  if (!target) {
    if (emptyEl) emptyEl.hidden = false;
    layoutEl.hidden = true;
    if (listEl) listEl.hidden = true;
    if (badge) {
      badge.textContent = "—";
      badge.style.borderColor = "var(--line)";
      badge.style.color = "var(--muted)";
    }
    return;
  }

  if (emptyEl) emptyEl.hidden = true;
  layoutEl.hidden = false;
  if (listEl) listEl.hidden = false;

  const state = computeAdaptation(target);
  const phase = PHASE_META[state.phase];
  const trend = TREND_META[state.trend];
  if (badge) {
    badge.textContent = `${phase.icon} ${phase.label}`;
    badge.style.borderColor = phase.color;
    badge.style.color = phase.color;
  }
  const assessment = currentSession.aiAssessment || generateAssessment();
  const nextStep = nextStepFor(state, assessment.variables);

  const metrics = document.querySelector("#adaptation-metrics");
  if (metrics) {
    metrics.innerHTML = `
      <div class="metric-tile"><span>Spins</span><strong>${state.spinCount}</strong></div>
      <div class="metric-tile"><span>Avg quality</span><strong>${state.avgQuality}</strong></div>
      <div class="metric-tile"><span>Trend</span><strong style="color:${trend.color}">${trend.icon} ${trend.label}</strong></div>
      <div class="metric-tile"><span>Transfer passes</span><strong>${state.transferPassed}</strong></div>
    `;
  }
  const nextEl = document.querySelector("#next-step");
  if (nextEl) {
    nextEl.innerHTML = `
      <div class="next-step-label">🧭 Next spin (adaptive)</div>
      <p>${escapeHtml(nextStep)}</p>
    `;
  }
  renderSparkline(state.checkIns);
  renderCheckinList(state.checkIns);
}

function logCheckIn() {
  if (!currentSession) {
    alert("Define a target first.");
    return;
  }
  const quality = Number(document.querySelector("#ci-quality").value);
  const effort = Number(document.querySelector("#ci-effort").value);
  const stability = Number(document.querySelector("#ci-stability").value);
  const discomfort = Number(document.querySelector("#ci-discomfort").value);
  if (![quality, effort, stability, discomfort].every((v) => Number.isFinite(v))) {
    alert("Fill all four scores: quality, effort, stability, discomfort.");
    return;
  }
  const checkIn = {
    id: `ci-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    target: currentSession.target,
    date: new Date().toISOString(),
    quality: clamp01to10(quality),
    effort: clamp01to10(effort),
    stability: clamp01to10(stability),
    discomfort: clamp01to10(discomfort),
    note: formValue("#ci-note"),
    contextChanged: document.querySelector("#ci-context").checked
  };
  adaptationHistory.push(checkIn);
  writeJson(STORAGE_KEYS.history, adaptationHistory);
  ["#ci-quality", "#ci-effort", "#ci-stability", "#ci-discomfort"].forEach((sel) => {
    const el = document.querySelector(sel);
    if (el) el.value = "";
  });
  const note = document.querySelector("#ci-note");
  if (note) note.value = "";
  const ctx = document.querySelector("#ci-context");
  if (ctx) ctx.checked = false;
  renderAdaptationPanel();
  // Refresh the roadmap so its adaptive header reflects the new state.
  if (currentSession.roadmap) {
    currentSession.roadmap = addAdaptiveHeader(currentSession.roadmap);
    saveSession();
    renderRoadmap();
  }
  updateWizard();
}

function addAdaptiveHeader(roadmap) {
  const state = computeAdaptation(currentSession.target);
  const assessment = currentSession.aiAssessment || generateAssessment();
  const nextStep = nextStepFor(state, assessment.variables);
  const phase = PHASE_META[state.phase];
  const trend = TREND_META[state.trend];
  const header = [
    `[ADAPTIVE STATE] ${phase.icon} ${phase.label} — ${trend.icon} ${trend.label} (spin ${state.spinCount})`,
    `NEXT SPIN: ${nextStep}`
  ].join("\n");
  const lines = roadmap.split("\n");
  const idx = lines.findIndex((l) => l.startsWith("[ADAPTIVE STATE]"));
  if (idx !== -1) {
    lines.splice(idx, 2, header);
    return lines.join("\n");
  }
  return header + "\n\n" + roadmap;
}
