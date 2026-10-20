// Template memory tests: lazy roadmap must not leak into the DOM before opening.
const { standardPage, loadClient } = require("./harness");

const body = `
  templates = [{
    id: "tpl-1", target: "guitar", domain: "tool", invariant: "invariant",
    assessmentSummary: "wood", roadmap: "1. Tune\\n2. Practice",
    createdAt: new Date().toISOString(), status: "validated", evidence: 5
  }];
  renderTemplates();
  const html = window.__list.innerHTML;
  if (!html.includes("Show roadmap")) throw new Error("toggle button missing");
  if (html.includes("1. Tune")) throw new Error("roadmap leaked into DOM before open");
  if (!html.includes("Validated")) throw new Error("status badge missing");
  if (!html.includes("5 spins")) throw new Error("evidence missing");
  console.log("  templates: lazy roadmap (no leak), status badge, evidence OK");
`;

const page = standardPage();
loadClient({
  document: page.document,
  localStorage: page.localStorage,
  windowExtras: { __list: page.els["#template-list"] },
  body
});
