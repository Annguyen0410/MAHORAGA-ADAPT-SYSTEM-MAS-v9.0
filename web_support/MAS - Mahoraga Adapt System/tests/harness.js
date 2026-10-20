// Shared harness for MAS tests.
// Loads the browser modules (js/*.js) inside a Node `new Function` scope with a
// stubbed DOM, then runs the test body in that same scope so it can reach the
// modules' internal state (currentSession, templates, adaptationHistory, ...).
const fs = require("fs");
const path = require("path");

const CLIENT_FILES = [
  "utils.js", "storage.js", "api.js", "graph.js", "adaptation.js",
  "assessment.js", "session.js", "templates.js", "backup.js", "ui.js", "main.js"
];

// Stateful element proxy: stores value/textContent/innerHTML/hidden/checked.
function makeEl(extra = {}) {
  const state = { value: "", textContent: "", innerHTML: "", hidden: false, checked: false, ...extra };
  const classes = new Set();
  return new Proxy(function () {}, {
    get(t, prop) {
      if (prop in state) return state[prop];
      if (prop === "classList") {
        return {
          toggle: (c, on) => { if (on) classes.add(c); else classes.delete(c); },
          add: (c) => classes.add(c),
          remove: (c) => classes.delete(c),
          contains: (c) => classes.has(c)
        };
      }
      if (prop === "style") return {};
      if (prop === "dataset") return {};
      return () => makeEl();
    },
    set(t, prop, v) { state[prop] = v; return true; }
  });
}

function makeDot(step) {
  const classes = new Set();
  return {
    dataset: { step: String(step) },
    disabled: false,
    classList: {
      toggle: (c, on) => { if (on) classes.add(c); else classes.delete(c); },
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c)
    },
    addEventListener: () => {},
    _classes: classes
  };
}

// All element ids the client touches, so tests don't have to enumerate them.
const STANDARD_IDS = [
  "#node-layer", "#edge-paths", "#node-category", "#node-title", "#node-definition",
  "#node-practice", "#node-source", "#node-relations",
  "#session-summary", "#capture-save-status", "#capture-score", "#assessment-output",
  "#roadmap-editor", "#deep-analysis-output", "#deep-badge", "#deep-cost", "#step-progress",
  "#adaptation-empty", "#adaptation-layout", "#adaptation-metrics", "#progress-sparkline",
  "#next-step", "#checkin-list", "#phase-badge",
  "#ci-quality", "#ci-effort", "#ci-stability", "#ci-discomfort", "#ci-note", "#ci-context",
  "#log-checkin", "#checkin-form",
  "#target-name", "#target-domain", "#target-goal", "#skill-level",
  "#historical-patterns", "#previous-attempts",
  "#observed-properties", "#evaluation", "#description", "#test-performed", "#test-result",
  "#environment", "#measured-signals", "#failure-type",
  "#rate-limit-badge", "#rate-limit-remaining", "#rate-limit-fill", "#api-status-indicator",
  "#rate-limit-text", "#loading-overlay", "#loading-text",
  "#background-modal", "#open-background", "#close-background",
  "#template-list", "#source-list",
  "#export-data", "#import-data", "#import-file"
];

const STANDARD_SELECTORS = {
  ".step-dot": [1, 2, 3, 4].map(makeDot),
  ".wizard-step": [1, 2, 3, 4].map((step) => ({
    dataset: { step: String(step) },
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } }
  })),
  "[data-next-step]": [2, 3, 4].map((n) => ({ dataset: { nextStep: String(n) }, disabled: false, addEventListener: () => {} })),
  "[data-prev-step]": [],
  ".deep-mode-chip": [],
  ".nav-button": [],
  "[data-filter]": [],
  ".example-chip": [],
  ".perspective-card-header": [],
  "[data-node]": [],
  "[data-relation]": [],
  ".template-roadmap-toggle": []
};

// Build a standard page: every element id + selector pre-registered.
function standardPage(overrides = {}) {
  const els = {};
  for (const id of STANDARD_IDS) els[id] = makeEl();
  const selectors = {};
  for (const [sel, arr] of Object.entries(STANDARD_SELECTORS)) selectors[sel] = arr.slice();

  for (const [id, extra] of Object.entries(overrides.els || {})) {
    els[id] = typeof extra === "function" ? extra(els[id], makeEl) : makeEl(extra);
  }
  for (const [sel, arr] of Object.entries(overrides.selectors || {})) {
    selectors[sel] = arr;
  }

  const store = { ...(overrides.localStorage || {}) };
  const localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; }
  };

  const document = {
    querySelector: (sel) => els[sel] || makeEl(),
    querySelectorAll: (sel) => selectors[sel] || [],
    createElement: () => makeEl(),
    addEventListener: () => {}
  };

  return { els, selectors, document, localStorage };
}

// Load the client modules and run `body` inside their scope.
// The body is wrapped in an async IIFE so tests may `await` (e.g. importData).
// main.js installs a 15s setInterval that keeps the event loop alive, so we
// exit explicitly after the body settles.
function loadClient({ document, localStorage, windowExtras = {}, body }) {
  const src = CLIENT_FILES
    .map((f) => fs.readFileSync(path.join(__dirname, "..", "js", f), "utf8"))
    .join("\n;\n");
  const factory = new Function(
    "document", "localStorage", "fetch", "window",
    src + "\n;\nreturn (async () => {\n" + body + "\n})();"
  );
  const result = factory(document, localStorage, () => Promise.reject(new Error("offline")), windowExtras);
  Promise.resolve(result).then(
    () => process.exit(0),
    (e) => { console.error("  FAIL: " + e.message); process.exit(1); }
  );
  return result;
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

module.exports = { makeEl, makeDot, standardPage, loadClient, assert };
