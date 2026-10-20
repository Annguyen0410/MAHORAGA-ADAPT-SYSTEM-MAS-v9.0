'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const SE = require('../search-engine.js');

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function makeIndex(links, folders) {
    return SE.buildIndex(links, folders);
}

const FOLDERS = [{ id: 'f1', name: 'Công việc' }, { id: 'f2', name: 'Học tập' }];
const LINKS = [
    { id: '1', title: 'Cà phê và lập trình', url: 'https://blog.dev/ca-phe', notes: 'học react mỗi sáng', tags: ['react', 'vietnam'], category: 'Dev', folderId: 'f1', favorite: true, pinned: true, visitCount: 10, createdAt: '2024-05-01' },
    { id: '2', title: 'React Documentation', url: 'https://react.dev', notes: 'official guide', tags: ['react', 'docs'], category: 'Dev', folderId: 'f2', favorite: false, pinned: false, visitCount: 2, createdAt: '2023-01-15' },
    { id: '3', title: 'Design Systems 101', url: 'https://design.example/101', notes: 'figma tips', tags: ['design'], category: 'Design', folderId: 'f2', favorite: false, pinned: false, visitCount: 0, createdAt: '2025-02-10' },
];

test('normalizeText strips Vietnamese diacritics', () => {
    assert.strictEqual(SE.normalizeText('Cà phê'), 'ca phe');
    assert.strictEqual(SE.normalizeText('  HỌC  TẬP  '), 'hoc tap');
    assert.strictEqual(SE.normalizeText(null), '');
});

test('parseQuery handles plain words, operators, negatives, phrases', () => {
    const q = SE.parseQuery('react -tutorial tag:docs "exact phrase" fav:true visits:>5');
    assert.deepStrictEqual(q.words, ['react']);
    assert.deepStrictEqual(q.excludeWords, ['tutorial']);
    assert.strictEqual(q.tag, 'docs');
    assert.deepStrictEqual(q.phrases, ['exact phrase']);
    assert.strictEqual(q.fav, true);
    assert.deepStrictEqual(q.visits, { op: '>', n: 5 });
    assert.ok(q.hasConstraints);
});

test('parseQuery maps #tag and @category shorthand', () => {
    const q = SE.parseQuery('#react @Design');
    assert.strictEqual(q.tag, 'react');
    assert.strictEqual(q.category, 'design');
});

test('parseQuery parses date range and boolean filters', () => {
    const q = SE.parseQuery('from:2024-01-01 to:2025-06-30 pinned:true read:false');
    assert.ok(q.from instanceof Date && !isNaN(q.from.getTime()));
    assert.ok(q.to instanceof Date && !isNaN(q.to.getTime()));
    assert.ok(q.from < q.to, 'from must precede to');
    // from clamps to start of day, to clamps to end of day (TZ-independent)
    assert.strictEqual(q.from.getHours(), 0);
    assert.strictEqual(q.from.getMinutes(), 0);
    assert.strictEqual(q.to.getHours(), 23);
    assert.strictEqual(q.to.getMinutes(), 59);
    assert.strictEqual(q.pinned, true);
    assert.strictEqual(q.read, false);
});

test('score: AND matching across words, accent-insensitive', () => {
    const idx = makeIndex(LINKS, FOLDERS);
    // "ca phe" (no accents) must match "Cà phê và lập trình"
    const q = SE.parseQuery('ca phe');
    assert.ok(SE.score(LINKS[0], q, idx) > 0);
    assert.strictEqual(SE.score(LINKS[1], q, idx), 0);
});

test('score: exclusion and filters reject', () => {
    const idx = makeIndex(LINKS, FOLDERS);
    assert.strictEqual(SE.score(LINKS[0], SE.parseQuery('react -vietnam'), idx), 0);
    assert.strictEqual(SE.score(LINKS[0], SE.parseQuery('fav:false'), idx), 0);
    assert.strictEqual(SE.score(LINKS[2], SE.parseQuery('pinned:true'), idx), 0);
    assert.strictEqual(SE.score(LINKS[2], SE.parseQuery('visits:>5'), idx), 0);
    assert.strictEqual(SE.score(LINKS[1], SE.parseQuery('visits:>5'), idx), 0);
});

test('score: date range filters', () => {
    const idx = makeIndex(LINKS, FOLDERS);
    assert.ok(SE.score(LINKS[0], SE.parseQuery('from:2024-01-01'), idx) > 0);
    assert.strictEqual(SE.score(LINKS[1], SE.parseQuery('from:2024-01-01'), idx), 0);
});

test('score: relevance ordering — title beats tag beats notes, pinned/fav boost', () => {
    const titleLink = { id: 't1', title: 'React Tutorial', url: 'https://a.com', tags: ['react'], category: 'Dev' };
    const tagLink = { id: 't2', title: 'Something Else', url: 'https://b.com', tags: ['react'], category: 'Dev' };
    const boostedTagLink = { id: 't3', title: 'Something Else', url: 'https://c.com', tags: ['react'], category: 'Dev', pinned: true, favorite: true };
    const notesLink = { id: 't4', title: 'Something Else', url: 'https://d.com', notes: 'react tips', tags: [], category: 'Dev' };
    const idx = makeIndex([titleLink, tagLink, boostedTagLink, notesLink], []);
    const q = SE.parseQuery('react');
    const sTitle = SE.score(titleLink, q, idx);   // 50 (title hit)
    const sTag = SE.score(tagLink, q, idx);       // 30 (tag hit)
    const sBoost = SE.score(boostedTagLink, q, idx); // 30 + 3 + 2
    const sNotes = SE.score(notesLink, q, idx);   // 5 (notes hit)
    assert.strictEqual(sTitle, 50);
    assert.strictEqual(sTag, 30);
    assert.strictEqual(sBoost, 35);
    assert.strictEqual(sNotes, 5);
    assert.ok(sTitle > sTag && sTag > sNotes);
});

test('score: folder: operator uses folder names', () => {
    const idx = makeIndex(LINKS, FOLDERS);
    const q = SE.parseQuery('folder:Công việc');
    assert.ok(SE.score(LINKS[0], q, idx) > 0);
    assert.strictEqual(SE.score(LINKS[1], q, idx), 0);
});

test('highlight wraps accents correctly for accent-less query', () => {
    const out = SE.highlight('Cà phê và lập trình', ['ca phe'], esc);
    assert.ok(out.includes('<mark class="search-hit">Cà phê</mark>'), out);
});

test('highlight escapes HTML and merges overlapping terms', () => {
    const out = SE.highlight('<b>React</b>', ['react', 'react docs'], esc);
    assert.ok(out.includes('&lt;b&gt;'));
    const out2 = SE.highlight('react router', ['react', 'react router'], esc);
    assert.strictEqual(out2.match(/<mark/g).length, 1, 'ranges must merge');
});

test('highlight returns escaped text when no terms match', () => {
    assert.strictEqual(SE.highlight('<b>X</b>', ['zzz'], esc), '&lt;b&gt;X&lt;/b&gt;');
    assert.strictEqual(SE.highlight('plain', [], esc), 'plain');
});

test('buildIndex handles empty / malformed data', () => {
    assert.strictEqual(makeIndex([], []).size, 0);
    const idx = makeIndex([{ id: 'x', title: 'no url' }], null);
    assert.strictEqual(idx.get('x').domain, '');
});

test('score with no query words still applies filters', () => {
    const idx = makeIndex(LINKS, FOLDERS);
    assert.ok(SE.score(LINKS[0], SE.parseQuery('pinned:true'), idx) > 0);
    assert.strictEqual(SE.score(LINKS[2], SE.parseQuery('pinned:true'), idx), 0);
});

test('filter-only queries include every matching link (baseline score)', () => {
    const idx = makeIndex(LINKS, FOLDERS);
    // tag:react must include BOTH react links (even without keyword/boost hits)
    const q = SE.parseQuery('tag:react');
    const matched = LINKS.filter(l => SE.score(l, q, idx) > 0);
    assert.deepStrictEqual(matched.map(l => l.id).sort(), ['1', '2']);
    // visits:>5 only Cà phê (10 visits)
    const qv = SE.parseQuery('visits:>5');
    const mv = LINKS.filter(l => SE.score(l, qv, idx) > 0);
    assert.deepStrictEqual(mv.map(l => l.id), ['1']);
    // -design excludes only the design link
    const qx = SE.parseQuery('-design');
    const mx = LINKS.filter(l => SE.score(l, qx, idx) > 0);
    assert.deepStrictEqual(mx.map(l => l.id).sort(), ['1', '2']);
});
