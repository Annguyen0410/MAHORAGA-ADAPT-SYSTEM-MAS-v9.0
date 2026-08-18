<div align="center">

# MAHORAGA ADAPT SYSTEM (MAS) v9.0

**A Cognitive Operating System & Predictive Embodied Framework for Human–AI Co-Evolution**

<br />

![Mahoraga Spin Wheel](./assets/mahoraga_wheel.gif)

<br />

> *"With this treasure, I summon the potential within. One turn of the wheel, and the object begins to bow."*

<br />

[![Protocol Version](https://img.shields.io/badge/Protocol-v9.0.0-blueviolet?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)
[![AI Engine](https://img.shields.io/badge/AI_Engine-Gemini--Flash-cyan?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)
[![Type](https://img.shields.io/badge/Type-Cognitive_OS-orange?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)

---

</div>

## Abstract

The **Mahoraga Adapt System (MAS)** is a formal cognitive architecture and predictive embodied framework designed to synchronize direct human sensory experience with artificial intelligence inference engines. Grounded in Predictive Embodied Meta-Learning (PEML) and inspired by the metaphor of absolute recursive adaptation, MAS converts external environmental friction into internal structural capability.

Through structured human operational capture, automated property assessment, and parallel multi-perspective analysis, MAS constructs executable adaptation roadmaps that systematically eliminate friction across physical, cognitive, tools, and social domains.

**v9.0 introduces the Adaptation Engine**: a measured state machine (First Hit → Calibrating → Drilling → Refining → Transferring → Immune) that reads the user's logged check-in data, detects improving/plateau/declining trends, and generates the next move dynamically instead of replaying a fixed script. The system now genuinely adapts and evolves with the user, rather than merely generating plans.

---

## Core System Architecture

### 1. Predictive Embodied Meta-Learning (PEML)
PEML utilizes a 7-layer predictive hierarchy to minimize error signals between an internal mental model and environmental reality:
- Layer 1: Raw Sensory Capture
- Layer 2: Signal Filtering & Feature Extraction
- Layer 3: Failure Taxonomy Mapping
- Layer 4: Control Variable Isolation
- Layer 5: Hypothesis & Micro-Drill Generation
- Layer 6: Constraint Verification & Refinement
- Layer 7: Ontological Assimilation

### 2. The Eight-Handled Wheel Protocol
The operational execution follows a recursive 8-stage adaptation loop:
`Observe` -> `Hypothesize` -> `Act` -> `Measure` -> `Update` -> `Optimize` -> `Assimilate` -> `Evolve`

### 3. Anti-Fragile Failure Taxonomy
Friction and errors are classified into four distinct operational failure modes:
- **Perception Failure**: Inaccurate or insufficient sensory data collection.
- **Model Failure**: Flawed internal representation of force, timing, or constraints.
- **Execution Failure**: Motor control, physical fatigue, or precision degradation.
- **Context Failure**: Environmental shifts, external noise, or boundary mismatches.

### 4. The Adaptation Engine (v9.0)
A deterministic state machine computed from measured check-in data (quality, effort, stability, discomfort) logged across sessions:

| Phase | Meaning | Engine's next instruction |
|-------|---------|---------------------------|
| First Hit | No measured data yet | Run one baseline test; treat the first miss as data |
| Calibrating | Baseline established | 3 slow reps on one control variable |
| Drilling | Quality improving | Keep the winning variable, add reps, stop before fatigue |
| Refining | Quality plateaued | Change ONE variable instead of pushing harder |
| Transferring | High quality, low effort | Prove generalization in a changed context |
| Immune | Consistent high quality across contexts | Save as validated template; pick next target |
| Stuck | Quality declining | Reduce difficulty, return to baseline, re-observe |

Trend detection uses linear regression over the quality series; phases are never scripted from a template — they emerge from the user's own measurements. Roadmaps carry a live `[ADAPTIVE STATE]` header and a `NEXT SPIN` instruction that updates after every logged check-in.

### 5. Parallel Deep Analysis Engine (9 Perspectives + Synthesis)
When evaluated, the system executes 9 analytical perspectives:
1. **Material & Force**: Mechanical properties, elasticity, and load boundaries.
2. **Frequency & Rhythm**: Cycle timing, vibration, and tempo consistency.
3. **Error & Failure Modes**: Root cause analysis across failure taxonomy.
4. **Biomechanical / Ergonomic**: Motor patterns, posture, joint mechanics, and strain.
5. **Cognitive Load & Focus**: Mental bandwidth, attention allocation, and fatigue thresholds.
6. **Environmental Constraints**: External conditions, lighting, noise, and setup geometry.
7. **Habit & Pattern Loops**: Behavioral feedback loops and automatic routines.
8. **Risk & Safety Boundaries**: Injury prevention, failure containment, and safety margins.
9. **Transfer & Generalization**: Cross-domain skill mapping and invariant extraction.

**10th Synthesis**: Aggregates all 9 perspective analyses into an optimal, non-redundant adaptation roadmap. Each perspective is framed as an independent agent with its own analytical personality (analytical, systemic, kinesthetic, temporal, relational, pattern, constraint, dialectical, generative).

---

## Multi-Agent Execution under Rate Limits (v9.0)

The deep analysis engine runs 9 independent agent personalities, which historically consumed 10 Gemini calls per run — half of the free-tier hourly budget. v9.0 resolves this with three complementary mechanisms:

1. **Batch Mode**: All 9 agent perspectives run inside a single prompt with strict section delimiters, then are parsed back into 9 independent result cards. Cost: 2 calls per run (perspectives + synthesis), with an optional repair call only if a section is missing. Full independent mode remains available when budget allows.

2. **Content-Hash Caching**: Every analysis is keyed by a SHA-1 fingerprint of the session data. Re-running deep analysis on unchanged data returns the cached result instantly — 0 AI calls — and the cache survives server restarts (persisted in `sessions.json`).

3. **Real Budget Tracking**: The server now tracks actual Gemini invocations (`server/geminiBudget.js`) rather than HTTP request counts, so cache hits and batch mode are rewarded instead of penalized. Mode selection is budget-aware: with ≥12 calls remaining the server runs the full 9-agent mode; otherwise it degrades gracefully to batch mode instead of failing. The client displays the estimated call cost before every run and reports which mode was used.

The result: a full deep analysis costs ~2 calls instead of 10, and repeated analysis of unchanged data costs nothing.

---

## Software Architecture (v9.0)

The browser client was refactored from a single 2,000-line file into ordered classic-script modules (no build step required; works over `file://` and any static server):

| Module | Responsibility |
|--------|----------------|
| `js/utils.js` | Storage helpers, HTML escaping, debounce, form reads |
| `js/storage.js` | Storage keys, session/template normalization |
| `js/api.js` | REST client, health + rate-limit polling |
| `js/graph.js` | Knowledge graph data and rendering |
| `js/adaptation.js` | Adaptation engine: phases, trends, check-ins, next-step |
| `js/assessment.js` | Local assessment, roadmap, complete-packet generation |
| `js/session.js` | Session state, capture forms, wizard controller |
| `js/templates.js` | Template memory with evolving statuses |
| `js/backup.js` | Export/import of all local data as JSON |
| `js/ui.js` | View switching, loading overlay, rate-limit UI, deep-analysis render |
| `js/main.js` | Event wiring, examples, initialization |

The user interface was restructured into a 3-step wizard (Describe → Plan → Evolve) with a fourth advanced step (Deep Dive). Steps unlock automatically as data is provided, so the user is never confronted with the full system at once; dense supporting information (assessment details, deep analysis) is collapsed behind progressive disclosure.

Server components: `server/server.js` (REST API), `server/deepAnalysis.js` (multi-agent orchestration), `server/perspectives.js` (agent definitions), `server/geminiBudget.js` (AI call budget).

### Automated Tests

The test suite (`tests/`) covers the adaptation engine, wizard controller, adaptation panel, lazy template rendering, backup round-trip, and the server-side batch parser and budget. It runs the browser modules inside a stubbed DOM, so no browser or network is required:

```bash
npm test
```

### Data Backup

Use the **Export** / **Import** buttons in the sidebar to save or restore the full local dataset (current session, templates, and check-in evolution history) as a single JSON file — useful for moving between machines without losing adaptation progress.

---

## Honest Capability Map

MAS is transparent about which capabilities are deterministic local logic and which require the optional Gemini integration:

| Capability | Local (no API key) | Gemini (server + key) |
|------------|-------------------|----------------------|
| Knowledge graph, templates, session state | Yes | Yes |
| Assessment + roadmap generation | Heuristic engine (keyword + structured templates) | LLM assessment + LLM roadmap |
| Adaptation engine (phases, trends, next-step) | Yes (data-driven, deterministic) | Yes |
| 9-agent deep analysis + synthesis | No | Yes (batch or full mode) |
| Check-in history and evolution tracking | Yes | Yes |

No external AI or internet connection is required for the core loop; the plan is generated locally from what the user types. The more detail the user gives, the better the plan.

---

## Repository Index & Documentation

### Core Protocols (`/core`)
- **[Master Codex v8.5](./core/MAS_MASTER_CODEX_v8_5.md)**: Central reference specification defining the Human-AI integration loop.
- **[Ontological Adaptation Protocol](./core/MAS_v8_5_Ontological_Adaptation.md)**: Technical standard for property extraction and diagnostic capture.
- **[Genesis and Logic System](./core/MAS_Genesis_and_Logic_System.md)**: Philosophical foundations and atomic logic of adaptation.

### Technical Analysis (`/analysis`)
- **[Operational Mechanisms](./analysis/MAS_Operational_Mechanisms.md)**: Formal breakdown of the 7-layer predictive architecture.
- **[Expert Review v8.5](./analysis/MAS_Expert_Review_v8_5.md)**: Comprehensive evaluation, guardrails, and implementation guidelines.
- **[Deep Analysis Specification](./analysis/MAS_v8_5_Deep_Analysis.md)**: Anti-delusion logic and perspective generation structures.

### Mythos & Symbolic Foundations (`/mythos`)
- **[Character Introduction](./mythos/Mahoraga_Character_Intro.md)**: Analysis of the Divine General as a functional adaptive archetype.
- **[Naming Revelation](./mythos/Mahoraga_Naming_Revelation.md)**: Philosophical rationale behind the Mahoraga terminology.

### Case Studies (`/case_studies`)
- **[Keyboard Actuation Mastery](./case_studies/Keyboard_Actuation_Mastery.md)**: Eradicating typing errors and actuation friction at 90+ WPM.
- **[Pencil Pressure Control](./case_studies/Pencil_Pressure_Control.md)**: Optimizing force feedback and tension in fine sketching.
- **[An's Decade of Mahoraga](./case_studies/An_Decade_of_Mahoraga.md)**: A 10-year narrative log of physical and cognitive adaptation.

---

## System Quick Start & Server Setup

### Environment Configuration

1. Navigate to the server directory:
   ```bash
   cd server
   ```

2. Create `.env` from template:
   ```bash
   cp .env.example .env
   ```

3. Open `server/.env` and insert your Google AI Studio API key:
   ```env
   PORT=3001
   GEMINI_API_KEY=AIzaSyYourActualKeyHere...
   GEMINI_MODEL=gemini-flash-latest
   GEMINI_ASSESSMENT_MODEL=gemini-flash-latest
   GEMINI_ROADMAP_MODEL=gemini-flash-latest
   GEMINI_SYNTHESIS_MODEL=gemini-flash-latest
   ```

### Installation and Execution

```bash
cd server
npm install
npm start
```

Access the application interface in your web browser:
`http://localhost:3001`

Without the server, open `index.html` directly in a browser: the core loop (steps 1-3) runs locally with `localStorage` persistence.

---

## Interactive Web Interface Workflow

1. **Describe**: Define the target domain, goal, skill baseline, and historical error patterns; record direct sensory observations, physical measurements, performed tests, and constraint failures.
2. **Plan**: Generate a structured adaptation roadmap (*Baseline Calibration* to *Embodiment Validation*) with a live adaptive header — local heuristic engine by default, Gemini when available.
3. **Evolve**: Log measured check-ins (quality, effort, stability, discomfort) after each practice run. The Adaptation Engine updates the phase and trend, redraws the progress curve, and issues the next instruction. Save roadmaps as templates whose status evolves from Candidate → Validated → Embodied based on accumulated evidence.
4. **Deep Dive (advanced)**: Run the 9-agent analysis with automatic batch/cache/budget management to receive the 10th Optimal Synthesis Path.

---

## Security Notes

- The API server binds to `127.0.0.1` by default (override with `HOST=0.0.0.0`) and serves only the public frontend assets — server sources, `sessions.json`, and `node_modules` are never reachable over HTTP.
- CORS is restricted to loopback origins and `file://` pages; security headers (nosniff, `X-Frame-Options`, a strict Content-Security-Policy, `no-store` on API responses) are applied to every response.
- Session create/update input is validated through a field whitelist (`server/validate.js`); client session ids are sanitized before use in API URLs.

## Technical Specifications & Resilience

- **AI Provider**: Google Generative AI (`@google/generative-ai`)
- **Default Model**: `gemini-flash-latest`
- **Rate Limit Resilience**: 9-agent deep analysis batches into 1-2 calls; content-hash caching makes unchanged re-runs free; a real Gemini call budget (`AI_RATE_LIMIT_MAX`, default 20/hour) drives budget-aware mode selection with exponential backoff + jitter on 429 responses.
- **Data Persistence**: Local session state managed via `server/sessions.json` and browser `localStorage`.

---

<div align="center">

**SPIN THE WHEEL. BECOME THE GENERAL.**

*"No phenomenon is unadaptable."*

</div>
