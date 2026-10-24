# Capabilities & the reserved API

This file is the **ledger** for one rule: public API in `litebrowser/` either has a
caller somewhere in the repo, or it is listed here as *reserved* and covered by
`tests/test_reserved_api.py` — otherwise it gets deleted.

Two gates enforce it:

| Gate | Test | What it fails on |
|---|---|---|
| No dead public API | `tests/test_capability_ledger.py` | a public `def`/`class` in `litebrowser/` with no reference anywhere in the package or the tests |
| Reserved API stays honest | `tests/test_reserved_api.py` | a promoted/renamed/removed reserved function, or a behaviour regression in one |

The point of the pairing is that "we kept it for later" is a decision with a test
attached, not a comment nobody re-reads. Adding an entry below is the *only*
accepted alternative to deleting the code.

---

## 1. Live wiring (has a desktop caller)

| Capability | Single source of truth |
|---|---|
| Product identity, version, update channel, asset name | `core/product.py` (re-exported by `core/app_version.py`) |
| Update check / download / verify / install | `services/update_service.py` → `ui/app_shell.py` |
| Slash commands (completion, hints, help dialog) | `core/commands.py` → `app_shell.py`, `ui/dialogs/navigation.py`, `ui/dialogs/shell_palette.py` |
| Bridge action advertising | `services/android_bridge_service.py` (`API_VERSION`) |
| Workspace/chain apps (7 apps: LinkLumina, Management Hub, MAS, World Leaderboard, PersonalFrequency, Fortune & Reflection, Hub) | `litebrowser/data/chain.json` → `core/app_paths.py` |
| Search engines | `core/prefs.py` → `SEARCH_ENGINES` |
| Themes / accents | `ui/theme.py` → `PALETTES` / `ACCENTS`; the *resolved* (auto day/night) mode comes from `core/prefs.py` (`resolved_auto_theme`, `theme_data.is_night_theme`) |
| Web pages following the shell's light/dark mode | `core/prefs.py` (`effective_force_dark_web`) → `browser/browser_page.py` (`ensure_forced_dark_script`), re-applied on a theme flip by `ui/main_window/window_topbar.py` (`refresh_chrome_theme`) |
| Morning-brief greetings | `core/greetings.py` (shared by `browser/new_tab_page.py` and `services/brief_service.py`) |
| Versioned profile stores | `core/store.py` + `core/migrations.py` → `personal_plan` (v2), `tab_sets`, `entity_links` |
| Sync entities | `services/sync_service.py` → `SYNC_ENTITIES` (incl. planner, flashcards, entity links) |
| Study data on every surface | planner + flashcards flow through backup (`history_service`), sync, the AI index (`ai_service.collect_docs`), library search (`life_service.search_everything`) and the Morning Brief (`brief_service`) |
| Course lifecycle + block editing | `personal_plan.create_course` / `update_course` / `delete_course` / `update_time_block` → Weekly Plan UI (`ui/personal_window.py`) |
| Study sessions | `services/study_session.py` → PersonalWindow “▶ Study”; minutes are credited to the item once |
| Entity links (two-way) | `services/link_service.py` (`entity_links.json`) → note “🔗 Link…/Unlink” panel; backlinks are the same rows read in reverse |
| Unified Home agenda | `life_service.today_agenda` → Home “Today” card (planner deadlines + quick-task inbox) |
| The study loop (one next step) | `services/study_flow.py` → Home “▶ Continue”, `/flow`, the brief's `next_step` line and the planner study hint |
| Inbox → planner promotion | `study_flow.promote_task` → Home “→ Planner” (task and item stay linked) |
| Proactive study reminders | `study_flow.reminder` → `AppShell._check_study_reminder` (60 s tick) → `system_notify` toast; gap from `prefs.get_study_reminder_minutes`, Settings combo |
| Weekly reflection | `study_flow.weekly_review` / `review_line` → Home “This Week” card (spark, streak, skipped rows) and the AI index (`study_week` doc) |
| Term settings | `personal_plan.update_plan_settings` → Weekly Plan “⚙ Semester” dialog |
| Google sign-in | `google_auth.sign_in_via_device_code` / `ensure_valid_token` + `prefs.get/set_google_token_cache` → Settings “Google account” card (background thread, `AppShell.run_in_background`) |
| Passcode re-lock | `security.lock` → Settings “Lock now” |
| Watched pages management | `page_monitor.remove_monitor` → Settings “Watched pages” card |
| Tab-set rename | `tab_sets.rename_tab_set` → Tab Sets dialog “⋯ More → Rename…” |
| Workspace rename | `workspace_manager.rename_workspace` → Manage Workspaces dialog “⋯ More → Rename the selected workspace…” (double-click also renames) |
| One action per dialog | `ui/dialogs/common.py::dialog_footer` + the Primary/Ghost/Quiet/Danger roles → every dialog footer, `theme.py` §6.7 |
| Background work relay | `AppShell.run_in_background` → `background_done` signal → page callbacks on the GUI thread |
| Loop memoization | `study_flow._memoized` (1 s TTL + store signature) → `reset_flow_cache` for callers that must see a write immediately |
| Brief markdown export | `brief_service.brief_markdown` → Home “📝 Save as note” |
| Release integrity | `update_service.file_sha256` / `verify_package(expected_sha256)` → the manifest `tools/publish_release.py` (and `tools/write_local_update.py`) writes, verified after every download; `publish_release.verify_web_support_zip` re-checks the shipped site archive before upload |
| Packaged startup check | `litebrowser/main.py` (`--smoke-test`) → the release workflow, using a throwaway `LITEBROWSER_DATA_DIR` and requiring the `MEI_SMOKE_MARKER` written after both shells are shown |
| Anki deck files | `services/anki_service.py` (`import_package`, `export_package`) → Review page **⋯** menu (Import an .apkg / Export as an Anki deck); reads `collection.anki2` and the zstd `collection.anki21`/`anki21b` through whichever decoder exists (`zstandard`/`pyzstd`/`zstd`), writes a legacy package Anki imports, with interval and ease carried both ways |
| Credentials at rest | `core/secret_store.py` (`adopt`, `get_secret`, `set_secret`, `status`) → `core/prefs.py` for the AI provider key, Google cache, sync token, mobile bridge token and proxy password; DPAPI on Windows, owner-only file elsewhere; `secrets.dat` is excluded from backup, sync and diagnostics |
| Log credential redaction | `core/log.py` (`redact`, the file-handler filter) → every logger under `litebrowser`; masks known secret values and bearer/API-key/password shapes before the bytes reach `mei.log` |
| Diagnostics bundle | `services/diagnostics.py` (`build_bundle`, `versions_payload`, `profile_inventory`) → Settings “Diagnostics” card (Export zip / Open log folder); carries the redacted log tail, component versions and store shapes, never note text, passwords, `secrets.dat` or history |
| Which engine is running | `services/diagnostics.py` (`engine_notice`) → the same Settings card, painted by `_refresh_engine_notice()`; names Chromium + Qt + binding and cautions on the old branch (Qt 5.15 = Chromium 87). The same facts are printed by `tools/engine_report.py` on every CI run, and the versions are pinned in `pyproject.toml` (`qt6 = PyQt6==6.11.0`) |
| Release channel | `product.DEFAULT_UPDATE_CHANNEL_URL` (`releases/latest/download/update.json`) → `update_service.check_for_updates` → Settings “Updates” card; `product.RELEASES_PAGE_URL` → “Open release page” |
| The desk (Home's four blocks) | `services/desk_service.py` (`build_desk`, `block_by_key`) → `ui/shell/pages.py` (`HomeDashboardPage._desk_section` / `_refresh_desk`), the desktop caller for every block |
| Search that reaches your content | `ui/dialogs/shell_palette.py` (`search_entries`, `content_entries`, `CONTENT_*`) over `life_service.search_everything` + `personal_service.list_notes` → `AppShell._show_feature_popup` (rows) and `_execute_shell_palette` (routing through `open_library_item`) |
| Study-session ritual | `services/study_ritual.py` (`POURS`, `start_ritual`, `last_pour`, `ritual_line`) → Home ☕ *Study session* (`ui/dialogs/study_ritual.py`); onboarding step 1 saves the usual cup |
| Weather / time-of-day themes | `core/theme_data.py` (`rain-day`, `rain-night`, `sunrise-day`, `autumn-day`) + the auto pairs in `core/prefs.py` (`resolved_auto_theme`) → the Settings theme picker, `/theme`, onboarding |
| Folder sync (two-way, no cloud) | `services/sync_folder.py` (`compute`, `sync`, `status`, `summary_line`, `set_folder` / `get_folder`, `device_id`) → Settings **Folder sync** card (choose folder / Preview / Apply); three-way merge against `sync_folder_state.json`, backup on every write, and writes only the stores that actually differ |
| Declarative plugins | `services/plugins.py` (`load_plugins`, `run_plugin`, `report_line`, `Plugin`) + the shipped manifests in `litebrowser/data/plugins/*.json` → Settings **Plugins** card (list, run the selected one, open the folder); a manifest declares fields and a target store, it never runs code |
| Phone → desktop ingest | `services/android_bridge_service.py` (`SUPPORTED_ACTIONS`, `dispatch_ingest`) → the bridge's `POST /api/mobile/ingest`; `save_selection` writes the selection the extension or the phone sent as a note, a card or a saved page |
| Desktop → phone read | `android_bridge_service.desk_for_phone` (`GET /api/mobile/today`, `?day=`) over `desk_service.build_desk` → MeiRemote; read-only, advertised in `/api/mobile/capabilities` under `read` |
| Browser-extension door | `android_bridge_service._extension_origin` + the CORS headers in `end_headers` / `do_OPTIONS` → the unpacked `Extensions/tab-window-bridge` v1.2 (send this tab / send this selection); a web page gets no readable answer even with the token |
| One pairing code, two parsers | `android_bridge_service.pairing_code` / `parse_pairing_code` → Settings **Quick pairing** (MeiRemote and the extension); `Extensions/tab-window-bridge/bridge.js` mirrors the same rules and `tests/test_extension_bridge_js.py` compares the two parsers on the same strings |
| Qt binding selection | `litebrowser/qt.py` over `qt_compat.py` |

## 2. Reserved API (reachable, no desktop caller yet)

These exist in the data/service layer, are reachable from the phone bridge, the sync
bundle, or a future UI, and are intentionally *not* dead:

| Capability | API | Reachable from | Why kept |
|---|---|---|---|
| Management Hub support URL | `app_paths.cuc_quan_ly_support_url` | — | Resolves the bundled copy's `index.html`; wired when the packaged copy is missing |

The Google, planner-settings, rename, monitor-removal and passcode rows that used to
live here were promoted into §1 (Settings, the Weekly Plan header, the Tab Sets dialog
and the Manage Workspaces dialog) — the ledger only shrinks.

## 3. Promoting or dropping an entry

**Promote** (wire it into a dialog): keep the implementation, add the caller, then
remove the row from §2. `tests/test_reserved_api.py` still covers it, so both gates
keep passing — the ledger only shrinks.

**Drop** (no longer wanted): delete the function *and* its `test_reserved_api.py`
coverage in the same change. `tests/test_capability_ledger.py` fails the moment an
unreferenced public `def` survives without a ledger entry, so a half-finished
removal cannot land.

> Deleting `tests/test_reserved_api.py` coverage without deleting the code is the one
> mistake this file exists to prevent: the ledger test would then report the function
> as dead API.
