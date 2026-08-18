require("dotenv").config({ path: __dirname + "/.env" });
const express = require("express");
const cors = require("cors");
const rateLimit = require("express-rate-limit");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const fs = require("fs");
const path = require("path");
const { runDeepAnalysis } = require("./deepAnalysis");
const budget = require("./geminiBudget");
const modelBudget = require("./modelBudget");
const { cleanSessionInput } = require("./validate");

const PORT = process.env.PORT || 3001;
// Render always injects PORT, so a PORT-bearing environment (any deploy)
// binds all interfaces automatically. Local dev keeps the loopback-only
// default for safety. The .split() tolerates sloppy values like
// "0.0.0.0, 127.0.0.1" (first entry wins) instead of crashing the boot.
const HOST = (process.env.HOST || (process.env.PORT ? "0.0.0.0" : "127.0.0.1"))
  .split(/[,\s]+/)[0]
  .trim();
const DATA_FILE = process.env.DATA_FILE || path.join(__dirname, "sessions.json");
const AI_WINDOW_MS = parseInt(process.env.AI_RATE_LIMIT_WINDOW_MS || "3600000");
const AI_MAX_CALLS = parseInt(process.env.AI_RATE_LIMIT_MAX || "20");

// Deep-analysis requests are gated by the REAL Gemini budget, not this limiter.
// Cache hits and batch mode should never be blocked by request counting.
const deepLimiter = rateLimit({
  windowMs: AI_WINDOW_MS,
  max: parseInt(process.env.AI_REQUEST_LIMIT_MAX || "120", 10),
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    res.status(429).json({
      error: "Deep analysis rate limit exceeded",
      rateLimit: {
        limit: parseInt(process.env.AI_REQUEST_LIMIT_MAX || "120", 10),
        remaining: 0,
        resetAt: new Date(req.rateLimit.resetTime).toISOString(),
        retryAfterSeconds: Math.ceil((req.rateLimit.resetTime - Date.now()) / 1000)
      }
    });
  }
});

function getGenAI() {
  const key = process.env.GEMINI_API_KEY;
  if (!key || key.length < 20 || key.includes("YOUR_GEMINI_API_KEY")) throw new Error("GEMINI_API_KEY not configured");
  return new GoogleGenerativeAI(key);
}

const app = express();

// CORS: allow only the app itself (same origin), loopback origins, and
// file:// pages (origin "null"). Arbitrary websites can neither read nor
// preflight-mutate this local API.
const ALLOWED_ORIGINS = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/;
app.use(cors({
  origin: (origin, cb) => {
    if (!origin || origin === "null" || ALLOWED_ORIGINS.test(origin)) return cb(null, true);
    return cb(null, false);
  }
}));

// Security headers. The CSP keeps scripts/styles to self (inline style
// attributes are required by the UI; no inline scripts or eval exist).
app.use((req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
  );
  if (req.path.startsWith("/api/")) res.setHeader("Cache-Control", "no-store");
  next();
});

app.use(express.json({ limit: "2mb" }));

const PROJECT_ROOT = path.resolve(__dirname, "..");
// Serve ONLY the public frontend assets. server/, node_modules/, tests/ and
// package files must never be reachable over HTTP.
const INDEX_FILE = path.join(PROJECT_ROOT, "index.html");
app.get(["/", "/index.html"], (req, res) => res.sendFile(INDEX_FILE));
app.use("/style.css", express.static(path.join(PROJECT_ROOT, "style.css")));
app.use("/js", express.static(path.join(PROJECT_ROOT, "js"), { dotfiles: "ignore" }));
app.use("/assets", express.static(path.join(PROJECT_ROOT, "assets"), { dotfiles: "ignore" }));
for (const dir of ["core", "analysis", "mythos", "case_studies"]) {
  app.use(`/${dir}`, express.static(path.join(PROJECT_ROOT, dir), { dotfiles: "ignore" }));
}

let sessions = {};
if (fs.existsSync(DATA_FILE)) {
  try { sessions = JSON.parse(fs.readFileSync(DATA_FILE, "utf-8")); } catch { sessions = {}; }
}

function saveSessions() {
  fs.writeFileSync(DATA_FILE, JSON.stringify(sessions, null, 2));
}

const aiLimiter = rateLimit({
  windowMs: AI_WINDOW_MS,
  max: AI_MAX_CALLS,
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    res.status(429).json({
      error: "AI rate limit exceeded",
      rateLimit: {
        limit: AI_MAX_CALLS,
        remaining: 0,
        resetAt: new Date(req.rateLimit.resetTime).toISOString(),
        retryAfterSeconds: Math.ceil((req.rateLimit.resetTime - Date.now()) / 1000)
      }
    });
  }
});

// One Gemini call, guarded by the per-model quota (RPM/TPM/RPD).
// If the preferred model is exhausted, the priority list in modelBudget
// is tried; if EVERY model is exhausted we throw without calling the API
// (quotaExhausted) so the user is never billed for an over-quota request.
async function callGoogleAI(systemPrompt, userContent, preferredModel) {
  const genAI = getGenAI(); // throws early if the key is missing — before reserving quota
  // Try up to a few models: quota-exhausted ones are skipped by the guard,
  // and a model that errors out (bad ID / not supported) is marked blocked
  // and we fall through to the next one instead of failing the request.
  for (let attempt = 0; attempt < 4; attempt++) {
    const estTokens = modelBudget.estimateTokens(systemPrompt) + modelBudget.estimateTokens(userContent);
    const modelId = modelBudget.acquire([preferredModel || process.env.GEMINI_MODEL], estTokens);
    if (!modelId) {
      const err = new Error("All Gemini models are at their free-tier quota (RPM/TPM/RPD). No AI call was made — try again later.");
      err.quotaExhausted = true;
      throw err;
    }
    try {
      const model = genAI.getGenerativeModel({ model: modelId, systemInstruction: systemPrompt });
      const result = await model.generateContent(userContent);
      budget.record(1);
      modelBudget.recordTokens(modelId, result.response.usageMetadata?.totalTokenCount || estTokens);
      return result.response.text();
    } catch (err) {
      const msg = String(err.message);
      if (/429|RESOURCE_EXHAUSTED|Quota exceeded/i.test(msg)) {
        modelBudget.markBlocked(modelId);
        throw err; // quota: surface the 429, don't burn other models
      }
      if (/model.*(not found|not supported|doesn't exist|does not exist)|invalid.*model/i.test(msg)) {
        modelBudget.markBlocked(modelId);
        continue; // bad model: self-heal by trying the next one
      }
      throw err;
    }
  }
  const err = new Error("No Gemini model could complete the request.");
  err.quotaExhausted = true;
  throw err;
}

app.get("/api/health", (req, res) => {
  const key = process.env.GEMINI_API_KEY || "";
  const keyOk = !!(key && key.length > 20 && !key.includes("YOUR_GEMINI_API_KEY"));
  res.json({
    status: "ok",
    version: "9.0.0",
    aiConfigured: keyOk,
    aiModel: process.env.GEMINI_MODEL || modelBudget.PRIORITY[0] || "gemini-3.5-flash-lite",
    provider: "google/gemini",
    deepAnalysisAvailable: keyOk,
    uptime: process.uptime()
  });
});

app.get("/api/rate-limit", (req, res) => {
  const s = budget.status();
  res.json({
    limit: s.limit,
    windowMs: s.windowMs,
    windowSeconds: s.windowSeconds,
    description: `${s.limit} real AI calls per ${Math.floor(s.windowMs / 60000)} minutes`,
    hits: s.hits,
    remaining: s.remaining,
    resetAt: s.resetAt
  });
});

// Per-model free-tier quota status (RPM / TPM / RPD) — what modelBudget
// enforces before every Gemini call, and which models still have room.
app.get("/api/models", (req, res) => {
  res.json(modelBudget.status());
});

app.get("/api/sessions", (req, res) => {
  res.json(Object.values(sessions).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)));
});

app.post("/api/sessions", (req, res) => {
  const input = cleanSessionInput(req.body);
  if (!input.target) return res.status(400).json({ error: "Target is required" });
  const { target, domain, goal, baseline, humanCapture } = input;
  const id = `${Date.now()}-${target.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const session = {
    id, target, domain: domain || "object", goal: goal || "",
    baseline: {
      skillLevel: baseline?.skillLevel || "",
      historicalPatterns: baseline?.historicalPatterns || "",
      previousAttempts: baseline?.previousAttempts || ""
    },
    createdAt: new Date().toISOString(),
    humanCapture: humanCapture || {
      observedProperties: "", evaluation: "", description: "",
      testPerformed: "", testResult: "", environment: "",
      measuredSignals: "", failureType: "perception"
    },
    aiAssessment: null, roadmap: "", deepAnalysis: null, turns: []
  };
  sessions[id] = session;
  saveSessions();
  res.status(201).json(session);
});

app.get("/api/sessions/:id", (req, res) => {
  const session = sessions[req.params.id];
  if (!session) return res.status(404).json({ error: "Session not found" });
  res.json(session);
});

app.put("/api/sessions/:id", (req, res) => {
  const session = sessions[req.params.id];
  if (!session) return res.status(404).json({ error: "Session not found" });
  // Whitelist: clients may only touch these fields; anything else (ids,
  // caches, internal state) is rejected instead of blindly assigned.
  const input = cleanSessionInput(req.body);
  for (const field of ["target", "domain", "goal", "baseline", "humanCapture"]) {
    if (input[field] !== undefined) session[field] = input[field];
  }
  saveSessions();
  res.json(session);
});

app.delete("/api/sessions/:id", (req, res) => {
  if (!sessions[req.params.id]) return res.status(404).json({ error: "Session not found" });
  delete sessions[req.params.id];
  saveSessions();
  res.json({ ok: true });
});

app.post("/api/sessions/:id/assessment", aiLimiter, async (req, res) => {
  const session = sessions[req.params.id];
  if (!session) return res.status(404).json({ error: "Session not found" });
  const c = session.humanCapture;
  const hasData = c.observedProperties || c.evaluation || c.description || c.testPerformed || c.testResult;
  if (!hasData) return res.status(400).json({ error: "Human capture data is required" });

  try {
    const systemPrompt = `You are the AI Assessment engine of the Mahoraga Adapt System (MAS). Analyze the human's operational capture data and produce a structured assessment in EXACTLY this JSON format (no markdown, no code fences — pure JSON only):

{
  "material": "string - assessment of material/structure properties based on capture data",
  "durability": "string - durability analysis and risk assessment",
  "frequency": "string - vibration, rhythm, timing, or frequency signal analysis",
  "variables": ["string - control variable 1", "string - control variable 2", ...],
  "risks": ["string - risk 1", "string - risk 2", ...],
  "uncertainty": ["string - uncertainty flag 1", ...],
  "detailedGuidance": "string - 3-5 sentences of practical guidance for the user's next steps"
}

Rules:
- Be concrete and practical. Never generic.
- If data is sparse, note uncertainty honestly.
- Suggest 4-6 control variables the user should isolate and test.
- Match the domain: object/environment/concept/social/tool.`;

    const userContent = `Target: ${session.target}\nDomain: ${session.domain}\nGoal: ${session.goal}\n\nCapture Data:\nProperties: ${c.observedProperties || "(none)"}\nEvaluation: ${c.evaluation || "(none)"}\nDescription: ${c.description || "(none)"}\nTest: ${c.testPerformed || "(none)"}\nResult: ${c.testResult || "(none)"}\nContext: ${c.environment || "(none)"}\nSignals: ${c.measuredSignals || "(none)"}\nFailure Type: ${c.failureType || "(none)"}`;

    const raw = await callGoogleAI(systemPrompt, userContent, process.env.GEMINI_ASSESSMENT_MODEL || process.env.GEMINI_MODEL);
    const cleaned = raw.replace(/```json|```/g, "").trim();
    const jsonStart = cleaned.indexOf("{");
    const jsonEnd = cleaned.lastIndexOf("}") + 1;
    const assessment = JSON.parse(cleaned.slice(jsonStart, jsonEnd));
    session.aiAssessment = assessment;
    saveSessions();
    res.json({
      assessment,
      rateLimit: budget.status()
    });
  } catch (err) {
    if (err.quotaExhausted) {
      return res.status(429).json({ error: err.message, budget: modelBudget.status() });
    }
    if (err.message.includes("GEMINI_API_KEY not configured")) {
      return res.status(503).json({ error: err.message, fallbackAvailable: true });
    }
    res.status(502).json({ error: `AI call failed: ${err.message}` });
  }
});

app.post("/api/sessions/:id/roadmap", aiLimiter, async (req, res) => {
  const session = sessions[req.params.id];
  if (!session) return res.status(404).json({ error: "Session not found" });

  try {
    const assessment = session.aiAssessment || { material: "unknown", durability: "unknown", frequency: "unknown", variables: ["attention"], risks: [], uncertainty: ["Limited data"] };
    const c = session.humanCapture;

    const adaptation = req.body.adaptation || null;
    const adaptLine = adaptation
      ? `Phase=${adaptation.phase || "first-hit"}, Trend=${adaptation.trend || "unknown"}, SpinCount=${adaptation.spinCount || 0}, TransferPassed=${adaptation.transferPassed || 0}`
      : "Phase=first-hit, Trend=unknown, SpinCount=0";
    const nextStep = adaptation?.nextStep || "Run a baseline test and log the first check-in.";

    const systemPrompt = "You are the Roadmap Generator for the Mahoraga Adapt System (MAS). Generate a practical 9-step adaptation roadmap based on the user's target, capture, AI assessment, and their CURRENT ADAPTIVE STATE. Use the Mahoraga metaphor (First Hit → Wheel Spin → Immunity) as the narrative frame. The roadmap must OPEN with a line `[ADAPTIVE STATE] <phase> — <trend> (spin <count>)` and a line `NEXT SPIN: <the exact next action for the user's current phase>`. Then adapt the 9 steps to the phase: a user who is refining needs a variable-change step first; a user who is stuck needs a baseline-return step; a user transferring needs a context-change drill. Be specific, actionable, and safety-aware. Return ONLY the roadmap text — no JSON, no markdown formatting.";

    const userContent = `Target: ${session.target}
Domain: ${session.domain}
Goal: ${session.goal || "(not specified)"}
Skill Level: ${session.baseline?.skillLevel || "unknown"}/10
Historical Patterns: ${session.baseline?.historicalPatterns || "(none)"}
Previous Attempts: ${session.baseline?.previousAttempts || "(none)"}

Capture: Properties=${c.observedProperties || "(none)"}, Evaluation=${c.evaluation || "(none)"}, Description=${c.description || "(none)"}, Test=${c.testPerformed || "(none)"}, Result=${c.testResult || "(none)"}, Context=${c.environment || "(none)"}, Signals=${c.measuredSignals || "(none)"}, Failure=${c.failureType || "(none)"}

Assessment: Material=${assessment.material}, Durability=${assessment.durability}, Frequency=${assessment.frequency}, Variables=${assessment.variables?.join(", ") || "unknown"}, Risks=${assessment.risks?.join("; ") || "unknown"}

ADAPTIVE STATE: ${adaptLine}
Suggested NEXT SPIN from the engine: ${nextStep}

Generate a 9-step roadmap adapted to this phase: 1) Baseline calibration, 2) First drill, 3) Measurement target, 4) Property-aware adjustment, 5) Constraint check, 6) Refinement loop, 7) Transfer test, 8) Template candidate, 9) Embodiment validation.`;

    const roadmap = await callGoogleAI(systemPrompt, userContent, process.env.GEMINI_ROADMAP_MODEL || process.env.GEMINI_MODEL);
    session.roadmap = roadmap;
    saveSessions();
    res.json({
      roadmap,
      rateLimit: budget.status()
    });
  } catch (err) {
    if (err.quotaExhausted) {
      return res.status(429).json({ error: err.message, budget: modelBudget.status() });
    }
    if (err.message.includes("GEMINI_API_KEY not configured")) {
      return res.status(503).json({ error: err.message, fallbackAvailable: true });
    }
    res.status(502).json({ error: `AI call failed: ${err.message}` });
  }
});

app.post("/api/sessions/:id/deep-analysis", deepLimiter, async (req, res) => {
  const session = sessions[req.params.id];
  if (!session) return res.status(404).json({ error: "Session not found" });

  const key = process.env.GEMINI_API_KEY || "";
  if (!key || key.length < 20 || key.includes("YOUR_GEMINI_API_KEY")) {
    return res.status(503).json({ error: "GEMINI_API_KEY is not configured in server/.env" });
  }

  try {
    const remaining = budget.status().remaining;
    let mode = req.body.mode || "auto";
    if (mode === "auto") {
      // Full independent run costs ~10 calls; batch costs ~2-3.
      mode = remaining >= 12 ? "full" : "batch";
    }
    if (mode === "full" && remaining < 12) {
      mode = "batch"; // degrade gracefully instead of failing
    }

    const result = await runDeepAnalysis(session, {
      apiKey: process.env.GEMINI_API_KEY,
      modelName: process.env.GEMINI_MODEL,
      synthesisModel: process.env.GEMINI_SYNTHESIS_MODEL || process.env.GEMINI_MODEL,
      mode,
      cache: session.deepAnalysisCache || (session.deepAnalysisCache = {})
    });

    session.deepAnalysis = {
      perspectives: result.perspectives,
      synthesis: result.synthesis,
      modeUsed: result.modeUsed,
      cached: result.cached,
      hash: result.hash
    };
    saveSessions();
    res.json({
      ...result,
      rateLimit: budget.status()
    });
  } catch (err) {
    if (err.quotaExhausted) {
      return res.status(429).json({ error: err.message, budget: modelBudget.status() });
    }
    res.status(502).json({ error: `Deep analysis failed: ${err.message}` });
  }
});

// JSON body errors must not leak stack traces or absolute paths to clients.
// body-parser normally renders an HTML error page with the full stack.
app.use((err, req, res, next) => {
  if (err.type === "entity.parse.failed") {
    return res.status(400).json({ error: "Invalid JSON body" });
  }
  if (err.type === "entity.too.large") {
    return res.status(413).json({ error: "Request body too large" });
  }
  if (err.type === "encoding.unsupported") {
    return res.status(415).json({ error: "Unsupported content encoding" });
  }
  res.status(500).json({ error: "Internal server error" });
});

app.listen(PORT, HOST, () => {
  const keyOk = !!(process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY.length > 20);
  console.log(`\n  MAS API Server v9.0`);
  console.log(`  Server:   http://localhost:${PORT}`);
  console.log(`  AI:       ${process.env.GEMINI_MODEL || "gemini-2.0-flash"}`);
  console.log(`  Limit:    ${AI_MAX_CALLS} calls per ${AI_WINDOW_MS / 60000}min`);
  console.log(`  AI Status:${keyOk ? "ready" : "NOT configured — set GEMINI_API_KEY in .env"}`);
  console.log(`  Sessions: ${Object.keys(sessions).length} stored\n`);
});
