"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const catalogKey = 'an_nguyen_storage_system_v1';
const graphKey = 'an_nguyen_visualgraph_v1';
function page(relative, initial = {}, reduced = false) {
  const values = new Map(Object.entries(initial)), nodes = {}, events = {}, alerts = [];
  let failedKey = null, frameCount = 0;
  const drawing = new Proxy({}, { get: (_, name) => name === 'createRadialGradient' ? () => ({ addColorStop() {} }) : () => {}, set: () => true });
  function node(id) { return nodes[id] ||= { value: '', textContent: '', innerHTML: '', style: {}, width: 940, height: 560, handlers: {}, classList: { add() {}, remove() {}, contains() { return false; } }, addEventListener(name, handler) { this.handlers[name] = handler; }, getContext: () => drawing }; }
  node('categoryFilter').value = 'all'; node('sortFilter').value = 'latest'; node('topicType').value = 'note'; node('densityLevel').value = '18';
  const context = vm.createContext({
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => { if (key === failedKey) throw Error('quota'); values.set(key, value); }, removeItem: key => values.delete(key) },
    document: { hidden: false, getElementById: node, createElement: () => node('sprite'), addEventListener: (name, handler) => events[name] = handler },
    window: { addEventListener: (name, handler) => events[name] = handler, matchMedia: () => ({ matches: reduced, addEventListener() {} }) },
    requestAnimationFrame: () => ++frameCount, cancelAnimationFrame() {}, alert: message => alerts.push(message), setTimeout: fn => { fn(); return 1; }, clearTimeout() {},
  });
  vm.runInContext(fs.readFileSync(path.join(root, relative), 'utf8'), context);
  return { values, node, events, alerts, fail: key => failedKey = key, frames: () => frameCount };
}
const catalogPath = 'web_support/Cục Quản Lý/Hệ Thống Lưu Trữ Máy Chủ/app.js';
const graphPath = 'web_support/Cục Quản Lý/Hệ Thống Toàn Diện Cá Nhân/app.js';
const malicious = { id: '"><img src=x onerror=alert(1)>', name: '<img src=x onerror=alert(1)>.txt', size: '12', category: '__proto__', type: '<img src=x>', extension: '<svg onload=alert(1)>', uploadedAtFormatted: '<img src=x>', uploadedAt: '2026-09-29' };
let catalog = page(catalogPath, { [catalogKey]: JSON.stringify([malicious]) });
assert.ok(!catalog.node('fileList').innerHTML.includes('<img'));
assert.ok(catalog.node('fileList').innerHTML.includes('&lt;img'));
assert.equal(catalog.node('usedDisplay').textContent, '12 B');
const original = catalog.values.get(catalogKey);
catalog.fail(catalogKey);
catalog.node('fileList').handlers.click({ target: { getAttribute: () => malicious.id } });
assert.equal(catalog.values.get(catalogKey), original);
assert.ok(catalog.alerts.pop().includes('not changed'));
catalog.fail(null);
catalog.values.set(catalogKey, JSON.stringify([{ id: 'external', name: 'External.txt', size: 20 }]));
catalog.events.storage({ key: catalogKey });
assert.ok(catalog.node('fileList').innerHTML.includes('External.txt'));
catalog.node('fileInput').handlers.change({ target: { files: [{ name: 'New.txt', size: 2, type: 'text/plain' }], value: 'selected' } });
assert.equal(JSON.parse(catalog.values.get(catalogKey)).length, 2);
for (const invalid of ['{bad', '{}', '[null]', '[{"id":"x","name":"x","size":-1}]']) {
  catalog = page(catalogPath, { [catalogKey]: invalid });
  catalog.node('fileInput').handlers.change({ target: { files: [{ name: 'New.txt', size: 2, type: '' }], value: '' } });
  assert.equal(catalog.values.get(catalogKey), invalid);
  assert.ok(catalog.alerts.pop().includes('preserved'));
}
const topic = { id: malicious.id, title: malicious.name, content: 'Reliable learning through deliberate practice', keywords: ['<img src=x>'], nodes: [null], edges: [null], summary: '<img src=x>', type: '<svg>' };
let graph = page(graphPath, { [graphKey]: JSON.stringify([topic]) }, true);
assert.ok(!graph.node('topicLibrary').innerHTML.includes('<img'));
graph.node('topicLibrary').handlers.click({ target: { getAttribute: name => name === 'data-view' ? topic.id : null } });
assert.equal(graph.frames(), 0, 'reduced-motion graphs draw without a recurring animation');
assert.equal(graph.node('activeTitle').textContent, topic.title);
graph.node('topicTitle').value = 'My retained draft'; graph.node('topicContent').value = 'Practice leads to learning';
graph.fail(graphKey);
graph.node('generateBtn').handlers.click();
assert.equal(JSON.parse(graph.values.get(graphKey)).length, 1);
assert.equal(graph.node('topicTitle').value, 'My retained draft');
assert.ok(graph.alerts.pop().includes('draft is retained'));
graph.fail(null);
graph.values.set(graphKey, '[]'); graph.events.storage({ key: graphKey });
assert.equal(graph.node('activeTitle').textContent, 'No topic selected');
assert.equal(graph.values.has('an_nguyen_visualgraph_summary_v1'), false);
graph.node('generateBtn').handlers.click();
assert.equal(JSON.parse(graph.values.get(graphKey)).length, 1);
graph.node('topicLibrary').handlers.click({ target: { getAttribute: name => name === 'data-delete' ? JSON.parse(graph.values.get(graphKey))[0].id : null } });
assert.equal(JSON.parse(graph.values.get(graphKey)).length, 0);
assert.equal(graph.values.has('an_nguyen_visualgraph_summary_v1'), false);
for (const invalid of ['{bad', '{}', '[null]']) {
  graph = page(graphPath, { [graphKey]: invalid });
  graph.node('topicTitle').value = 'Draft'; graph.node('topicContent').value = 'Contents'; graph.node('generateBtn').handlers.click();
  assert.equal(graph.values.get(graphKey), invalid);
  assert.ok(graph.alerts.pop().includes('preserved'));
}
console.log('catalog and graph malicious data, corruption preservation, quota, cross-tab, deletion and reduced-motion checks passed');
