"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const fields = [{ id: 'books', value: '10', defaultValue: '', type: 'number', tagName: 'INPUT', min: '0', max: '1000' }, { id: 'education', value: '50', defaultValue: '0', tagName: 'SELECT', options: [{ value: '0' }, { value: '50' }] }];
const elements = new Map(fields.map(field => [field.id, field]));
function element(id) { if (!elements.has(id)) elements.set(id, { value: '', min: '', max: '', textContent: '', innerHTML: '', style: {}, parentElement: { appendChild(el) { elements.set(el.id, el); } }, setAttribute() {}, getContext() { return {}; }, classList: { remove() {} } }); return elements.get(id); }
const saved = new Map();
let quota = false;
const context = vm.createContext({
  document: { addEventListener() {}, getElementById: element, querySelectorAll: () => fields, createElement: () => ({ setAttribute() {} }) },
  localStorage: { getItem: key => saved.get(key) ?? null, setItem: (key, value) => { if (quota) throw Error('quota'); saved.set(key, value); }, removeItem: key => { if (quota) throw Error('quota'); saved.delete(key); } },
  setTimeout, clearTimeout, Chart: function () { this.destroy = () => {}; }, confirm: () => true,
});
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../web_support/World Leaderboard/script.js'), 'utf8'), context);
vm.runInContext("DOM.historyStats = document.getElementById('history-stats'); DOM.inputFields = document.querySelectorAll('.input-field'); DOM.progressFill = document.getElementById('progress-fill'); DOM.progressText = document.getElementById('progress-text');", context);
assert.throws(() => context.applyProfileData({ books: '20', education: 'bogus' }));
assert.equal(fields[0].value, '10', 'all fields validated before applying');
context.applyProfileData({ books: '20', education: '50', 'calculate-btn': 'attacker' });
assert.equal(fields[0].value, '20');
assert.equal(element('calculate-btn').value, '', 'only actual input fields can be imported');
assert.throws(() => context.applyProfileData({ books: Infinity }));
fields[0].value = '-7'; assert.equal(context.getValue('books'), 0);
fields[0].value = 'Infinity'; assert.equal(context.getValue('books'), 0);
fields[0].value = '999999'; assert.equal(context.getValue('books'), 1000);
const rank = context.calculateRanking();
assert.ok(Number.isFinite(rank.rank) && rank.rank >= 1 && rank.rank <= 8000000000);
assert.ok(Object.values(rank.scores).every(value => value >= 0 && value <= 100));
saved.set('worldRankingHistory', '{broken');
context.displayRankHistory(100, 99);
assert.equal(saved.get('worldRankingHistory'), '{broken');
assert.ok(element('profile-storage-status').textContent.includes('preserved'));
saved.set('worldRankingHistory', JSON.stringify([null, { date: 0 }, { date: '2026-09-28', rank: 100, percentile: 99 }]));
context.displayRankHistory(90, 99);
assert.ok(JSON.parse(saved.get('worldRankingHistory')).every(entry => typeof entry.date === 'string'));
quota = true;
context.autoSave();
assert.ok(element('profile-storage-status').textContent.includes('retained'));
const before = fields[0].value;
context.clearAll();
assert.equal(fields[0].value, before);
saved.set('worldRankingAutoSave', '{bad');
context.loadAutoSave();
assert.equal(saved.get('worldRankingAutoSave'), '{bad');
console.log('leaderboard validation, bounded scoring, corrupt history and quota checks passed');
