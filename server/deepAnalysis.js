const { GoogleGenerativeAI } = require("@google/generative-ai");
const { PERSPECTIVES, SYNTHESIS_SYSTEM_PROMPT } = require("./perspectives");

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

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function callGemini(apiKey, modelName, systemPrompt, userContent, retries = 3, initialDelayMs = 3000) {
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({
    model: modelName || "gemini-flash-latest",
    systemInstruction: systemPrompt
  });

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const result = await model.generateContent(userContent);
      return result.response.text();
    } catch (err) {
      const is429 = err.message.includes("429") || err.message.includes("Quota exceeded") || err.message.includes("RESOURCE_EXHAUSTED");
      if (is429 && attempt < retries) {
        let waitMs = initialDelayMs * Math.pow(2, attempt);
        const match = err.message.match(/retry in ([\d\.]+)s/i);
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

async function runDeepAnalysis(session, options = {}) {
  const {
    apiKey,
    modelName = "gemini-flash-latest",
    synthesisModel = "gemini-flash-latest"
  } = options;

  if (!apiKey) {
    throw new Error("GEMINI_API_KEY not configured");
  }

  const userContent = buildUserContent(session);

  const perspectives = [];
  for (const p of PERSPECTIVES) {
    try {
      const text = await callGemini(apiKey, modelName, p.systemPrompt, userContent);
      perspectives.push({ id: p.id, label: p.label, labelVi: p.labelVi, icon: p.icon, analysis: text });
    } catch (err) {
      perspectives.push({ id: p.id, label: p.label, labelVi: p.labelVi, icon: p.icon, analysis: `ERROR: ${err.message}`, error: true });
    }
    // Small pause between calls to respect API rate limits
    await delay(300);
  }

  const synthesisInput = perspectives
    .map((p) => `=== ${p.label} (${p.labelVi}) ===\n${p.analysis}`)
    .join("\n\n");

  let synthesis = "";
  try {
    synthesis = await callGemini(
      apiKey,
      synthesisModel,
      SYNTHESIS_SYSTEM_PROMPT,
      `Here are the 9 perspective analyses. Synthesize them into one optimal MAS adaptation roadmap.\n\n${synthesisInput}`
    );
  } catch (err) {
    synthesis = `Synthesis failed: ${err.message}`;
  }

  return { perspectives, synthesis };
}

module.exports = { runDeepAnalysis };
