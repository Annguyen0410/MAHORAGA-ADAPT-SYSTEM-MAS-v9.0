# Changelog

All notable changes to the Mahoraga Adapt System (MAS).

## [9.0.0] — 2026-08-17

### Added
- **Adaptation Engine**: a measured state machine (First Hit → Calibrating → Drilling → Refining → Transferring → Immune, plus Stuck) computed from logged check-in data, with linear-regression trend detection (improving / plateau / declining). The engine issues a dynamic "next spin" instruction instead of replaying a fixed script.
- **Evolution Loop UI**: check-in form (quality, effort, stability, discomfort, note, transfer flag), progress sparkline, phase badge, and a history list. The wheel now genuinely adapts and evolves with the user.
- **Evolving templates**: saved roadmaps carry a status (Candidate → Validated → Embodied) and an evidence count derived from measured data.
- **Multi-agent deep analysis with rate-limit resilience**:
  - Batch mode runs all 9 agent perspectives in 1-2 calls (down from 10).
  - Content-hash caching makes re-runs on unchanged data cost 0 AI calls.
  - Real Gemini call budget (`server/geminiBudget.js`) drives budget-aware mode selection (full vs batch) and honest UI cost display.
  - Client-side agent-mode toggle (Auto / Fast / Full) and 120s timeout for long analyses.
- **Modular client architecture**: the single 2,000-line `app.js` was split into ordered classic-script modules under `js/` (no build step; works over `file://`).
- **Wizard UI**: 3 core steps (Describe → Plan → Evolve) plus an advanced Deep Dive step. Steps unlock automatically as data is provided; dense information is collapsed behind progressive disclosure.
- **Data backup**: Export / Import of the full local dataset (session, templates, check-in history) as a single JSON file.
- **Automated tests**: `tests/` suite covering the adaptation engine, wizard, adaptation panel, lazy templates, backup round-trip, and the server batch parser / budget. Run with `npm test`.
- Root `package.json` with `npm test` and `npm start` scripts.

### Changed
- Protocol bumped to v9.0.0 across server health, package metadata, and documentation.
- Assessment details collapsed behind a `<details>` summary; templates lazy-load their roadmap text on demand.
- Plan invalidation is now hash-based: a roadmap is only cleared when the capture data that generated it actually changes.

### Fixed
- Crash when clearing all capture text (`captureCompleteness(null)`).
- Check-in form data loss: the form was rebuilt on every re-render; it is now static HTML wired once.
- Example sessions reached deep analysis with empty server-side capture (POST `/api/sessions` now persists `humanCapture`).
- `hidden` attributes were overridden by component `display` rules; a global `[hidden]` rule now wins.
- Premature "Transferring / Immune" from one or two lucky samples (now requires ≥ 3 spins, anti-overfit).
- User could be left standing on a step that became locked after editing data; the wizard now falls back to the highest unlocked step.
- Duplicate `deep-mode-chip` handler created during the module split.
- Stale deep-analysis results shown after "Start over".
- Unused import in `server/server.js`.
- Deep-analysis client timeout raised from 30s to 120s to accommodate batch mode with retries.

### Security
- **Static exposure closed**: the server previously served the whole repo root over HTTP, exposing `server/sessions.json` (user data), server source, and `node_modules`. Static serving is now whitelisted to the public frontend directories only; `server/`, `node_modules/`, `tests/` and package files return 404.
- **Loopback bind**: the API now binds to `127.0.0.1` by default (override with `HOST=0.0.0.0`) instead of all interfaces, removing the LAN attack surface.
- **CORS locked down**: replaced `Access-Control-Allow-Origin: *` with a loopback + `file://` allowlist, so arbitrary websites can neither read nor preflight-mutate the local API.
- **Security headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a strict Content-Security-Policy, and `Cache-Control: no-store` on all `/api/` responses.
- **Input validation**: session create/update now runs through a field whitelist (`server/validate.js`) — type coercion, length caps, and rejection of internal fields (ids, caches, roadmap) instead of blind `Object.assign`.
- **ID sanitization**: session ids are validated against a safe character set before being interpolated into API URLs (protects against tampered backups).
- **No stack-trace leakage**: malformed JSON bodies no longer return body-parser's default HTML error page (which exposed the absolute server path and module versions); a dedicated error handler returns clean JSON `400`/`413`/`415` responses.
- **Prototype-pollution proofed**: `__proto__` / `constructor` payloads on `PUT` are ignored by the field whitelist — verified live: no foreign keys persisted, no global prototype pollution.

### Performance
- Template Memory HTML reduced ~5x (626KB → 126KB at 200 templates) by lazy-loading roadmap text.
- Check-in history list capped at the 15 most recent entries.
- Benchmark-verified: 500 check-ins render in well under a millisecond per update; graph, sources and session re-renders are sub-millisecond.

## [8.5.0] — previous

- Cognitive OS framework with 9-perspective deep analysis, sequential Gemini calls, and express rate limiting.
- Local heuristic assessment and roadmap generation (no API key required for the core loop).
- Knowledge graph, template memory, and example sessions.
