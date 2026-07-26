require("dotenv").config({ path: __dirname + "/.env" });
const express = require("express");
const cors = require("cors");
const rateLimit = require("express-rate-limit");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const fs = require("fs");
const path = require("path");
const { runDeepAnalysis } = require("./deepAnalysis");

const PORT = process.env.PORT || 3001;
const DATA_FILE = path.join(__dirname, "sessions.json");
const AI_WINDOW_MS = parseInt(process.env.AI_RATE_LIMIT_WINDOW_MS || "3600000");
const AI_MAX_CALLS = parseInt(process.env.AI_RATE_LIMIT_MAX || "20");

function getGenAI() {
  const key = process.env.GEMINI_API_KEY;
  if (!key || key.length < 20 || key.includes("YOUR_GEMINI_API_KEY")) throw new Error("GEMINI_API_KEY not configured");
  return new GoogleGenerativeAI(key);
}

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

const PROJECT_ROOT = path.resolve(__dirname, "..");
app.use(express.static(PROJECT_ROOT));

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

async function callGoogleAI(systemPrompt, userContent, modelName) {
  const genAI = getGenAI();
  const model = genAI.getGenerativeModel({
    model: modelName || process.env.GEMINI_MODEL || "gemini-flash-latest",
    systemInstruction: systemPrompt
  });
  const result = await model.generateContent(userContent);
  return result.response.text();
}

app.get("/api/health", (req, res) => {
  const key = process.env.GEMINI_API_KEY || "";
  const keyOk = !!(key && key.length > 20 && !key.includes("YOUR_GEMINI_API_KEY"));
  res.json({
    status: "ok",
    version: "8.5.0",
    aiConfigured: keyOk,
    aiModel: process.env.GEMINI_MODEL || "gemini-flash-latest",
    provider: "google/gemini",
    deepAnalysisAvailable: keyOk,
    uptime: process.uptime()
  });
});

app.get("/api/rate-limit", (req, res) => {
  res.json({
    limit: AI_MAX_CALLS,
    windowMs: AI_WINDOW_MS,
    windowSeconds: Math.floor(AI_WINDOW_MS / 1000),
    description: `${AI_MAX_CALLS} AI calls per ${Math.floor(AI_WINDOW_MS / 60000)} minutes`,
    hits: req.rateLimit?.current || 0,
    remaining: Math.max(0, AI_MAX_CALLS - (req.rateLimit?.current || 0)),
    resetAt: req.rateLimit?.resetTime ? new Date(req.rateLimit.resetTime).toISOString() : null
  });
});

app.get("/api/sessions", (req, res) => {
  res.json(Object.values(sessions).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)));
});

app.post("/api/sessions", (req, res) => {
  const { target, domain, goal, baseline } = req.body;
  if (!target) return res.status(400).json({ error: "Target is required" });
  const id = `${Date.now()}-${target.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const session = {
    id, target, domain: domain || "object", goal: goal || "",
    baseline: {
      skillLevel: baseline?.skillLevel || "",
      historicalPatterns: baseline?.historicalPatterns || "",
      previousAttempts: baseline?.previousAttempts || ""
    },
    createdAt: new Date().toISOString(),
    humanCapture: {
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
  Object.assign(session, req.body);
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

    const raw = await callGoogleAI(systemPrompt, userContent, process.env.GEMINI_ASSESSMENT_MODEL || process.env.GEMINI_MODEL || "gemini-flash-latest");
    const cleaned = raw.replace(/```json|```/g, "").trim();
    const jsonStart = cleaned.indexOf("{");
    const jsonEnd = cleaned.lastIndexOf("}") + 1;
    const assessment = JSON.parse(cleaned.slice(jsonStart, jsonEnd));
    session.aiAssessment = assessment;
    saveSessions();
    res.json({
      assessment,
      rateLimit: { remaining: Math.max(0, AI_MAX_CALLS - (req.rateLimit?.current || 0)) }
    });
  } catch (err) {
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

    const systemPrompt = "You are the Roadmap Generator for the Mahoraga Adapt System (MAS). Generate a practical 9-step adaptation roadmap based on the user's target, capture, and AI assessment. Use the Mahoraga metaphor (First Hit → Wheel Spin → Immunity) as the narrative frame. Be specific, actionable, and safety-aware. Return ONLY the roadmap text — no JSON, no markdown formatting.";

    const userContent = `Target: ${session.target}
Domain: ${session.domain}
Goal: ${session.goal || "(not specified)"}
Skill Level: ${session.baseline?.skillLevel || "unknown"}/10
Historical Patterns: ${session.baseline?.historicalPatterns || "(none)"}
Previous Attempts: ${session.baseline?.previousAttempts || "(none)"}

Capture: Properties=${c.observedProperties || "(none)"}, Evaluation=${c.evaluation || "(none)"}, Description=${c.description || "(none)"}, Test=${c.testPerformed || "(none)"}, Result=${c.testResult || "(none)"}, Context=${c.environment || "(none)"}, Signals=${c.measuredSignals || "(none)"}, Failure=${c.failureType || "(none)"}

Assessment: Material=${assessment.material}, Durability=${assessment.durability}, Frequency=${assessment.frequency}, Variables=${assessment.variables?.join(", ") || "unknown"}, Risks=${assessment.risks?.join("; ") || "unknown"}

Generate a 9-step roadmap: 1) Baseline calibration, 2) First drill, 3) Measurement target, 4) Property-aware adjustment, 5) Constraint check, 6) Refinement loop, 7) Transfer test, 8) Template candidate, 9) Embodiment validation.`;

    const roadmap = await callGoogleAI(systemPrompt, userContent, process.env.GEMINI_ROADMAP_MODEL || process.env.GEMINI_MODEL || "gemini-flash-latest");
    session.roadmap = roadmap;
    saveSessions();
    res.json({
      roadmap,
      rateLimit: { remaining: Math.max(0, AI_MAX_CALLS - (req.rateLimit?.current || 0)) }
    });
  } catch (err) {
    if (err.message.includes("GEMINI_API_KEY not configured")) {
      return res.status(503).json({ error: err.message, fallbackAvailable: true });
    }
    res.status(502).json({ error: `AI call failed: ${err.message}` });
  }
});

app.post("/api/sessions/:id/deep-analysis", aiLimiter, async (req, res) => {
  const session = sessions[req.params.id];
  if (!session) return res.status(404).json({ error: "Session not found" });

  const key = process.env.GEMINI_API_KEY || "";
  if (!key || key.length < 20 || key.includes("YOUR_GEMINI_API_KEY")) {
    return res.status(503).json({ error: "GEMINI_API_KEY is not configured in server/.env" });
  }

  try {
    const result = await runDeepAnalysis(session, {
      apiKey: process.env.GEMINI_API_KEY,
      modelName: process.env.GEMINI_MODEL || "gemini-flash-latest",
      synthesisModel: process.env.GEMINI_SYNTHESIS_MODEL || process.env.GEMINI_MODEL || "gemini-flash-latest"
    });
    session.deepAnalysis = result;
    saveSessions();
    res.json({
      ...result,
      rateLimit: { remaining: Math.max(0, AI_MAX_CALLS - (req.rateLimit?.current || 0)) }
    });
  } catch (err) {
    res.status(502).json({ error: `Deep analysis failed: ${err.message}` });
  }
});

app.listen(PORT, () => {
  const keyOk = !!(process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY.length > 20);
  console.log(`\n  MAS API Server v8.5`);
  console.log(`  Server:   http://localhost:${PORT}`);
  console.log(`  AI:       ${process.env.GEMINI_MODEL || "gemini-2.0-flash"}`);
  console.log(`  Limit:    ${AI_MAX_CALLS} calls per ${AI_WINDOW_MS / 60000}min`);
  console.log(`  AI Status:${keyOk ? "ready" : "NOT configured — set GEMINI_API_KEY in .env"}`);
  console.log(`  Sessions: ${Object.keys(sessions).length} stored\n`);
});
