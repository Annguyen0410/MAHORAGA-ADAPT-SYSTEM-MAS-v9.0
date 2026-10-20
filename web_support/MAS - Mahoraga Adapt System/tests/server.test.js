const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-http-test-'));
process.env.MAS_LOAD_ENV = '0'; process.env.GEMINI_API_KEY = '';
process.env.MAS_DATA_FILE = path.join(directory, 'sessions.json');
const store = require('../server/sessionStore');
const app = require('../server/server');
const server = app.listen(0, '127.0.0.1', async () => {
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (url, method = 'GET', body, extra = {}) => fetch(base + url, { method,
    headers: { 'Content-Type': 'application/json', ...extra }, body: body === undefined ? undefined : JSON.stringify(body) });
  try {
    assert.equal((await request('/api/health')).status, 200);
    assert.equal((await request('/api/sessions', 'POST', { target: 'Injected' }, { Origin: 'https://attacker.example' })).status, 403);
    assert.equal((await (await request('/api/sessions')).json()).length, 0);
    const first = await (await request('/api/sessions', 'POST', { target: 'Guitar' })).json();
    const second = await (await request('/api/sessions', 'POST', { target: 'Guitar' })).json();
    assert.notEqual(first.id, second.id);
    assert.equal((await request('/api/sessions/__proto__')).status, 404);
    const edited = await (await request('/api/sessions/' + first.id, 'PUT', { goal: 'Practice daily', serverId: 'attack' })).json();
    assert.equal(edited.goal, 'Practice daily'); assert.equal(edited.serverId, undefined);
    for (const file of ['/chain.js', '/chain.json']) assert.equal((await request(file)).status, 200);
    for (const file of ['/server/.env', '/server/sessions.json', '/package.json']) assert.equal((await request(file)).status, 404);
    assert.equal((await fetch(base + '/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{broken' })).status, 400);
    assert.equal((await request('/api/sessions/' + first.id, 'DELETE')).status, 200);
    assert.equal(Object.keys(store.loadSessions(process.env.MAS_DATA_FILE)).length, 1);
    const corrupt = path.join(directory, 'corrupt.json'); fs.writeFileSync(corrupt, '{broken');
    assert.throws(() => store.loadSessions(corrupt)); assert.equal(fs.readFileSync(corrupt, 'utf8'), '{broken');
    const before = fs.readFileSync(process.env.MAS_DATA_FILE, 'utf8');
    const circular = {}; circular.self = circular;
    assert.throws(() => store.saveSessions(process.env.MAS_DATA_FILE, circular));
    assert.equal(fs.readFileSync(process.env.MAS_DATA_FILE, 'utf8'), before);
    console.log('  server: CRUD, origins, unique IDs, private assets, corrupt stores and atomic writes OK');
  } catch (error) { console.error(error); process.exitCode = 1; }
  finally { server.closeAllConnections(); server.close(() => fs.rmSync(directory, { recursive: true, force: true })); }
});
