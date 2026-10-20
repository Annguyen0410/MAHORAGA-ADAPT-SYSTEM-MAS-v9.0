if (process.env.MAS_LOAD_ENV !== '0') require('dotenv').config({ path: __dirname + '/.env' });
const express = require('express');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const path = require('path');
const { randomUUID } = require('crypto');
const { runDeepAnalysis } = require('./deepAnalysis');
const budget = require('./geminiBudget');
const { cleanSessionInput } = require('./validate');
const store = require('./sessionStore');
const PORT = process.env.PORT || 3001;
const HOST = process.env.HOST || '127.0.0.1';
const DATA_FILE = process.env.MAS_DATA_FILE || path.join(__dirname, 'sessions.json');
const positiveInt = (value, fallback) => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : fallback;
const AI_WINDOW_MS = positiveInt(process.env.AI_RATE_LIMIT_WINDOW_MS, 3600000);
const AI_MAX_CALLS = positiveInt(process.env.AI_RATE_LIMIT_MAX, 20);
const app = express();
const LOOPBACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/;
function allowedOrigin(origin, req) {
  if (!origin || origin === 'null' || LOOPBACK.test(origin)) return true;
  // Deployment origins must match the actual request host, not merely a CORS header.
  return origin === `${req.protocol}://${req.get('host')}`;
}
app.use((req, res, next) => {
  if (!allowedOrigin(req.get('origin'), req) || req.get('sec-fetch-site') === 'cross-site' && !req.get('origin'))
    return res.status(403).json({ error: 'Origin not allowed' });
  next();
});
app.use(cors({ origin: true }));
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'");
  if (req.path.startsWith('/api/')) res.setHeader('Cache-Control', 'no-store');
  next();
});
app.use(express.json({ limit: '2mb' }));
const PROJECT_ROOT = path.resolve(__dirname, '..');
app.get(['/', '/index.html'], (req, res) => res.sendFile(path.join(PROJECT_ROOT, 'index.html')));
for (const file of ['style.css', 'chain.js', 'chain.json']) app.get('/' + file, (req, res) => res.sendFile(path.join(PROJECT_ROOT, file)));
for (const dir of ['js', 'assets', 'core', 'analysis', 'mythos', 'case_studies'])
  app.use('/' + dir, express.static(path.join(PROJECT_ROOT, dir), { dotfiles: 'ignore' }));

let sessions;
try { sessions = store.loadSessions(DATA_FILE); }
catch { throw new Error('Session store is unreadable or corrupt; original file retained. Restore it before starting MAS.'); }
let committed = JSON.stringify(sessions);
function saveSessions() {
  try {
    store.saveSessions(DATA_FILE, sessions);
    committed = JSON.stringify(sessions);
  } catch (cause) {
    sessions = Object.assign(Object.create(null), JSON.parse(committed));
    const error = new Error('Session could not be saved; previous data retained');
    error.status = 503; error.cause = cause; throw error;
  }
}
function limiter(max, message) {
  return rateLimit({ windowMs: AI_WINDOW_MS, max, standardHeaders: true, legacyHeaders: false,
    handler: (req, res) => res.status(429).json({ error: message,
      rateLimit: { limit: max, remaining: 0, resetAt: new Date(req.rateLimit.resetTime).toISOString(),
        retryAfterSeconds: Math.ceil((req.rateLimit.resetTime - Date.now()) / 1000) } }) });
}
const aiLimiter = limiter(AI_MAX_CALLS, 'AI rate limit exceeded');
const deepLimiter = limiter(positiveInt(process.env.AI_REQUEST_LIMIT_MAX, 120), 'Deep analysis rate limit exceeded');
function keyConfigured() {
  const key = process.env.GEMINI_API_KEY || '';
  return key.length > 20 && !key.includes('YOUR_GEMINI_API_KEY');
}
async function callGoogleAI(systemPrompt, userContent, modelName) {
  if (!keyConfigured()) throw new Error('GEMINI_API_KEY not configured');
  const model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
    model: modelName || process.env.GEMINI_MODEL || 'gemini-flash-latest', systemInstruction: systemPrompt });
  const result = await model.generateContent(userContent);
  budget.record(1); return result.response.text();
}
const sessionFor = (req, res) => {
  const session = sessions[req.params.id];
  if (!session) res.status(404).json({ error: 'Session not found' });
  return session;
};
const asyncRoute = handler => (req, res, next) => Promise.resolve(handler(req, res)).catch(next);
function aiError(res, error, prefix) {
  if (error.status) return res.status(error.status).json({ error: error.message });
  if (error.message.includes('GEMINI_API_KEY not configured')) return res.status(503).json({ error: error.message, fallbackAvailable: true });
  console.warn(prefix, error.message);
  return res.status(502).json({ error: prefix + '; retry or use local assessment' });
}
app.get('/api/health', (req, res) => res.json({ status: 'ok', version: '9.0.0', aiConfigured: keyConfigured(),
  aiModel: process.env.GEMINI_MODEL || 'gemini-flash-latest', provider: 'google/gemini', deepAnalysisAvailable: keyConfigured(), uptime: process.uptime() }));
app.get('/api/rate-limit', (req, res) => {
  const status = budget.status();
  res.json({ ...status, description: `${status.limit} real AI calls per ${Math.floor(status.windowMs / 60000)} minutes` });
});
app.get('/api/sessions', (req, res) => res.json(Object.values(sessions).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))));
app.post('/api/sessions', (req, res) => {
  const input = cleanSessionInput(req.body);
  if (!input.target) return res.status(400).json({ error: 'Target is required' });
  const id = randomUUID();
  const session = { id, target: input.target, domain: input.domain || 'object', goal: input.goal || '',
    baseline: { skillLevel: '', historicalPatterns: '', previousAttempts: '', ...input.baseline },
    createdAt: new Date().toISOString(),
    humanCapture: { observedProperties: '', evaluation: '', description: '', testPerformed: '', testResult: '', environment: '', measuredSignals: '', failureType: 'perception', ...input.humanCapture },
    aiAssessment: null, roadmap: '', deepAnalysis: null, turns: [] };
  sessions[id] = session; saveSessions(); res.status(201).json(session);
});
app.get('/api/sessions/:id', (req, res) => { const session = sessionFor(req, res); if (session) res.json(session); });
app.put('/api/sessions/:id', (req, res) => {
  const session = sessionFor(req, res); if (!session) return;
  const input = cleanSessionInput(req.body);
  for (const field of ['target', 'domain', 'goal', 'baseline', 'humanCapture']) if (input[field] !== undefined) session[field] = input[field];
  saveSessions(); res.json(session);
});
app.delete('/api/sessions/:id', (req, res) => {
  if (!sessionFor(req, res)) return;
  delete sessions[req.params.id]; saveSessions(); res.json({ ok: true });
});
app.post('/api/sessions/:id/assessment', aiLimiter, asyncRoute(async (req, res) => {
  const session = sessionFor(req, res); if (!session) return;
  const capture = session.humanCapture || {};
  if (!['observedProperties', 'evaluation', 'description', 'testPerformed', 'testResult'].some(key => capture[key]))
    return res.status(400).json({ error: 'Human capture data is required' });
  try {
    const raw = await callGoogleAI(
      'You are the AI Assessment engine of the Mahoraga Adapt System. Analyze the operational capture concretely, practically and safety-aware. Return pure JSON with string fields material, durability, frequency, detailedGuidance and arrays of strings variables, risks, uncertainty. Suggest 4-6 control variables. Flag sparse evidence honestly. Match the target domain.',
      JSON.stringify({ target: session.target, domain: session.domain, goal: session.goal, capture }),
      process.env.GEMINI_ASSESSMENT_MODEL || process.env.GEMINI_MODEL);
    const cleaned = raw.replace(/```json|```/g, '').trim();
    const assessment = JSON.parse(cleaned.slice(cleaned.indexOf('{'), cleaned.lastIndexOf('}') + 1));
    if (!assessment || typeof assessment !== 'object' || Array.isArray(assessment)) throw new Error('Invalid assessment');
    for (const field of ['material', 'durability', 'frequency', 'detailedGuidance']) if (typeof assessment[field] !== 'string') assessment[field] = '';
    for (const field of ['variables', 'risks', 'uncertainty']) assessment[field] = Array.isArray(assessment[field]) ? assessment[field].filter(item => typeof item === 'string') : [];
    // A deleted session must not be resurrected by a late AI response.
    if (sessions[session.id] !== session) return res.status(409).json({ error: 'Session changed while analysis was running' });
    session.aiAssessment = assessment; saveSessions(); res.json({ assessment, rateLimit: budget.status() });
  } catch (error) { aiError(res, error, 'AI call failed'); }
}));
app.post('/api/sessions/:id/roadmap', aiLimiter, asyncRoute(async (req, res) => {
  const session = sessionFor(req, res); if (!session) return;
  try {
    const roadmap = await callGoogleAI(
      "You are the Roadmap Generator for MAS. Generate a practical safety-aware 9-step adaptation roadmap. Use First Hit → Wheel Spin → Immunity. Open with [ADAPTIVE STATE] <phase> — <trend> (spin <count>) and NEXT SPIN: <exact next action>. Adapt to the current phase: refining starts with variable change; stuck returns to baseline; transferring uses a context-change drill. Cover baseline calibration, first drill, measurement, property-aware adjustment, constraints, refinement, transfer, template candidate, embodiment validation. Return text only, no JSON or markdown.",
      JSON.stringify({ target: session.target, domain: session.domain, goal: session.goal, baseline: session.baseline,
        capture: session.humanCapture, assessment: session.aiAssessment, adaptation: req.body?.adaptation || null }),
      process.env.GEMINI_ROADMAP_MODEL || process.env.GEMINI_MODEL);
    if (sessions[session.id] !== session) return res.status(409).json({ error: 'Session changed while analysis was running' });
    session.roadmap = roadmap; saveSessions(); res.json({ roadmap, rateLimit: budget.status() });
  } catch (error) { aiError(res, error, 'AI call failed'); }
}));
app.post('/api/sessions/:id/deep-analysis', deepLimiter, asyncRoute(async (req, res) => {
  const session = sessionFor(req, res); if (!session) return;
  if (!keyConfigured()) return res.status(503).json({ error: 'GEMINI_API_KEY not configured', fallbackAvailable: true });
  try {
    const remaining = budget.status().remaining;
    let mode = req.body?.mode || 'auto';
    if (!['auto', 'full', 'batch'].includes(mode)) return res.status(400).json({ error: 'Invalid analysis mode' });
    if (mode === 'auto') mode = remaining >= 12 ? 'full' : 'batch';
    if (mode === 'full' && remaining < 12) mode = 'batch';
    const result = await runDeepAnalysis(session, { apiKey: process.env.GEMINI_API_KEY,
      modelName: process.env.GEMINI_MODEL || 'gemini-flash-latest',
      synthesisModel: process.env.GEMINI_SYNTHESIS_MODEL || process.env.GEMINI_MODEL || 'gemini-flash-latest', mode,
      cache: session.deepAnalysisCache || (session.deepAnalysisCache = {}) });
    if (sessions[session.id] !== session) return res.status(409).json({ error: 'Session changed while analysis was running' });
    session.deepAnalysis = { perspectives: result.perspectives, synthesis: result.synthesis, modeUsed: result.modeUsed, cached: result.cached, hash: result.hash };
    saveSessions(); res.json({ ...result, rateLimit: budget.status() });
  } catch (error) { aiError(res, error, 'Deep analysis failed'); }
}));
app.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  const errors = { 'entity.parse.failed': [400, 'Invalid JSON body'], 'entity.too.large': [413, 'Request body too large'], 'encoding.unsupported': [415, 'Unsupported content encoding'] };
  const [status, message] = errors[error.type] || [error.status || 500, error.status === 503 ? error.message : 'Internal server error'];
  res.status(status).json({ error: message });
});
if (require.main === module) app.listen(PORT, HOST, () => {
  console.log(`MAS API v9.0 on http://${HOST}:${PORT}; AI ${keyConfigured() ? 'ready' : 'not configured'}; ${Object.keys(sessions).length} sessions`);
});
module.exports = app;
