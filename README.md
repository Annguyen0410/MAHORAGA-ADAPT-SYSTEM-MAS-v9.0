<div align="center">

# MAHORAGA ADAPT SYSTEM (MAS) v8.5

**A Cognitive Operating System & Predictive Embodied Framework for Human–AI Co-Evolution**

<br />

![Mahoraga Spin Wheel](./assets/mahoraga_wheel.gif)

<br />

> *"With this treasure, I summon the potential within. One turn of the wheel, and the object begins to bow."*

<br />

[![Protocol Version](https://img.shields.io/badge/Protocol-v8.5.0-blueviolet?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)
[![AI Engine](https://img.shields.io/badge/AI_Engine-Gemini--Flash-cyan?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)
[![Type](https://img.shields.io/badge/Type-Cognitive_OS-orange?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://github.com/Annguyen0410/MAHORAGA-ADAPT-SYSTEM-MAS-v8.5)

---

</div>

## Abstract

The **Mahoraga Adapt System (MAS)** is a formal cognitive architecture and predictive embodied framework designed to synchronize direct human sensory experience with artificial intelligence inference engines. Grounded in Predictive Embodied Meta-Learning (PEML) and inspired by the metaphor of absolute recursive adaptation, MAS converts external environmental friction into internal structural capability.

Through structured human operational capture, automated property assessment, and parallel multi-perspective analysis, MAS constructs executable 9-step adaptation roadmaps that systematically eliminate friction across physical, cognitive, tools, and social domains.

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

### 4. Parallel Deep Analysis Engine (9 Perspectives + Synthesis)
When evaluated, the system executes 9 analytical perspectives in parallel:
1. **Material & Force**: Mechanical properties, elasticity, and load boundaries.
2. **Frequency & Rhythm**: Cycle timing, vibration, and tempo consistency.
3. **Error & Failure Modes**: Root cause analysis across failure taxonomy.
4. **Biomechanical / Ergonomic**: Motor patterns, posture, joint mechanics, and strain.
5. **Cognitive Load & Focus**: Mental bandwidth, attention allocation, and fatigue thresholds.
6. **Environmental Constraints**: External conditions, lighting, noise, and setup geometry.
7. **Habit & Pattern Loops**: Behavioral feedback loops and automatic routines.
8. **Risk & Safety Boundaries**: Injury prevention, failure containment, and safety margins.
9. **Transfer & Generalization**: Cross-domain skill mapping and invariant extraction.

**10th Synthesis**: Aggregates all 9 perspective analyses into an optimal, non-redundant adaptation roadmap.

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

---

## Interactive Web Interface Workflow

1. **Session Initialization**: Define the target domain, goal, skill baseline, and historical error patterns.
2. **Human Operational Capture**: Input direct sensory observations, physical measurements, performed tests, and constraint failures.
3. **AI Property Assessment**: Execute automated analysis to extract control variables and risk factors.
4. **Adaptive Roadmap Generation**: Generate a structured 9-step progression protocol (*Baseline Calibration* to *Embodiment Validation*).
5. **Parallel Deep Analysis**: Execute the 9-perspective engine with automated 429 rate-limit backoff retry to receive the 10th Optimal Synthesis Path.

---

## Technical Specifications & Resilience

- **AI Provider**: Google Generative AI (`@google/generative-ai`)
- **Default Model**: `gemini-flash-latest`
- **Rate Limit Resilience**: Includes automatic exponential backoff retries and sequential throttling to prevent `429 Too Many Requests` errors on Google AI Studio Free Tier API quotas.
- **Data Persistence**: Local session state managed via `server/sessions.json` and browser `localStorage`.

---

<div align="center">

**SPIN THE WHEEL. BECOME THE GENERAL.**

*"No phenomenon is unadaptable."*

</div>
