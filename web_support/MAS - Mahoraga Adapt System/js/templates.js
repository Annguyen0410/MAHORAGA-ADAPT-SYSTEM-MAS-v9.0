// ============================================================
// Template memory: statuses, rendering
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> ui -> main (see index.html).
// ============================================================

let templates = normalizeTemplates(readJson(STORAGE_KEYS.templates, null) || readJson(STORAGE_KEYS.legacyTemplates, []));

const TEMPLATE_STATUS = {
  candidate: { label: "Candidate", color: "var(--warning)" },
  validated: { label: "Validated", color: "var(--accent-2)" },
  embodied: { label: "Embodied", color: "var(--accent)" }
};

function templateStatusBadge(template) {
  const meta = TEMPLATE_STATUS[template.status] || TEMPLATE_STATUS.candidate;
  return `<span class="template-status" style="border-color:${meta.color};color:${meta.color}">${meta.label}</span>`;
}

function renderTemplates() {
  const list = document.querySelector("#template-list");
  if (templates.length === 0) {
    list.innerHTML = `<div class="empty-state">Template memory is empty. Save an edited roadmap after assessment.</div>`;
    return;
  }
  // Lazy roadmap: cards render without the heavy packet text; the full
  // roadmap is injected only when the user opens it. Keeps DOM tiny even
  // with hundreds of saved templates.
  list.innerHTML = templates
    .slice()
    .reverse()
    .map((template) => {
      const roadmapLen = (template.roadmap || "").length;
      return `
      <article class="template-card roadmap-template" data-template-id="${escapeHtml(template.id)}">
        <h3>${escapeHtml(template.target)} ${templateStatusBadge(template)}</h3>
        <p><strong>Domain:</strong> ${escapeHtml(domainLabel(template.domain))}</p>
        <p><strong>Template candidate:</strong> ${escapeHtml(template.invariant)}</p>
        <p><strong>Assessment:</strong> ${escapeHtml(template.assessmentSummary)}</p>
        <p><strong>Saved:</strong> ${escapeHtml(new Date(template.createdAt).toLocaleString())} · <strong>Evidence:</strong> ${template.evidence || 0} spins</p>
        <button class="ghost-button template-roadmap-toggle" type="button">${roadmapLen > 0 ? `Show roadmap (${roadmapLen} chars)` : "No roadmap"}</button>
      </article>
    `;
    })
    .join("");

  list.querySelectorAll(".template-roadmap-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".template-card");
      const template = templates.find((t) => t.id === card.dataset.templateId);
      if (!template) return;
      const existing = card.querySelector("pre");
      if (existing) {
        existing.remove();
        btn.textContent = `Show roadmap (${(template.roadmap || "").length} chars)`;
        return;
      }
      const pre = document.createElement("pre");
      pre.textContent = template.roadmap || "";
      card.appendChild(pre);
      btn.textContent = "Hide roadmap";
    });
  });
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
