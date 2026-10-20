const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
function context(stored = {}) {
  const window = {};
  const sandbox = { window, console: { warn() {}, log() {}, error() {} }, localStorage: {
    getItem: key => stored[key] ?? null, setItem: (key, value) => { stored[key] = value; }, removeItem: key => { delete stored[key]; }
  } };
  vm.createContext(sandbox); return sandbox;
}
test('corrupt layout is recovered without deleting saved bytes; sizes bounded', () => {
  const stored = { linkLumina_layout: '{broken' }; const sandbox = context(stored);
  vm.runInContext(source('layout.js'), sandbox); const layout = sandbox.window.LayoutManager;
  layout.loadSettings(); assert.equal(layout.settings.sidebarWidth, 256); assert.equal(stored.linkLumina_layout, '{broken');
  stored.linkLumina_layout = JSON.stringify({ sidebarWidth: -5, cardMinWidth: 99999, minSidebarWidth: -100, timelineGraphHeight: 'bad' });
  layout.loadSettings(); assert.equal(layout.settings.sidebarWidth, 200); assert.equal(layout.settings.cardMinWidth, 600);
  assert.equal(layout.settings.minSidebarWidth, 200); assert.equal(layout.settings.timelineGraphHeight, 600);
});
test('invalid rules cannot crash events or inject modal HTML', async () => {
  const stored = { linkLumina_laws: '{bad', linkLumina_custom_laws: JSON.stringify([null, { id: "x');alert(1)", name: 'unsafe', trigger: [] },
    { id: 'safe', name: '<img onerror=alert(1)>', description: '<script>', trigger: ['link_added'], enabled: true, config: { actionType: 'notify', actionParam: 'hello' } }]) };
  const sandbox = context(stored); vm.runInContext(source('laws.js'), sandbox);
  const rules = sandbox.window.LawEngine; rules.loadLaws(); assert.equal(rules.customLaws.length, 1);
  assert.equal(rules.laws.length, 4); await rules.emit('link_visited', {});
  assert.equal(vm.runInContext("lawText('<img onerror=alert(1)>')", sandbox), '&lt;img onerror=alert(1)&gt;');
});
test('service worker deletes only owned caches and ignores APIs', async () => {
  const handlers = {}, deleted = [];
  const sandbox = { URL, Set, Response, console, self: { registration: { scope: 'https://example.test/link/' }, location: { origin: 'https://example.test' },
    addEventListener: (event, handler) => { handlers[event] = handler; }, clients: { claim() {} } },
    caches: { keys: async () => ['other-app', 'linklumina-shell-v3', 'linklumina-shell-v4'], delete: async key => { deleted.push(key); } } };
  vm.createContext(sandbox); vm.runInContext(source('sw.js'), sandbox);
  let activated; handlers.activate({ waitUntil: promise => { activated = promise; } }); await activated;
  assert.deepEqual(deleted, ['linklumina-shell-v3']);
  let intercepted = false;
  handlers.fetch({ request: { method: 'GET', headers: new Headers(), url: 'https://example.test/api/private' }, respondWith() { intercepted = true; } });
  assert.equal(intercepted, false);
});
