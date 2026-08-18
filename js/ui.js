// ============================================================
// View switching, loading overlay, rate-limit UI, deep-analysis render
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

let isAiCalling = false;
let deepMode = "auto"; // "auto" | "batch" | "full"

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
  updateDeepCost();
}

function updateDeepCost() {
  const costEl = document.querySelector("#deep-cost");
  if (!costEl) return;
  if (!geminiAvailable) {
    costEl.textContent = "AI offline — add GEMINI_API_KEY to server/.env";
    costEl.style.color = "var(--muted)";
    return;
  }
  const remaining = rateLimitInfo.remaining ?? 0;
  const est = deepMode === "full" ? 10 : deepMode === "batch" ? 2 : (remaining >= 12 ? 10 : 2);
  const color = remaining >= est ? "var(--accent)" : remaining > 0 ? "var(--warning)" : "var(--danger)";
  costEl.textContent = `≈${est} AI calls · ${remaining} remaining${remaining < est ? " (not enough — will run Fast)" : ""}`;
  costEl.style.color = color;
}

document.querySelectorAll(".deep-mode-chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    deepMode = btn.dataset.deepMode;
    document.querySelectorAll(".deep-mode-chip").forEach((b) => b.classList.toggle("active", b === btn));
    updateDeepCost();
  });
});

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
  updateModelBudgetUI();
  updateDeepCost();
}

// Compact per-model quota line (e.g. "3.5-flash-lite 3/500/day · 3.1-flash-lite 0/500/day").
function updateModelBudgetUI() {
  const el = document.querySelector("#model-budget-text");
  if (!el) return;
  if (!apiAvailable || !modelBudgetInfo || !Array.isArray(modelBudgetInfo.models)) {
    el.textContent = "";
    return;
  }
  const parts = modelBudgetInfo.models
    .filter((m) => m.limit && m.used)
    .slice(0, 3)
    .map((m) => {
      const name = m.id.replace(/^gemini-/, "");
      const flag = m.used.dayCalls >= m.limit.rpd ? " ⛔" : m.blocked ? " ⏸" : "";
      return `${name} ${m.used.dayCalls}/${m.limit.rpd}/day${flag}`;
    });
  el.textContent = parts.length ? `Model budget: ${parts.join(" · ")}` : "";
  el.title = JSON.stringify(modelBudgetInfo, null, 2);
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

function setView(viewName) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelector(`#${viewName}-view`).classList.add("active");
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  if (viewName === "templates") renderTemplates();
  if (viewName === "sources") renderSources();
}

function renderDeepAnalysis(deepData) {
  const output = document.querySelector("#deep-analysis-output");
  if (!deepData) {
    output.innerHTML = `<div class="empty-state">Save human capture and run Deep Analysis to see 9 thinking perspectives and their synthesis.</div>`;
    return;
  }

  const { perspectives, synthesis } = deepData;
  const modeMeta = deepData.cached
    ? "♻️ Cached result — 0 AI calls (data unchanged)"
    : deepData.modeUsed === "full"
      ? "🔬 Full mode — 9 independent agents + synthesis"
      : deepData.modeUsed === "batch"
        ? "⚡ Fast mode — 9 agents batched into 1-2 calls"
        : "";
  const metaHtml = modeMeta ? `<div class="deep-meta">${modeMeta}</div>` : "";

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
    ${metaHtml}
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
