const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');

function loadSessions(filename) {
  let raw;
  try { raw = fs.readFileSync(filename, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') return Object.create(null); throw error; }
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid session store');
  const result = Object.create(null);
  for (const [id, session] of Object.entries(parsed)) {
    if (!/^[a-zA-Z0-9_-]+$/.test(id) || !session || typeof session !== 'object' || Array.isArray(session)) throw new Error('Invalid stored session');
    result[id] = session;
  }
  return result;
}
function saveSessions(filename, sessions) {
  // Serialize before touching disk: even serialization failure preserves bytes.
  const content = JSON.stringify(sessions, null, 2);
  const temporary = path.join(path.dirname(filename), '.' + path.basename(filename) + '.' + randomUUID() + '.tmp');
  let fd;
  try {
    fd = fs.openSync(temporary, 'wx', 0o600);
    fs.writeFileSync(fd, content, 'utf8');
    fs.fsyncSync(fd);
    fs.closeSync(fd); fd = undefined;
    fs.renameSync(temporary, filename);
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') console.warn('Temporary store cleanup failed'); }
  }
}
module.exports = { loadSessions, saveSessions };
