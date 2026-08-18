const crypto = require("crypto");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const { PERSPECTIVES, SYNTHESIS_SYSTEM_PROMPT } = require("./perspectives");
const budget = require("./geminiBudget");
const modelBudget = require("./modelBudget");

function buildUserContent(session) {
  const c = session.humanCapture || {};
  return `TARGET: ${session.target}
DOMAIN: ${session.domain}
GOAL: ${session.goal || "(not specified)"}
SKILL LEVEL: ${session.baseline?.skillLevel || "unknown"}/10
HISTORICAL PATTERNS: ${session.baseline?.historicalPatterns || "(none)"}
PREVIOUS ATTEMPTS: ${session.baseline?.previousAttempts || "(none)"}

HUMAN CAPTURE DATA:
- Observed properties: ${c.observedProperties || "(none)"}
- Evaluation: ${c.evaluation || "(none)"}
- Description: ${c.description || "(none)"}
- Test performed: ${c.testPerformed || "(none)"}
- Test result: ${c.testResult || "(none)"}
- Environment/context: ${c.environment || "(none)"}
- Measured signals: ${c.measuredSignals || "(none)"}
- Failure type: ${c.failureType || "(none)"}`;
}

// Deterministic fingerprint of everything that feeds the analysis.
// If the user has not changed anything, re-running costs 0 AI calls.
function contentHash(session) {
  const c = session.humanCapture || {};
  const payload = JSON.stringify({
    target: session.target,
    domain: session.domain,
    goal: session.goal,
    baseline: session.baseline,
    capture: c,
    assessment: session.aiAssessment
  });
  return crypto.createHash("sha1").update(payload).digest("hex").slice(0, 16);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function callGemini(apiKey, systemPrompt, userContent, preferredModel, retries = 3, initialDelayMs = 3000) {
  // Reserve quota BEFORE calling: if every model is at its free-tier
  // RPM/TPM/RPD limit, refuse without hitting the API (never billed).
  const estTokens = modelBudget.estimateTokens(systemPrompt) + modelBudget.estimateTokens(userContent);
  const modelId = modelBudget.acquire([preferredModel], estTokens);
  if (!modelId) {
    const err = new Error("All Gemini models are at their free-tier quota (RPM/TPM/RPD). No AI call was made — try again later.");
    err.quotaExhausted = true;
    throw err;
  }

  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({
    model: modelId,
    systemInstruction: systemPrompt
  });

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const result = await model.generateContent(userContent);
      budget.record(1);
      modelBudget.recordTokens(modelId, result.response.usageMetadata?.totalTokenCount || estTokens);
      return result.response.text();
    } catch (err) {
      const is429 = err.message.includes("429") || err.message.includes("Quota exceeded") || err.message.includes("RESOURCE_EXHAUSTED");
      if (is429) modelBudget.markBlocked(modelId);
      if (is429 && attempt < retries) {
        let waitMs = initialDelayMs * Math.pow(2, attempt) + Math.floor(Math.random() * 800);
        const match = err.message.match(/retry in ([\d.]+)s/i);
        if (match && match[1]) {
          waitMs = Math.max(waitMs, Math.ceil(parseFloat(match[1]) * 1000) + 1000);
        }
        console.log(`[DeepAnalysis] Rate limited (429). Retrying attempt ${attempt + 1}/${retries} after ${Math.round(waitMs / 1000)}s...`);
        await delay(waitMs);
        continue;
      }
      throw err;
    }
  }
}

// Build a single prompt that runs all 9 agent personalities in ONE call.
function buildBatchPrompt() {
  const sections = PERSPECTIVES.map(
    (p) => `### ${p.id.toUpperCase()} — ${p.label}\n${p.systemPrompt}`
  ).join("\n\n");
  return `You are the PARALLEL PERSPECTIVE ENGINE of the Mahoraga Adapt System (MAS).

9 distinct thinking agents — each with its own lens and personality — analyze the SAME user situation. Stay in character for each section: the analytical agent is rigorous and structural, the dialectical agent hunts contradictions, the generative agent imagines the impossible, and so on.

Answer ALL 9 sections in ONE response. Keep each section 3-6 sentences: concrete, grounded in the user's data, and actionable. Do not summarize other sections.

Use EXACTLY these section headers (the parser depends on them):

${sections}`;
}

function parseBatchedResponse(text) {
  const byId = {};
  const lines = String(text || "").split("\n");
  let currentId = null;
  const buf = [];
  const flush = () => {
    if (currentId) byId[currentId] = buf.join("\n").trim();
  };
  for (const line of lines) {
    const m = line.match(/^###\s*([A-Z_]+)\s*—?\s*(.*)$/i);
    if (m) {
      flush();
      currentId = m[1].toLowerCase();
      buf.length = 0;
    } else {
      buf.push(line);
    }
  }
  flush();

  return PERSPECTIVES.map((p) => {
    const analysis = byId[p.id.toUpperCase()] || byId[p.id] || "";
    return {
      id: p.id,
      label: p.label,
      labelVi: p.labelVi,
      icon: p.icon,
      analysis: analysis || `(no section found for ${p.id})`
    };
  });
}

function stripErrorFlag(p) {
  return { id: p.id, label: p.label, labelVi: p.labelVi, icon: p.icon, analysis: p.analysis };
}

async function runDeepAnalysis(session, options = {}) {
  const {
    apiKey,
    modelName = null, // preferred model; modelBudget falls back through its priority list
    synthesisModel = null,
    mode = "auto", // "auto" | "batch" | "full"
    cache = null
  } = options;

  if (!apiKey) {
    throw new Error("GEMINI_API_KEY not configured");
  }

  const hash = contentHash(session);
  const cached = cache ? cache[hash] : null;
  if (cached && Array.isArray(cached.perspectives) && cached.perspectives.length && cached.synthesis) {
    return { ...cached, cached: true, modeUsed: "cache", hash };
  }

  const userContent = buildUserContent(session);
  let perspectives = [];
  let modeUsed = mode;

  if (mode === "full") {
    // True independent multi-agent: one call per personality (expensive, ~10 calls).
    for (const p of PERSPECTIVES) {
      const cachedP = cache?.[hash]?.perspectives?.find((x) => x.id === p.id);
      if (cachedP && cachedP.analysis && !cachedP.analysis.startsWith("ERROR:")) {
        perspectives.push(cachedP);
        continue;
      }
      try {
        const text = await callGemini(apiKey, p.systemPrompt, userContent, modelName);
        perspectives.push({ id: p.id, label: p.label, labelVi: p.labelVi, icon: p.icon, analysis: text });
      } catch (err) {
        perspectives.push({ id: p.id, label: p.label, labelVi: p.labelVi, icon: p.icon, analysis: `ERROR: ${err.message}`, error: true });
      }
      if (cache) cache[hash] = { perspectives: perspectives.map(stripErrorFlag) };
      await delay(250);
    }
    modeUsed = "full";
  } else {
    // Batch mode: all 9 personalities in one call (+ optional repair + synthesis).
    modeUsed = "batch";
    try {
      const batchedText = await callGemini(apiKey, buildBatchPrompt(), userContent, modelName);
      perspectives = parseBatchedResponse(batchedText);

      // Repair pass: if any section was missed, ask for ONLY the missing ones in one call.
      const missing = perspectives.filter((p) => p.analysis.startsWith("(no section"));
      if (missing.length && missing.length < PERSPECTIVES.length) {
        const repairPrompt = `Answer ONLY these missing sections, using the same ### headers:\n\n` +
          missing.map((p) => {
            const def = PERSPECTIVES.find((x) => x.id === p.id);
            return `### ${p.id.toUpperCase()} — ${def.label}\n${def.systemPrompt}`;
          }).join("\n\n");
        const repairText = await callGemini(apiKey, repairPrompt, userContent, modelName);
        const repaired = parseBatchedResponse(repairText);
        for (const r of repaired) {
          const idx = perspectives.findIndex((p) => p.id === r.id);
          if (idx !== -1 && !r.analysis.startsWith("(no section")) perspectives[idx] = r;
        }
      }
    } catch (err) {
      perspectives = PERSPECTIVES.map((p) => ({
        id: p.id, label: p.label, labelVi: p.labelVi, icon: p.icon,
        analysis: `ERROR: ${err.message}`, error: true
      }));
    }
  }

  const synthesisInput = perspectives
    .map((p) => `=== ${p.label} (${p.labelVi}) ===\n${p.analysis}`)
    .join("\n\n");

  let synthesis = "";
  try {
    synthesis = await callGemini(
      apiKey,
      SYNTHESIS_SYSTEM_PROMPT,
      `Here are ${perspectives.length} perspective analyses from 9 distinct agents. Synthesize them into one optimal MAS adaptation roadmap.\n\n${synthesisInput}`,
      synthesisModel
    );
  } catch (err) {
    synthesis = `Synthesis failed: ${err.message}`;
  }

  const result = {
    perspectives: perspectives.map(stripErrorFlag),
    synthesis,
    cached: false,
    modeUsed,
    hash
  };
  if (cache) cache[hash] = result;
  return result;
}

module.exports = { runDeepAnalysis, contentHash, parseBatchedResponse, buildBatchPrompt };
