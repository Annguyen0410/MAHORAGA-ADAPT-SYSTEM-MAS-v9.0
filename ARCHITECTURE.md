# Mei — Architecture & Upgrade Guide

This document describes the current code structure and the **extension points** so future
features can be added without touching code all over the place. Read it alongside `README.md`.

Two companion docs: `docs/CAPABILITIES.md` (what is wired, what is deliberately reserved)
and `docs/COMMAND_REFERENCE.md` (the slash-command surface).

---

## 1. Layers

```text
browser.py / litebrowser/main.py     Entry: profile + QApplication + 2 AppShell
        │
litebrowser/qt.py                     Qt façade — the only sanctioned way in
        │                             (PyQt5 / PyQt6 selected by qt_compat.py)
litebrowser/ui/                       UI layer
   ├─ app_shell.py                    Master shell: rail + omnibar + insight panel
   ├─ main_window/window.py           SearchWindow (main browser)
   │    └─ window_topbar.py           Toolbar chrome: nav, engine, address bar, pill, collapse
   ├─ personal_window.py              Personal Hub (Notes/Tasks/Calendar/Boards/Files/Sites)
   ├─ ai_window.py                    AI Workspace
   ├─ shell/pages.py                  Home / Library / Settings / History
   ├─ components.py                   Shared design system
   ├─ theme.py                        Palette + QSS (theme + accent, §6.7 = dialog verbs)
   └─ dialogs/                        All child dialogs
        └─ common.py                  Stylesheet hook + button roles + dialog_footer()
        │
litebrowser/browser/                  Browser core (independent of the shell)
   ├─ tab_manager.py                  Tab lifecycle + hibernation
   ├─ browser_page.py                 Permissions + Chrome-compat shim + profile scripts
   ├─ new_tab_page.py                 Speed dial (theme-aware)
   └─ adblock.py                      Interceptor: blocklist + HTTPS-only + client hints
        │
litebrowser/services/                 Data layer (never imports Qt widgets)
   ├─ prefs.py (core)                 All getters/setters + registry
   ├─ update_service.py               Version check (product-tagged) + verified install
   ├─ life_service.py                 Tasks / Events / Boards / Saved pages
   ├─ personal_service.py             Notes (SafeVault) + personal root
   ├─ personal_plan.py                Weekly student planner: courses / items / blocks (v2)
   ├─ study_session.py                Study sessions: pour from an item, credit minutes back
   ├─ study_flow.py                   The loop: one next step read from every store
   ├─ link_service.py                 Two-way entity links (entity_links.json)
   ├─ flashcard_service.py            SM-2 flashcards (Review page + study sessions)
   ├─ ai_service.py / retriever.py    RAG index + BM25 (+ cosine embed when Ollama)
   ├─ history_service.py              Activity log + backup/import
   ├─ brief_service.py                Morning Brief (local-first digest)
   ├─ agent_actions.py                AI agent: /agent summary|tasks|review
   ├─ sync_service.py                 Self-hosted sync (push/pull JSON bundle)
   ├─ tab_sets.py                     Save/open tab and research collections (versioned links)
   └─ ...                             download_mgr, password, security, ...
        │
litebrowser/core/                     Foundation: paths, storage, lock, version
   ├─ product.py                      Identity: PRODUCT_ID, version, update channel, asset
   ├─ commands.py                      Slash-command registry (name / arg / kind / example)
   ├─ app_paths.py                     Workspace chain manifest + profile paths
   ├─ store.py / migrations.py        Versioned JSON stores + stepwise upgrades
   ├─ secret_store.py                 OS-protected credentials (DPAPI on Windows)
   ├─ greetings.py                    Shared cafe greeting (no services↔browser cycle)
   └─ ...                             prefs, time_utils, log, profile_lock
litebrowser/data/chain.json           Workspace-app manifest (shipped as package data)
```

**Important rules** (enforced by `tests/test_architecture_boundaries.py`, which also fails on
orphan modules and stale allowlists):

1. `services/` and `core/` must **not** import `ui/`. All data flows through services.
2. `services/` must not import `browser/`, and `browser/` must not import `services/`
   (shared helpers live in `core/`, e.g. `core/greetings.py`).
3. The layer graph stays acyclic.

---

## 2. Storage & lock

- All data lives in the profile dir (`runtime_data/profiles/<Name>/`).
- File writes use **atomic writes** (`storage_utils.write_json` / `write_text_atomic`)
  → no risk of corrupting a file mid-write.
- `core/profile_lock.py` is a **per-profile RLock** → services can nest locks safely
  (e.g. `add_task` locks, then calls `history_service.log_event` which locks again).

### Versioned stores (`core/store.py`)

A JSON store is described **once** and read/written through the store API:

```python
PLAN_STORE = StoreSpec(name="personal_plan.json", version=PLAN_VERSION, default=_default_plan)

plan   = read_store(base_dir, PLAN_STORE)     # upgrades + persists once if older
write  = write_store(base_dir, PLAN_STORE, payload)  # stamps version, atomic, locked
```

Guarantees: the per-profile lock is taken for you; every write is atomic and carries
`"version"`; an older file is upgraded one version at a time via `core/migrations.py`
and re-persisted exactly once; a file written by a **newer** build is left untouched
(no silent downgrade); a missing migration hop logs and leaves the file alone instead of
writing a half-upgraded payload. To change a shape: bump the version and add
`@migrations.register("<file>", from_version=N)`, which returns the next version's payload.
Covered by `tests/test_store_migrations.py`.

`services/tab_sets.py` uses that store contract at schema v4. Research workspace rows hold
tab descriptions plus bounded references to existing notes, tasks, saved pages, and cards;
they do not copy those records. The active research workspace ID is a profile preference,
resolved against the collection store before use. v1–v3 collections migrate forward
stepwise.

### Secrets at rest (`core/secret_store.py`)

Credentials do not live in the ordinary preference files. `core/prefs.py` routes the
AI provider key, Google token cache, self-hosted sync token, mobile bridge token and
proxy password through `secret_store`, which keeps them in `secrets.dat`.

- **Windows:** each value is protected with `CryptProtectData` (DPAPI, current-user
  scope). Mei never derives, stores or hard-codes a master key.
- **Other platforms:** the file is written with owner-only permissions (0600) and
  `status()` states plainly that it is not encrypted at rest.
- **Migration is additive:** `adopt()` protects the value, reads it back, and only then
  removes the legacy plaintext. A protection or read-back failure leaves the original
  value in place and exposes a recovery hint; it never clears a working token.
- **Excluded by design:** `secrets.dat` is not part of folder sync, self-hosted sync,
  profile backups or diagnostics. DPAPI blobs are machine/user-bound, so a restored
  profile asks for credentials again instead of carrying them between devices.
- **Log hygiene:** `core/log.py` masks known secret values and recognisable credential
  shapes (bearer tokens, `key=…`, `https://user:pass@`, common provider prefixes)
  before writing the file, so a diagnostics log tail cannot contain a credential.

A profile passcode remains a workspace gate, not full-profile encryption. Do not
describe it as encryption in UI copy or documentation.

---

## 3. Extension points

### Add a new search engine
Edit **exactly one place**: `litebrowser/core/prefs.py` → `SEARCH_ENGINES`.
The address bar, new-tab page, and validation update automatically.

### Add a new theme
Add an entry to `theme.PALETTES` (a color dict with all tokens). No QSS edits needed —
`theme.main_qss()` and `theme.palette_tokens()` both read from the palette.

### Add an accent color
Add a `(base, hover, soft, focus)` tuple to `theme.ACCENTS`.

### Add a slash command
Edit **exactly one place**: `litebrowser/core/commands.py` → append a `Command`.
The omnibar completer, the hint line, the help dialog and the palette are all generated
from that registry, and `tests/test_command_registry.py` fails if the registry and the
documented command list (`docs/COMMAND_REFERENCE.md`) drift apart.

### Change the update channel or release asset
Edit **exactly one place**: `litebrowser/core/product.py`. Every identity string
(`PRODUCT_ID`, `APP_VERSION`, `ASSET_NAME`, channel path) lives there and nowhere else.
A release channel JSON must declare `"product": "mei"`; `update_service.check_for_updates`
refuses a channel that belongs to another product, and refuses an asset whose name is not
`ASSET_NAME`. The installer verifies the download (exists, ≥ `MIN_PACKAGE_BYTES`, `MZ`
header) before it touches the running `Mei.exe`, and keeps a `.bak` with a 15 s watchdog
that rolls back. `tests/test_update_identity.py` covers all of it.

### Ship an update without a server (self-replacing build)
The channel is checked in this order: an explicit URL (tests/tooling) →
`<exe dir>/update/update.json` → `product.DEFAULT_UPDATE_CHANNEL_URL`. So upgrading a
machine that has no release server is: bump `APP_VERSION`, `build_exe.bat`, then
`.venv\Scripts\python.exe tools\write_local_update.py dist` and copy that `dist/update`
folder beside the installed `Mei.exe`. The next launch offers it, verifies it, replaces the
executable (`.bak` + watchdog) and then deletes the old build, the `.bak` and the ~170 MB
copy in `%TEMP%\Mei\updates` — `update_service.cleanup_old_artifacts()` runs on every
startup so repeated updates never grow the disk usage.

### Add an extension user-script with match patterns
`litebrowser/browser/extension_patterns.py` parses the `==UserScript==` header (`@match` / `@exclude`)
of `.js` files in `Extensions/`. Adding a new pattern = edit this module + make sure the inject
loop (`window.py`) calls `should_inject_for_url`.

### Add a data source for self-hosted sync
`sync_service.py` — add **one entry** to `SYNC_ENTITIES` (`key`, report counter, publish, merge).
The bundle, the merge pass and the applied-count report all read that registry, so nothing else
needs editing (`tests/test_store_migrations.py` asserts they cannot drift apart).
Endpoints: `POST {base}/api/sync/push` + `GET {base}/api/sync/latest`. Sample server: README → Self-hosted sync.

### Add a workspace app / AI provider
- Workspace app: edit **`litebrowser/data/chain.json`** (id, name, glyph, subtitle, color,
  `folder`, `remote`) and mirror it to `web_support/chain.json`. `core/app_paths.py` reads
  the packaged manifest first and resolves `folder` against the dev sibling roots, so app
  ids, folders and remote seeds are declared once — there is no hard-coded URL table left.
  `tests/test_chain_manifest.py` checks the registry↔manifest contract.
- AI provider: `ai_service.py` + `ai_window.cmb_provider` (data = key).

### Migrate a module to the Qt façade
Import `from litebrowser.qt import QtCore, QtWidgets, ...` instead of `PyQt5.*`, then drop
the file from `QT5_ALLOWLIST` in `tests/test_qt_facade.py`. That test fails if a module
imports the binding directly outside the allowlist **and** if the allowlist keeps a stale
entry, so the migration can only move forward. Only `qt.py`, `qt_compat.py` and `main.py`
(must set Chromium/GL env vars before `QApplication` exists) may import PyQt5 forever.

The same test also enforces the import **order**: a test module must import `litebrowser`
(which activates the shim) before it imports a Qt binding. PyQt5 and PyQt6 are both
installed here, so importing a binding first pins that file to the *other* Qt runtime
while the app code uses the shimmed one — two bindings in one process, which dies with an
access violation instead of a traceback.

### Add a new indexed data type for AI
`ai_service.collect_docs()` — add the source and the retriever indexes it automatically.

---

## 4. Important flows

- **Startup**: `main.py` → select/ensure profile → `ensure_dual_workspaces` → 2 `AppShell`s.
- **New tab**: `SearchWindow.add_new_tab` → `tab_manager.add_tab` → `get_new_tab_html` (theme-aware).
- **App close**: `closeEvent` saves the session (tabs + recently_closed) → `_auto_save_tab_set`.
- **AI ask**: shell → `ai_window.ask_with_context` → `ai_service.answer_query` (thread pool).
- **Boards**: `PersonalWindow` → `QGraphicsScene` (StickyCardItem + InkStrokeItem + EdgeItem)
  → `life_service.update_board`.
- **The loop** (capture → plan → study → review → reflect): `study_flow.build_flow` reads the
  agenda, the deck, the captures, the pour journal and the link table → `next_step()` names one
  action → `AppShell.open_flow_step` routes it to a workspace (studying starts a `study_session`,
  reviewing opens the deck, capturing selects the note). Home's ▶ Continue, `/flow`, the brief's
  "Next step" line and the planner's study label all read the same function, so the four
  surfaces cannot disagree. Two more readers sit on the same function: `reminder()` (the 60 s
  shell tick, so Mei starts the step instead of waiting to be asked) and `weekly_review()`
  (Home's “This Week” card and the AI's `study_week` document).
- **Slow work never runs on the GUI thread**: `AppShell.run_in_background(work, on_done)` puts a
  callable on the shell's executor and delivers the finished future back through the
  `background_done` signal, so a page can touch widgets again without locking up while a device
  code is being polled or a token refreshed.

---

## 5. Upgrade roadmap

| Item | Status | Notes |
|---|---|---|
| Search engine registry | ✅ Done (5.1) | single source of truth |
| `_format_ts` util | ✅ Done (5.1) | `core/time_utils.py` |
| Boards node-edge link | ✅ Added (5.1) | Link mode + EdgeItem |
| Rename "sync-ready" → local snapshot | ✅ Done (5.1) | honest UI |
| Merge Guide/Control Center | ✅ Ready | only one `show_browser_control_center` |
| Password manager export/import | ⏳ Not yet | depends on `cryptography` |
| Update channel ownership (P0) | ✅ Done | `core/product.py` + product-tagged metadata + verified install/rollback |
| Serverless self-update + old-build cleanup | ✅ Done | `<exe dir>/update/` channel + `cleanup_old_artifacts()` |
| Single chain manifest (P1) | ✅ Done | `litebrowser/data/chain.json` → `core/app_paths.py` |
| Command registry (P2) | ✅ Done | `core/commands.py`, every surface generated |
| Layer boundaries + no dead API (P3/P6) | ✅ Done | `test_architecture_boundaries.py`, `test_capability_ledger.py` |
| Versioned stores + migrations (P4) | ✅ Done | `core/store.py`, `core/migrations.py` |
| Qt façade for PyQt6 (P5) | ✅ In progress | `litebrowser/qt.py`; allowlist shrinks file by file |
| Standardize 3 tab-set types | ⏳ Not yet | Search/Personal/AI differ slightly |
| Morning Brief (6.0) | ✅ Done | `brief_service.py` + Home card + `/brief` |
| AI Agent actions (6.0) | ✅ Done | `/agent summary/tasks`; `/agent review` (6.2) |
| Tab groups by domain (6.0) | ✅ Done | assign group + `group:` filter + `/group-tabs` |
| Semantic retrieval (5.5) | ✅ Done | cosine blend when Ollama, BM25 fallback |
| Extension match pattern (5.5) | ✅ Done | `extension_patterns.py` |
| Self-hosted sync (6.2) | ✅ Done | `sync_service.py` + Settings card + sample server |
| Planner & flashcards on every surface | ✅ Done | backup/sync/AI index/search/brief all read the study stores |
| Course UI + time-block editing | ✅ Done | Weekly Plan course card, course pickers, block edit dialog |
| Unified Home agenda | ✅ Done | `life_service.today_agenda` → Home “Today” card |
| Study sessions with credited minutes | ✅ Done | `study_session.py` + `focus_service` item sessions (planner store v2) |
| Two-way entity links | ✅ Done | `link_service.py` (`entity_links.json`) + note Related panel |
| One loop, one recommendation | ✅ Done | `study_flow.py` → Home ▶ Continue, `/flow`, brief next step, planner study hint |
| Inbox → planner promotion | ✅ Done | `study_flow.promote_task` + Home “→ Planner” (keeps the task↔item link) |
| Proactive study reminders | ✅ Done | `study_flow.reminder` → `AppShell._check_study_reminder` → tray toast; gap in prefs, quiet hours in the loop |
| Weekly reflection card | ✅ Done | `study_flow.weekly_review` / `review_line` → Home “This Week” + AI `study_week` doc |
| AI reads the browser page | ✅ Done | `ai_window` “👁 Read my browser”: current page text + open tabs as untrusted context |
| Background work relay for pages | ✅ Done | `AppShell.run_in_background` + `background_done` signal (Google sign-in, token refresh) |
| Loop memoization (perf) | ✅ Done | `study_flow._memoized`: 1 s TTL + store signature, `reset_flow_cache()` for writers |
| Tab Groups drag-drop + Split view | ⏳ Not yet | needs GUI testing (pure Qt UI) |
| Chromium engine upgrade (PyQt6-WebEngine 6.9/6.10) | ⏳ Not yet | big migration, needs GUI regression |

---

## 6. Quick checks

```bat
cd /d "D:\Code folder\new browser\new browser"

REM full test suite (headless — no GPU/display needed)
set QT_QPA_PLATFORM=offscreen
set PYTHONDONTWRITEBYTECODE=1
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q --no-header

REM lint the layer rules
.venv\Scripts\python.exe -m ruff check --select F401,F811,F841 litebrowser tests

REM run the app
.venv\Scripts\python.exe browser.py
```

The suite includes the architecture gates (`test_architecture_boundaries.py`,
`test_capability_ledger.py`, `test_qt_facade.py`), the product/update identity tests
(`test_update_identity.py`), and the store/migration tests (`test_store_migrations.py`),
so a green run is the contract this document describes.
