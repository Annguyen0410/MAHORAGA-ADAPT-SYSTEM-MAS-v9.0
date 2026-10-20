const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'script.js'), 'utf8');
const handler = source.slice(source.indexOf('async function handleAddLink('), source.indexOf('// Convert file to Base64', source.indexOf('async function handleAddLink(')));
function setup({ failSave = false, failRender = false, editing = false } = {}) {
    const elements = {};
    for (const id of ['submitBtn', 'submitText', 'submitLoading', 'linkUrl', 'linkTitle', 'linkCategory', 'linkTags', 'linkNotes', 'imageInput', 'imagePreview', 'previewImg'])
        elements[id] = { value: '', innerHTML: 'Save', disabled: false, files: [], dataset: {}, classList: { add() {}, remove() {}, contains: () => false }, querySelector: () => null };
    elements.linkUrl.value = 'https://example.com/study'; elements.linkTitle.value = 'New title'; elements.linkCategory.value = 'General';
    elements.previewImg.src = 'data:image/png;base64,abc';
    const original = { id: 'existing', url: 'https://example.com/study', title: 'Old title' };
    const saves = [], messages = [];
    const sandbox = { document: { getElementById: id => elements[id] }, links: editing ? [original] : [],
        editingLinkId: editing ? 'existing' : null, URL, crypto: { randomUUID: () => 'unique-id' },
        setTimeout, clearTimeout, console, window: {}, neonColors: ['#aaaaaa'],
        initializeIcons() {}, autoCategorizeUrl: () => 'General', generateAutoTags: () => ['study'], generateAutoNoteForLink: () => '',
        saveLinkToDB: async link => { if (failSave) throw Error('disk full'); saves.push({ ...link }); },
        showToast: (text, kind) => messages.push({ text, kind }), checkMilestone() {}, updateAllTags() {},
        renderLinks() { if (failRender) throw Error('renderer failed'); }, renderCategoryFilters() {}, closeModal() {}, updateStorageStatsIfOpen() {} };
    vm.createContext(sandbox); vm.runInContext(handler, sandbox);
    return { sandbox, elements, saves, messages, original };
}
test('failed write retains bookmark form and previous array; button recovers', async () => {
    const state = setup({ failSave: true }); await state.sandbox.handleAddLink({ preventDefault() {} });
    assert.equal(state.sandbox.links.length, 0); assert.equal(state.elements.linkTitle.value, 'New title');
    assert.equal(state.elements.submitBtn.disabled, false); assert.match(state.messages.at(-1).text, /Could not save/);
});
test('new bookmark commits exactly once', async () => {
    const state = setup(); await state.sandbox.handleAddLink({ preventDefault() {} });
    assert.equal(state.saves.length, 1); assert.equal(state.sandbox.links[0].id, 'unique-id');
});
test('edited bookmark commits once and retains identity', async () => {
    const state = setup({ editing: true }); await state.sandbox.handleAddLink({ preventDefault() {} });
    assert.equal(state.saves.length, 1); assert.equal(state.saves[0].id, 'existing'); assert.equal(state.saves[0].title, 'New title');
});
test('post-save renderer failure does not roll back a committed bookmark', async () => {
    const state = setup({ failRender: true }); await state.sandbox.handleAddLink({ preventDefault() {} });
    assert.equal(state.sandbox.links.length, 1); assert.equal(state.saves.length, 1); assert.match(state.messages.at(-1).text, /saved locally/);
});
