# Mei Tea Room Edition

Mei (formerly Mei Cafe Edition) is a multi-workspace desktop shell built on `PyQt5`/`PyQt6` + `QtWebEngine` (it runs on both through the `litebrowser/qt_compat.py` shim; when PyQt6-WebEngine 6.8 → Chromium 122 is installed it uses that), not just an ordinary browsing window.

> **Run & build the desktop app**: see the dedicated **`RUN_AND_BUILD.md`** — app testing checklist, how to use `.venv`, common run errors, and the full PyInstaller command (`--collect-all PyQt6.QtWebEngine*`) to produce the `.exe`.

> ## Accessibility polish
>
> - **Profile-scoped reduced motion** — Settings → Interface → Motion can follow the Windows client-area animation setting, reduce Mei's nonessential motion, or allow it. Reduced motion removes animations from Mei's new-tab page and makes tab-desk collapse immediate; websites keep their own presentation. The setting is profile-local and does not affect browser content.
> - **Universal Quick Capture** — `/capture` opens a review-first form for a note, task, saved link, or manual flashcard. It can prefill the active page title, URL, and selected text; private tabs are detected and their contents are never copied into the persistent profile. Captures use Mei's existing stores and route to the saved item.

> ## Next Horizon — research, personalization, and theme families
>
> - **Research workspaces** — Browser → Options → Sessions & Spaces → **Save Research Workspace…** stores a named tab collection with references to an existing note and task. These references do not duplicate their records. Saving excludes incognito tabs and fails closed when a tab's privacy state cannot be verified. Restore defaults to merging; replacing the current browser workspace is explicit, confirmed, and leaves tabs available through Reopen Closed Tab.
> - **Per-profile Home layout** — **Customize Home** lets users reorder, hide, or change the content height of the four Home desk cards. Reset touches only the dashboard preference.
> - **Capture → organize → ask → focus** — Saving/restoring a research workspace selects the profile's active Research desk. Home shows linked records and routes to resume, capture, or ask AI. Quick Capture links new notes, tasks, saved pages, and flashcards back to the active desk. Ctrl+K finds named research workspaces. AI context is opt-in, off by default, visibly disclosed, bounded, and presented as untrusted; incognito page contents are excluded.
> - **Fifteen additional palette families** — Aurora Glass, Sakura Twilight, Cyberpunk Neon, Midnight AMOLED, Arctic Aurora, Forest Sanctuary, Ocean Depths, Retro Terminal, Paper Studio, Monochrome Pro, Sunset Dusk, Dreamscape, Solarized Focus, High Contrast, and Glasshouse. They use the same complete palette token contract as the café themes and apply through the existing theme engine. Glasshouse uses opaque surfaces to preserve legibility across Qt platforms.
> - **Versioned tab-set store v4** — Existing v1–v3 files migrate stepwise; collections without related items remain unchanged, and linked-item identifiers are bounded and normalized.
> - **Verification** — Full Python suite: **889 passed, 1,035 subtests passed**; focused research-desk integration suite: **86 passed, 114 subtests passed**; Ruff and `compileall` passed. An offscreen startup smoke reached “Mei ready” in 2.69 seconds and remained live through a 14-second observation. A cross-binding run, packaged executable build, and installer check were not performed in this pass.

> ## Milestone 1.0.0.0 Alpha — one desk, two directions, open doors
>
> The first Alpha is where Mei stops describing itself as a browser and starts being the *one tidy window* it always was: everything in one place, reachable in one box, with a place to sit down — and a door out to everything that is not this app: the browser you are already in, your phone, the folder you already sync, the CSV your old task app exports.
>
> **The desk (1 of 3)**
>
> - **Home is a desk, not a menu.** It used to open on a grid of nine launcher tiles plus a row of stat tiles — a list of what the app *can* do, and never an answer to what to do *now*. Home now opens on four blocks, computed by the new `services/desk_service.py` from stores that already exist (no new file, nothing to migrate): **Today** (planner deadlines, today's focus blocks, quick-inbox rows), **Due** (anything late or landing inside a week, plus the cards owed), **Unfinished** (items with minutes already poured into them, and the page you were mid-way through), and **Next step** (the loop's single recommendation, with **▶ Continue** and **☕ Study session**). The launcher grid and the quick-command chips are not gone — they moved behind **☰ All features**, collapsed by default, because browsing the app is a click and working in it should be the default. `tests/test_desk.py` pins the rules (late work belongs in *Due*, 40 days out is not *due*, a half-studied item is still on the plate) and the page (four blocks present, launcher hidden until asked for).
> - **The search box reaches your work, not just the app.** The omnibar (Ctrl+K) already jumped to any workspace, page, site or command; it now also finds *your* records — notes, cards, planner rows and courses, focus blocks, tasks, calendar events, boards, saved pages — through `search_entries()` in `ui/dialogs/shell_palette.py`. Features stay first so a feature word still lands on the feature, content follows so "jump to Notes" stops being the only thing a search box can do, and a result routes to where the item lives rather than to a workspace. One letter does not dump the profile (two characters minimum), and an unreadable vault cannot empty the box.
> - **A ritual to start a pour.** `services/study_ritual.py` turns "start a timer" into a decision worth making: every cup on the menu *is* a pace — Cà phê đen 25, Trà sen 25, Cà phê sữa 45, Trà đào 45, Bạc xỉu 50, Nước cam 15 — so choosing a drink chooses the length, the last choice is remembered, and the one line you type about what you will finish rides into the session label. It writes the app's own focus session (so the status strip, the focus journal and the weekly review all count it), one history line and one preference; the dialog (`ui/dialogs/study_ritual.py`) prefills the loop's next step as the default thing to finish.
> - **Four more cafés: weather and time of day.** *Rainy Day / Rainy Night* (grey light through a wet window, then late drizzle), *Sunrise* (first light, the 5 a.m. shift) and *Autumn Table* (amber and spice). Each night half is registered in the auto day/night pairs as its own key, so choosing **Rainy Night** and leaving auto on cannot quietly slide back to a different night theme. Themes: 16 → **20**. `tests/test_theme_batch2.py` pins labels, palette resolution and that pairing; key parity for every palette stays in `test_modernization`.
>
> **Two directions: the profile travels, and the phone can ask (2 of 3)**
>
> - **Folder sync — the profile in a folder you already carry.** Settings → **Folder sync** points Mei at any folder (OneDrive, Dropbox, a USB stick you actually move) and merges the two sides through `services/sync_folder.py`. The merge is three-way against a baseline (`sync_folder_state.json`), not "newest file wins": a record edited on either side is carried over, a record deleted on one side is deleted on the other — *unless* the other side edited it, in which case the edit wins and the record comes back (`conflict_resurrect`). Two different edits to the same record are kept as a conflict rather than one silently overwriting the other, and re-running a merge that is already converged changes no file at all — including the copy in the shared folder. Eight stores travel: quick tasks, calendar, idea boards, saved pages, the weekly planner, the deck, entity links and notes. A folder Mei cannot read or write is reported instead of half-applied; **Preview** computes the whole plan and writes nothing; **Apply** snapshots the affected stores into `backups/sync-<stamp>/` first, then writes only the stores that actually differ.
> - **The phone can ask, not only send.** The bridge was receive-only: a phone could push a link and never read what was on the desk. `GET /api/mobile/today` (optional `?day=YYYY-MM-DD`) now answers with exactly the desk Home opens on — the same four blocks out of `desk_service.build_desk`, the headline and pulse lines, the loop's next step, and the four numbers a widget prints (on the plate, waiting, left open, cards due). It is read-only by construction (`tests/test_bridge_today.py` fails if a single file in the profile changes), it sits behind the same bearer token, and a junk `?day=` falls back to today instead of reaching `datetime.strptime` and becoming a 500.
> - **What this line still owes:** the signed **MeiRemote** APK (the Kotlin/Compose app lives in its own repository, and signing needs a keystore that stays with its owner) and an installer refresh. Neither changes what this build does on the desktop.
>
> **Open doors: the extension, the selection, the plugin manifests (3 of 3)**
>
> - **The browser extension talks to Mei instead of to a file.** `Extensions/tab-window-bridge` **v1.2** (Manifest V3) pairs with the same one-line code as the phone — `MEI1|host|port|token` from Settings → **Quick pairing** — and then sends the current tab (**Send this tab to Mei** → `save_page`) or the text you highlighted (**Send selection**: note, flashcard or saved page, tags included) over `POST /api/mobile/ingest`. The JSON/ZIP export of a whole multi-monitor workspace is untouched, for the machines where Mei is not running at all. Three things make that door safe to leave installed: the token is still required; CORS is answered **only** to a `chrome-extension://` / `moz-extension://` / `safari-web-extension://` origin, with the Origin rebuilt from scheme+host before it is echoed back (`do_OPTIONS` answers 204 for an extension and 405 for the web, so a page cannot even preflight, and the 401/404 replies still carry the header so the extension can read *why*); and the extension rewrites the pairing code's LAN address to `127.0.0.1`, because it runs on the same machine — nobody has to open the bridge to the network for it.
> - **`save_selection` is a real action, and the two tag conventions stay apart.** A selection becomes a note in *Clippings* with a `Source: <url>` line and `# tag` lines, a saved page, or — for the deck — a flashcard whose tags follow Anki's rules (`#networking`, no space), matching what the `.apkg` importer already wrote. An empty selection is refused with a message instead of leaving an empty record behind, and `save_page` / `save_selection` are advertised in the capability list so a client can negotiate.
> - **Plugins declare; they do not run.** Settings → **Plugins** lists the manifests in a profile's `plugins/` folder — a `plugin.json` with `api: 1`, a `kind` (`importer` / `exporter`), a target store (`tasks`, `notes`, `cards`, `saved_pages`), a field map and its options. Four ship in the box (`litebrowser/data/plugins/`): Todoist CSV and TickTick CSV in, notes→CSV and deck→CSV out, and the reader sniffs tabs vs commas and tolerates a BOM because the files come from other people's exports. A manifest that fails to load never breaks the page: it lands in the card's *problems* line with its reason, and loading never raises. There is deliberately **no** plugin kind that executes code.
> - **One pairing code, two parsers — compared on every run.** The extension parses the code the desktop prints, so `tests/test_extension_bridge_js.py` runs the JavaScript parser and `android_bridge_service.parse_pairing_code` over the same twenty strings — including a real code generated from a profile — and fails if they ever disagree. Writing it tightened the rules on both sides: a host carrying a slash, backslash, comma or space, a port outside 1–65535, or an over-long token is now refused by both. The extension's helpers have their own dependency-free Node harness (`tests/js/bridge.test.js`, 20 checks) over pairing, envelopes, tag handling, reply wording and every fetch path that matters: a 401, an unreadable body, a dead bridge, a fetch that throws, and a hung bridge that has to become a sentence instead of a spinner.
> - **Not in this Alpha, on purpose:** cards staying inside notes (the store shape is unchanged), plugins that execute code, and Quizlet-style review. The deck, the planner, the notes and the vault keep the format 0.7.1.0 wrote.
> - **The engine under the tabs is 18 versions newer.** Chromium **122 → 140** (PyQt6-WebEngine 6.8 → 6.11), measured before it was adopted rather than after: the suite (then 785 tests) passed on the new engine in two environments, and an app-level smoke of 24 facts that the suite cannot see — the request interceptor still being called by the engine, ads still blocked, force-dark still injecting or standing down as documented, downloads, profile paths, the UA spoof, two pages at once on one profile — passed 24/24. What that smoke was built for is now a tool (`tools/engine_smoke.py`, no network needed), the packaged-exe check is a tool too (`tools/engine_exe_smoke.ps1`: is the engine actually up, and in what shape), and `tools/engine_report.py` prints the engine on every CI run so a green build can no longer be a green build on an unknown Chromium. The engine is **pinned** — in `pyproject.toml` (`qt6 = PyQt6==6.11.0`, PyQt6-WebEngine==6.11.0) and in the CI matrix — because an unpinned install quietly becomes a different browser: that job used to test whatever PyPI published that morning.
> - **Settings now says which engine you are running.** Chromium, Qt and the binding appear in the Diagnostics card (`diagnostics.engine_notice`), and a build on the old branch gets a caution with the way out — Qt 5.15 is Chromium 87, and the number is worth showing instead of hiding in an exported zip. This is the fact the whole settings surface was silent about.
> - **A version the new engine exposed.** The Chrome-shaped client hints sent to sign-in hosts carry a full build number, and they used to read it out of the engine's user agent. Qt 6.8's UA says `Chrome/122.0.6261.171` — a real build. Qt 6.11's says only `Chrome/140.0.0.0`, which is shaped like a build and is not one, so the header Google reads would have claimed a version that never existed. The binding is now asked first (`qWebEngineChromiumVersion()`, no application object needed) and the user agent is only the fallback; `tests/test_engine_visibility.py` pins both, including the reduced-UA case that made this necessary. On PyQt5 there is no such function at all, which is exactly why the fallback stays.
> - **A long-standing "unstable on Windows" note, located.** Writing the test above hard-crashed the suite: touching `QWebEngineProfile.defaultProfile()` late in a run that has already built and torn down GUI tests takes Qt 6.11 down with it, and the old docstring's caveat ("when called before a QApplication exists") was only half the story. PyQt6 never reaches that path — the binding answers — so the crash is gone from the suite in the honest way: the user-agent parsing became a pure function (`_ua_chrome_versions`, string in, version out) whose rules are covered without asking Qt anything, and the profile is read once, only on the branch that has no binding to ask.
> - **A theme that only half-followed itself.** `theme.palette()` resolved the *palette* and ignored the accent, while the shell stylesheet was built with `prefs.get_accent(profile)` — so every hand-painted surface (both dashboard charts, the focus heatmap, the idea boards) drew the palette's **stock** accent. On a `cafe-night` desk with the **rose** accent, the window's buttons, chips and active nav row were rose while the “Your Week” bars were the theme's own gold: the same app in two colours, reported from a screenshot. `theme.palette()` now defaults the accent to the profile's (and takes a `base_dir`, for a widget that belongs to another profile), and chart bars use `theme.accent_bar_color` — the accent's own hue at reduced opacity — instead of the `ACCENT_SOFT` token, which is a *button background* (deliberately near-black on night palettes, a paper tint on light ones) and read as mud as a fill. The next question after that fix is the one the screenshot actually asked — *when night falls while the window is open, does this widget follow?* — so the test renders the same dashboard twice, at 10:00 and again at 22:00, and fails if a widget keeps painting a palette it resolved once; checked against the wound, not just the fix.
> - **“Your Week” was a day late, and today was always empty.** The chart bucketed visits with `(midnight_today - ts) // 86400`; a visit made today lands *after* midnight, so that subtraction is negative and floor-divides to −1, and every one of today's visits fell out of the window. The week from the report read Thu 40 / Fri 9 / today 30 and the chart drew Fri 40 / Sat 9 — the “9 pages **yesterday**” line in the morning brief was what gave it away. The chart and the `/review` Weekly Review note (same formula, same bug) now bucket by calendar day, so a visit counts on the day it happened.
> - **Audit stabilization and Study Café polish (unreleased).** Profile read/modify/write transactions, atomic bounded backup/restore, safer sync and password origins, concurrent-note draft preservation, private-workspace lock cleanup and save-before-close checks now protect the local-first workflow. Home puts the next action first; responsive cards, collapsible note tools, note deep links and onboarding fixes reduce friction on smaller windows. Android bridge contracts and extension timeouts are hardened; the signed phone app remains outside this checkout.
> - **English interfaces and bundled web reliability (unreleased).** Desktop, café drink labels, extension messages, Management Hub screens and the seven-app launch manifest are English; saved content, proper names and legacy storage paths remain unchanged. MAS rejects blank check-in scores without losing drafts; LinkLumina waits for committed writes. Management exports support all 84 scope/mode/format combinations and validate/roll back backup restoration. File-catalog wording now explicitly states that metadata, not file contents, is stored. Final local verification: **863 Python tests, 749 subtests**, 32 LinkLumina tests, 11 MAS test files, 19 native journeys and 24 engine checks; no API keys, deployment or release operations were used. See [the audit report](reports/product-audit.md).
> - **Final audit hardening (unreleased).** Management catalog/graph rendering escapes imported content, preserves unreadable stores and failed-save drafts, refreshes across tabs and respects reduced motion. World Leaderboard validates profiles and bounds scores; MAS rejects late replies belonging to replaced sessions. Folder Preview is asynchronous, note-move failure recovery retains resolvable references, and public web copy/release ZIP filtering excludes private payloads. Generated bundle cleanup fails closed if stale private files cannot be removed; source assets/vendor exceptions support a future clean-checkout build without exposing keys. The engine-smoke harness now flushes page/profile deletion in order and exits cleanly.
> - **Version** 0.7.1.0 → **1.0.0.0**, published as a GitHub **pre-release** so `/releases/latest` — the channel the ordinary self-update reads — keeps serving the last stable build until the Alpha is promoted. **811 tests, 744 subtests.**
>
> ## Milestone 0.7.1.0 — the deck travels to Anki, and a failure can be sent
>
> - **Decks are no longer trapped in one app.** The Review page's **⋯** menu imports an Anki `.apkg` and exports this deck back to one. Import reads Anki's own SQLite collection — the legacy `collection.anki2` and, when a decoder happens to be available (`zstandard`, `pyzstd`, or a `zstd` binary; Mei ships none), the zstd `collection.anki21`/`anki21b` that Anki 2.1.50+ writes, and without one the error *names the install* instead of showing a decompression traceback. Field 0 becomes the front and the rest the back, as plain text (`<br>` → newline, `<img>`/`[sound:…]` dropped, Anki tags appended as `#tag` lines); Anki's `ivl` and `factor` restore interval and ease, so a deck that was already studied keeps its schedule — but every imported card is due now, because Anki's `due` counts days from *its own* collection creation and guessing it would schedule a deck years out. Re-importing the same package adds nothing (same front+back are counted as duplicates), a note with no answer is skipped and counted, and media files are counted and reported rather than silently dropped. Export writes a legacy package Anki still imports — a `Basic (Mei)` model, the deck name, and the scheduling carried out (`services/anki_service.py`, `tests/test_anki_deck.py`). `tests/test_deck_ui.py` pins the part a service test cannot: that the menu is really inside the page, which is the exact bug that once left the Google card's **Sign out** wired and invisible.
> - **When something breaks, the evidence travels.** Settings gained a **Diagnostics** card: *Export diagnostics zip* writes one small archive with the log tail, component and Qt versions, the platform, and the *shape* of every store — sizes, migration versions, record counts, never note text, passwords, cookies or history — plus *Open log folder* for the log itself (`services/diagnostics.py`). The rule is enforced rather than promised: `tests/test_diagnostics.py` seeds a note and fails if its body ever appears in the bundle.
> - **CI says what failed, and stops depending on the clock.** A red run used to report nothing but `tests · PyQt5 failed` (reading a job log needs a token), so the pytest output is now teed into a file and the failing test ids and the summary are echoed as **check-run annotations**, which are public. The first thing it caught was a time-zone bug in the suite itself: the weekly-review fixture seeded a 30-minute pour at "now", which at 00:19 on a UTC runner *starts* the previous day — and the journal files a pour under the day it started — so the one-day window counted zero while the same suite was green in UTC+7. Pours are now anchored inside their own day, a regression test pins the midnight case at any hour, and the action majors moved to `checkout@v5`/`setup-python@v6` to drop the Node 20 deprecation warnings. The same trap caught the accent assertions a milestone later — green at 23:xx here, red at 06:2x UTC — so the clock-sensitive modules now run **both** halves of the day on every CI run (`tools/run_at_hour.py 10` and `tools/run_at_hour.py 22`) instead of waiting for a runner six hours away to find it.
> - **Version** 0.7.0.0 → **0.7.1.0.**
>
> ## Milestone 0.7.0.0 — the loop speaks first, and the AI reads your browser
>
> - **Mei starts the recommendation, not just answers it.** A 60-second shell tick asks `study_flow.reminder()` whether anything is worth a native toast: an overdue deadline, today's block, due cards — or a day with nothing poured. Three restraints live in the loop (never during a running pour, quiet 22:00–08:00, one nudge per gap) and the gap is a Settings choice (“Off” … “every 8 hours”, default 2 h). The alive-tab tray toast that already carried downloads, eye breaks and routines finally carries the study loop.
> - **Reflect, with numbers.** Home gained a **This Week** card: a 7-day text spark (`▁▂▃▅`), minutes poured, days studied, streak, and the governance half — the up-to-five rows that got *nothing* this week, worst first ("overdue 3d", "never studied"). One click turns the reflection into the action (`▶ Study the oldest one` → the same `study_session` the loop would start), and the same digest ships as the AI index's `study_week` document, so `/ask how much did I study this week?` answers from the surface you just read.
> - **The AI can look at your browser.** A new **👁 Read my browser** toggle (on by default, saved with the provider) attaches the page you are reading — real `innerText`, up to 9 000 chars, labelled *untrusted* — plus the list of open tabs to every question asked from the AI workspace, so “what is this page about?” no longer needs the inline panel. Local Ollama vision (Capture tab) stays exactly as it was.
> - **Five reserved capabilities became real UI.** The ledger's §2 shrank to one row: **Google sign-in** (device code + cached refresh token + “Verify token”, all on a worker thread through the new `AppShell.run_in_background` relay), **planner term settings** (Weekly Plan → “⚙ Semester”, name + start/end dates), **passcode “Lock now”**, **watched-pages removal**, and **renames** for workspaces and tab sets. `docs/CAPABILITIES.md` §1 documents the wiring; nothing was kept “for later” without a screen.
> - **One calm action per dialog.** Dialogs used to end in five to seven look-alike buttons, so the verb the dialog existed for was indistinguishable from “Delete everything” two pixels away. Every footer is now built by `ui/dialogs/common.py::dialog_footer`: one accent-filled **primary** (which also takes Enter), at most two secondary ghosts, a subdued Close, and one **“⋯ More”** menu holding the occasional verbs — history cleanup, bookmark import/export, tab-set rename/delete, workspace rename/remove, VPN leak test and the public proxy list, profile create/delete, vault file chores. The four roles (Primary/Ghost/Quiet/Danger) are painted once in `theme.py` §6.7 and reach both the full workspace and every modal; `danger_button` keeps **Disconnect** visible in the VPN hub where people hunt for it. The hub pages follow the same rule: Idea Boards' eleven boxes became one verb + three mode chips + a menu, and row chores on Tasks, Calendar, Idea Boards and the Weekly Plan became glyphs. `tests/test_dialog_verbs.py` (10 tests) keeps a dialog from growing back into a wall, and `tests/test_promoted_api.py` now fails on a control that was wired up but never added to a layout — the Google card's own **Sign out** and **Set client ID…** were left behind as exactly that when their verbs moved into the menu.
> - **Performance: the loop is memoized, not recomputed.** `study_flow.build_flow` / `next_step` / `weekly_review` were ~20 ms of JSON parsing for a 200-note profile, and Home, the brief, the planner hint and the AI index each asked for them on every refresh — on the GUI thread, in the middle of a click. They now share one memo keyed on a cheap store signature (mtime+size of the six stores plus the vault folders, 1 s floor), invalidated by any write. Measured on the same profile: `build_flow` 20.7 ms → 0.02 ms warm.
> - **A release channel that exists — and installs only what was published.** The updater used to poll `…/mei-update/update.json` on a Netlify host that never served that path (404; the same host only ever served the *other* product's channel), so no installed Mei could ever upgrade itself, and “Open release page” pointed at an empty string. The channel is now the `update.json` asset of the newest **GitHub Release** (`releases/latest/download/update.json`), the button opens `releases/latest`, and every release carries `Mei.exe` + `Mei-<version>-web_support.zip` + the manifest — published by the new `tools/publish_release.py`, whose release notes are copied from this file so the two cannot disagree. Integrity is no longer “size ≥ 1 MB and starts with `MZ`”: the manifest records the build's **`sha256`**, the updater recomputes it after the download and refuses a mismatch (deleting the bad file), while a manifest without a hash still verifies the old way. The same facts are written by `tools/write_local_update.py` for the offline `update\` folder channel.
> - **The build is watched by CI, and the version has one source.** `.github/workflows/ci.yml` runs ruff and the whole suite on `windows-latest` for **both** Qt bindings (PyQt5 and PyQt6 — the shipped exe is built on PyQt6 and gets there through the shim, so both paths deserve a gate) on every push and pull request. `tests/test_version_consistency.py` fails when `pyproject.toml`, `core/product.py` and this changelog disagree about the version — they did: the package metadata still said 0.6.9.0 while the app shipped 0.7.0.0.
> - **Wiring is now a gate, not a hope.** `tests/test_ui_wiring.py` fails on a control that a window or page never adds to a layout, on a primary/menu verb/Close with no slot connected, and on a button role the theme does not paint. It is the general form of the bug the dialog pass left behind (the Google card's own **Sign out** and **Set client ID…**, connected, greyed out and invisible). The Hotkeys dialog — the last one still building its own button — now uses the shared footer too.
> - **Version** 0.6.10.0 → **0.7.0.0**.
>
> ## Milestone — one loop: capture → plan → study → review → reflect
>
> - **`services/study_flow.py` reads every store at once.** The planner, the flashcard deck, the reading list, the inbox, the pour journal and the link table finally answer one question together — *what do I do next?* Priority ladder: finish a running pour, clear an overdue deadline, work today's items and focus blocks, pay the review debt, promote an inbox capture, turn a fresh clip into cards, and only then ask for a plan. `build_flow()` returns the five steps with live counts, a pulse line and the single next action; nothing is stored, so there is no migration and no second source of truth.
> - **Home's Today card became a doorway.** Under the agenda there is now a loop strip — *“1 overdue · 2 planned today · 5 card(s) due · next: ▶ Study “Late essay” (40 min)”* — with **▶ Continue** (runs the recommended step and means what its label says: it starts the pour, opens the deck, selects the note, or promotes the inbox row it names and opens the plan on the new row) and **→ Planner** (promotes the selected inbox row into the Weekly Plan, keeping a task↔item link so either side can be traced).
> - **`/flow`** reports the five steps and then runs the next one from the omnibar; the Morning Brief gained a **“## ▶ Next step”** section (and the plain-text line `▶ …`), the planner's study label answers back with `next: 🧠 Review 3 due card(s)` once a pour is credited, and the **AI index** carries the loop as a document so `/ask what should I do next?` retrieves the same recommendation instead of re-deriving one.
> - **Two gaps closed on the way.** Elapsed minutes are now credited by the refresh that notices the pour ended (`study_session.credit_pending` closes an expired session itself instead of waiting for the next status poll), and promoting a *today*-bucket capture schedules it for today, so the hand-off never moves a row out of the only list that was showing it.
> - **79 new tests** (suite: 450 → 529) — `test_study_flow.py` (priority ladder, counters, capture window, promote/cascade edges), `test_study_flow_surfaces.py` (backup v4 + sync + AI index + brief round-trips, cascade matrix, one scripted walk through all five steps), `test_study_loop_ui.py` (Home strip, `/flow` dispatch, `open_flow_step` routing table, planner study hint, note→card links).
>
> ## Milestone — the study loop closes: planner & flashcards become first-class
>
> - **Study data reaches every surface** — the weekly planner and the flashcard deck now travel with backups (`history_service`, zip format v4), sync to your own endpoint (`SYNC_ENTITIES`: planner, flashcards, entity links), feed the AI index (`/ask` can finally answer “what is due this week?”), appear in library search with a **Planner** / **Cards** shelf filter, and show up in the Morning Brief (🎓 study deadline lines, today's time blocks, cards due). Old backups (v≤3) never wipe newer study data on import.
> - **Courses are first-class on the desktop** — a course card on the Weekly Plan page: create/edit/delete with name, code, colour, schedule and credits. The free-text category box became a **course picker** for both items and time blocks, rows wear their course colour, and double-clicking a focus block opens an edit dialog (title, start, duration, course).
> - **Home “Today” is one agenda** — planner items, planner time blocks and quick inbox tasks in a single list, overdue first, each row badged **Planner** / **Inbox**; double-click opens it where it lives. No data migration: the planner stays the source of truth for anything with a date, the task list stays the quick inbox.
> - **The study loop** — “▶ Study” on a selected planner item or block pours a Café Focus session labelled with it; when the pour ends its elapsed minutes are credited back to the item (`studied_minutes`, once, never double-counted) and the planner shows the running session plus cards due. Planner store bumped to v2 with a registered migration.
> - **Two-way links where they were missing** — a small `entity_links.json` edge table plus a note “🔗 Link…” / **Unlink** panel: link a note to a planner item, cards auto-link their source note, backlinks read the same rows in reverse, and deleting a note/item/course/block/card cascades its edges. Links ride backups and sync like every other store.
>
> ## Milestone 0.6.8.0 — pre-1.0: four new layers on top of browser + personal space
>
> - **🧠 Learning layer** — **Flashcards with SM-2 spaced repetition** (Again/Hard/Good/Easy, ease clamped, 10-min retries) on a new Review page in the Personal Hub, `/review` command, and "⇄ Make flashcard" from selected note text; **Highlight clippings** — page-menu action appends the browser selection to a dated Clippings note with source title/URL; **Reading progress** — saved pages track scroll-% automatically, rows show badges, "▶" marks the furthest-along unfinished page.
> - **🛡 Wellbeing layer** — **Distraction Shield** blocks social/autoplay hosts while a café pour runs (or "always on" in Settings), riding the existing adblock interceptor; **system tray** with quick actions (quick note, 25-min pour, VPN status) and **native Windows toasts** for downloads/focus; **20-20-20 eye-break nudges** inside long pours; **wellbeing chart** — top domains of the week with distraction domains tinted honestly.
> - **⚙️ Automation layer** — **Routines**: daily jobs (e.g. 07:30 Mon–Fri → `/template daily` + open the school timetable) fired by a 30 s scheduler with native toasts, `/routines` editor; **Page monitor** — "Monitor this page" toasts when a watched page changes (15-min raw-HTML checks); **global hotkey Ctrl+Alt+M** captures a quick note from anywhere in Windows (graceful fallback if the OS refuses).
> - **📤 Interop layer** — **Export center** (`/export`): notes → Markdown zip bundle or a themed static HTML mini-site; **Calendar ICS** import/export (stdlib parser, no cloud); **RSS mini-reader** (RSS2 + Atom) under the web-panel menu with items opening as tabs; **Clipboard history** — last 20 entries, Ctrl+Shift+V to restore or paste & go.
> - **Under the hood** — window.py split into reviewable mixins (DockingMixin, WindowToolsMixin); a full Ruff F401/F841/F811 sweep; dead handlers removed.

> ## What's new in 6.7
>
> - **VPN / Shield 2.0** — a status card showing Protected/Unprotected with your visible IP, country and ISP (free ipleak.net lookup, no key); **auto-connect** re-enables the last proxy on every launch; **smart restart** applies proxy changes in ~2 s with tabs restored (no manual restart); **seamless proxy auth** answers Chromium's credential challenge from the saved config; a **leak test** compares the OS path with the browser path and warns on partial routing; **PAC URL** support.
> - **Browser engine parity** — real **split view** (two live pages side by side via "Show beside"); **media mini-player** on the dock rail (play/pause + mute for the audible tab, signal-driven); **runtime profile switching** (persist session, relaunch into the chosen profile).
> - **Personal Space 2.0** — Obsidian-style **[[wiki-links]]** with autocomplete, Ctrl+click to open/create, and a backlinks panel; the notes graph draws **real edges** from wiki-links; **/template daily** and **/template weekly** compose plan/review notes from your actual data; a Duolingo-style **focus streak heatmap** (12 weeks) on Personal Overview.
> - **First run & install** — a 3-step **onboarding wizard** (theme with live preview, import pointer, bridge toggle, skippable, once per profile); refreshed **Inno Setup installer** (taskbar pin, uninstall shortcut, explicit data-preservation note).
> - **Also in 6.7** — colored tab groups **fold/unfold** on the desk; speaker chip for playing tabs (replacing the "[Sound]" title hack); reopen in incognito; middle-click opens bookmarks/history/reading in background tabs; zoom-label click resets; download toasts; crash-safe session autosave every 5 minutes; **16 WCAG-audited café themes** with auto day/night pairing.

> ## What's new in 6.6
>
> - **Theme system redesigned** — 11 harmonious café palettes replacing the old muddy set: **Latte Cream, Honey Crème, Sakura Café, Café Dawn, Matcha Latte, Morning Crème** for day; **Espresso House, Midnight Mocha, Café Azul, Matcha Night, Ember Night** for night. Every TEXT/MUTED/ACCENT pair is WCAG contrast-audited; accents rebalanced with new **Caramel** and **Matcha** presets; the Settings picker shows display names with live color swatches; `/theme <id>` and `/accent <id>` switch instantly from the omnibar; and **Auto day/night** flips each theme to its sibling with the clock (Sakura ↔ Ember Night at 6:00/18:00).
> - **Opera GX web panels** — ◫ opens Telegram/WhatsApp/Discord/Messenger/Spotify/YT Music/Instagram/Gmail or any URL in a slim right dock sharing the main profile (logins persist), with a slim icon rail toggling panels + AI.
> - **Chrome parity features** — colored tab groups (session-persistent), save-password prompt after logins, site permissions manager, searchable hotkeys hub, thin load-progress bar, URL security pill.
> - **Mei identity, louder** — Copilot-style AI sidebar chatting with the visible page, Dashboard 2.0 with a 7-day activity chart, Command palette (quick switcher now launches all 17 slash commands), GX Control Center with a live RAM graph and tab limiter.
> - **Denser, calmer chrome** — 32px slim tab rows with group color dots, Zen mode (Ctrl+Shift+Z) hides every chrome surface for pure reading, slimmer stat tiles.
> - **QoL round** — **16 themes** total (Lavender Latte/Dusk, Hot Cocoa/Mint Mocha, Blueberry Night join); Chrome-style **link-hover URL preview**; **hard reload** (Ctrl+Shift+R); **middle-click paste & go** on the URL bar; **copy page address** in the page menu; **download completion toasts**; **crash-safe session autosave** every 5 minutes; searchable hotkeys hub now lists every mouse gesture and shortcut.
> - **Tab management round** — colored groups **fold/unfold** on the desk (Chrome parity, active tab of a folded group stays visible); playing tabs get a **speaker chip** in the row state slot (replacing the old "[Sound]" title prefix); **reopen in incognito** from tab and page menus; **middle-click opens bookmarks/history/reading rows in background tabs**; clicking the zoom label resets zoom; the reading list confirms with a toast.

> ## What's new in 6.5
>
> - **Notes are safe to type in** — a deep data-loss fix round for the Personal Hub: searching or filtering no longer wipes the open note, saving keeps your selection, moving a note to another category keeps following it, and edits now autosave 250 ms after you stop typing. Deleting notes/boards/events/sites asks for confirmation, and failed saves are reported instead of silently swallowed.
> - **Password vault hardening** — a mistyped master password can no longer overwrite the vault with a single new entry; decryption failures surface an empty password instead of leaking the ciphertext; the vault file is written atomically (crash-safe).
> - **Security fixes** — profile import no longer allows path traversal via crafted note ids; Google sign-in no longer creates Qt widgets on a worker thread; adblock/GitHub-style update callbacks are marshalled to the GUI thread safely.
> - **Downloads done right** — terminal state is recorded exactly once (no more “finished” races), the sidebar downloads panel refreshes on completion, and **incognito tabs can finally download** (their profiles were never wired up).
> - **HTTPS-only upgraded** — plain-http requests are auto-upgraded to https instead of dying on a bare error page (localhost stays allowed).
> - **Less lag** — the Android-bridge poll no longer rewrites a JSON file every 2.5 s, the new-tab page HTML is cached for rapid tab creation, the animated background skips hidden/minimized windows, note/file search boxes are debounced, the quick-switcher parses history on a debounce instead of every keystroke, tab hover probes are throttled to 10 s, and resize relayout only runs when a size class actually changes.
> - **UX polish** — typing in the tab filter no longer yanks you to a different tab; AI answers credit the provider that actually ran the query; manual AI questions no longer inherit a stale “Ask about this note” context; omnibar hints clear properly and no longer crash on empty input; switching search engines no longer hijacks the page you are reading; permission prompts are non-blocking; mute/auto-reload/bookmark feedback is a toast instead of modal dialogs; anti-bot/Google warnings appear once per host instead of every load; “Pin / Unpin” in the tab context menu actually works now; closing a pinned tab unpins it; the Sites preview really unloads pages when hidden.
> - **Crash recovery & shell fixes** — a dead renderer auto-reloads once, then marks the tab “[Crashed]” with a status note instead of leaving a blank white page; F12 reuses one devtools window instead of stacking orphans; closing the last tab lands on a new-tab page; window geometry validates against connected monitors after display changes; locked AI workspace no longer receives prompts submitted while locked; history attributes visits to the tab that actually navigated.
> - **Find bar & polish round 3** — Ctrl+F now opens a sticky Chrome-style find bar (next/prev, match count, Esc) instead of a modal; note find highlights refresh after edits; downloads use stable ids (no more wrong-entry updates when the phone bridge adds one concurrently); session saves hold the profile lock end-to-end; naive due dates count as local time, not UTC; sync pull merges bookmarks by URL instead of replacing them; the Android bridge has socket timeouts and stops echoing raw error paths; extension ZIP imports cap member size; the Sites preview and Ollama detection build in the background instead of at startup; the neural graph timer stops off-page; shell refresh skips the QSS re-polish unless the theme changed; profile names reject path traversal.
> - **UI refresh round** — the whole visual language follows one accent system: find bar/toasts themed, new-tab tiles get favicon-style letter chips and domain pills, dialog default buttons pop with the accent, dormant tabs show a friendly suspended card, reader mode and Personal Hub highlights (find, calendar, sticky cards) all follow the active palette, the AI workspace shows a live provider badge with a pulsing thinking state, empty lists get themed hint rows, and the Home hero greets by time of day.
> - **Professional polish & optimization round** — Chrome-style thin load-progress bar under the toolbar; glyph security pill in the URL bar; middle-click closes tabs and double-clicking the empty tab desk opens a new one; life-data reads are mtime-cached (dashboard refreshes stop re-parsing four JSON files); prefs deep-copies are signature-cached and profile layout checks take a fast path; activity log skips duplicate redirect events; the AI index signature caches per epoch with invalidation on note writes.
> - **Browser-grade feature round** — Opera GX-style **web panels** (Telegram/WhatsApp/Discord/Spotify/Gmail docked beside the page, sharing the main profile so logins persist); Chrome-style **colored tab groups** that survive session restore; **save-password prompt** after logins with vault storage; **site permissions manager** (origin × feature decisions, add/flip/remove/reset); **GX Control Center** with a live RAM spark line, max-live-tabs limiter and adjustable auto-freeze threshold; searchable **hotkeys hub**; **Dashboard 2.0** 7-day activity chart; and a Copilot-style **AI sidebar** that chats with the visible page without leaving the browser.

> ## What's new in 6.3
>
> - **Text highlight & one-click copy** — select any text on any page (main browser tabs and embedded previews alike) to highlight it in amber and get a floating “📋 Copy” bubble next to the selection. Toggle: Page menu → “✎ Highlight text to copy”.
> - **Insight AI reads the browser page** — when the “✦ Insights” panel is on, every `/ask` (or “Ask here”) attaches the full text of the page currently open in the browser to the AI context, and the panel shows which page it is reading.
> - **Site AI reads real content** — “Ask AI” in Personal → Sites now loads the selected site and answers from its actual page text instead of just the URL.
> - **Canonical “Cục Quản Lý” site** — the legacy “Cục Quản Lý - Bản Đầy Đủ 1” duplicate is pruned at startup; Sites keeps exactly one entry pointing at the current hub folder.
> - **No more black screens on tab hover** — the tab memory bubble is now a non-native overlay (the old native tooltip could knock the WebEngine compositor off its backing store and leave other windows black).

> ## What's new in 5.0
>
> - **Theme-aware new-tab page** — the speed dial now follows the active theme + accent. Light themes (minimal, sand-day, cafe-day, rose-day) no longer get stuck with a dark start page; every accent preset recolors the hero, shelf tiles, and search field.
> - **Two new themes** — `forest-night` (deep pine dark with spring-green accent) and `rose-day` (soft warm light with dusty-rose accent), bringing the pack to eight flat, minimal themes.
> - **Keyboard tab cycling** — `Ctrl+Tab` / `Ctrl+PgDown` for the next tab, `Ctrl+Shift+Tab` / `Ctrl+PgUp` for the previous, scoped to the visible workspace.
> - **Reopen closed window** — Sessions & Spaces now has “Reopen Closed Window”, restoring the last closed multi-tab window (including pinned state and per-tab workspace).
> - **Keyboard-first shell** — `Ctrl+K` focuses the omnibar; `Ctrl+1`–`Ctrl+7` jump straight to Home, Browser, History, AI, Personal, Library, and Settings.
> - **Stability** — fixed a crash in “Reopen Closed Tab” that called a method that no longer exists.

> ## What's new in 6.2
>
> - **Self-hosted sync** — Settings gains a “Self-hosted sync” card (endpoint + Bearer token). Push your profile snapshot (tasks, events, boards, saved pages, notes, bookmarks, history) to your own HTTP endpoint and pull it on another machine. `/sync` does push + pull from the omnibar.
> - **Weekly Review agent** — `/agent review` writes a note summarising the last 7 days: pages by day, completed tasks, vault count.

> ## What's new in 6.1
>
> - **More interface settings** — Settings gains an “Interface extras” card: turn the new-tab steam animation, the café time-greeting, and the Home Morning Brief card on or off, all saved per profile.
> - **Standardized nav icons** — the shell rail now uses one consistent glyph set (✦ AI · ◍ Personal · ▤ Library) across wide and compact layouts.

> ## What's new in 6.0
>
> - **Morning Brief** — Home now shows a local-first digest of your day: pages visited yesterday + top sites, overdue & due-today tasks, upcoming events, and focus minutes. `/brief` pops the same digest in a dialog.
> - **AI Agent actions** — `/agent summary` digests your open tabs into a Markdown note (AI when a provider is set, otherwise grouped by domain); `/agent tasks <a | b | c>` turns items into tasks.
> - **Tab groups by domain** — “Group tabs by domain” labels every tab with its site so you can filter with `group:youtube.com` in the tab search (`/group-tabs` does it from the omnibar).
> - **Tab search `group:` filter** — alongside `is:sleeping`, `is:pinned`, and `site:`.
> - **CSS-drawn coffee cup** — the new-tab hero mug is now drawn in pure CSS (steam + mug + saucer) instead of an emoji glyph, so it stays crisp, perfectly centered, and never clipped.
> - **Keyboard-hint chips** — the new-tab footer shows shortcut pills (Ctrl+T, Ctrl+K, /agent · /brief · /group-tabs).

> ## What's new in 5.9
>
> - **Stat tiles now truly fill and center** — the dashboard stat rows on Home, Personal, Library, and History were hugging the left edge (or shrinking to their minimum). They now spread evenly across the full width, so any number of tiles (3, 4, or 5) stays centered and balanced.

> ## What's new in 5.8
>
> - **Rebuilt new-tab page (“café bar”)** — a sticky shop awning, a hero with an animated rising-steam coffee cup, and menu-card shortcuts with hover lift + warm glow. Fully palette-driven, so it follows the active theme and accent in light and dark alike.

> ## What's new in 5.7
>
> - **Unified browser control deck** — the toolbar and tab area now share one calm visual language: back/forward/reload use themed glyphs (← → ↻) instead of system icons, the VPN button is a proper accent button, and the Control button matches the New Tab button as a cohesive footer pair.
> - **Clearer tab list** — the selected tab gets a left accent bar and the sidebar panel buttons (tabs/bookmarks/history/downloads/reading) are evenly sized pills with a distinct active state.

> ## What's new in 5.6
>
> - **New “Latte” theme** — an airy, modern coffee-house look: steamed-milk surfaces, gentle mocha hairlines, and a caramel accent. Pick it in Settings → Interface → Theme (it's the calm daytime café counterpoint to `minimal`).
> - **Softer UI rhythm** — slightly larger radii on cards, hero, inputs, and the omnibar, plus a single accent-colored focus ring, so the whole app reads lighter and more composed without losing the flat café character.
> - **Tidy** — removed a duplicated nav hover rule in the shared stylesheet.

> ## What's new in 5.5
>
> - **Extensions with match patterns** — each `.js` in the Extensions folder can now start with a standard `==UserScript==` header declaring `@match` / `@exclude` URL globs (e.g. `https://*.example.com/*`). Scripts run only on matching pages instead of every page; files without a header keep the old run-everywhere behaviour.
> - **Restore / manage tab sets** — Sessions & Spaces gains “Restore Tab Set…”, which lists saved tab collections and opens or deletes them. Restored tabs start suspended, so reopening a big research session stays cheap.
> - **Semantic search (optional)** — when the AI provider is Ollama with a local model, retrieval now blends embedding cosine similarity with BM25, so related items surface even when the words differ. Falls back to pure BM25 the moment Ollama isn't reachable.
> - **New omnibar macros** — `/freeze` (suspend background tabs), `/save-tabs <name>` (save current tabs as a named set), `/summarize` (summarize the active page with AI).

> ## What's new in 5.4
>
> - **Google sign-in hardening** — the Chrome-compat shim now also patches the remaining fingerprint tells that can trigger “This browser or app may not be secure”: `navigator.deviceMemory` / `hardwareConcurrency` / `vendor` / `maxTouchPoints` / `onLine` (only when missing), `window.chrome.webstore`, and WebGL `UNMASKED_VENDOR_WEBGL` / `UNMASKED_RENDERER_WEBGL` (only when the GPU string looks like a software/embedded renderer). Real hardware values pass through untouched so WebGL sites keep working.

> ## What's new in 5.3
>
> - **Max live tabs** performance setting (Settings → Interface) — lower the number to keep more tabs suspended and stay smooth with hundreds of tabs open. Default 10, range 1–32.
> - **Chrome-style tab memory bubble** — hover any tab and it shows the page title, host, JS heap, and estimated RAM in MB (suspended tabs show “~0 MB”). The bubble now appears after ~0.7 s instead of 3 s.
> - **Authenticated proxies** — VPN/proxy now passes user:password through to Chromium (`--proxy-server=socks5://user:pass@host:port`), so proxies that require login actually work.
> - **Safer proxy handling** — a half-configured proxy (empty host/port) no longer breaks networking; it falls back to “No proxy”.
> - **Extensions** — “Open folder” button in the Extensions dialog, and the Adblock sample script is now enabled by default so first-time users see it take effect.

> ## What's new in 5.2
>
> - **Boards → Link mode** — connect sticky cards with a real edge: click one card, then another, and a dashed line follows them as you drag. Edges persist with the board; “Clear links” removes them.
> - **Ecosia search engine** — added to the address bar + speed dial (privacy-first, planet-friendly).
> - **Search engine registry** — all engine URLs now live in one place (`core/prefs.py`); adding an engine is a one-line change.
> - **Shared time util** — `_format_ts` de-duplicated into `core/time_utils.py`.
> - **Honest labeling** — the “Sync” button/badges now say **Snapshot / Local snapshot**, because it flushes local state (no remote server yet).
> - **ARCHITECTURE.md** — a written guide to the layers and extension points for future upgrades.

> ## What's new in 5.1
>
> - **Home dashboard** — a live clock in the hero, plus a “Recently Closed” card: double-click any tab you closed to reopen it in the browser.
> - **AI Workspace** — “Export” writes the whole assistant thread to a Markdown/text file; “Clear” empties the thread and answer panes.
> - **Personal Hub → Notes** — live word & character count under the editor as you type.
> - **Settings** — “Open profile folder” and “Open runtime data folder” buttons jump straight to your data on disk.
> - **History** — “Clear all” wipes the activity log after confirmation.

> ## What's new in 4.0 / 4.1 / 4.2
>
> - **Minimal theme (4.2.5)** - the shared theme went flat and minimal: every gradient was stripped from the chrome (top bar, hero card, nav pills, accent buttons, checkboxes, progress bars) in favor of flat fills, and two new monochrome themes joined the pack — `minimal` (pure white + hairline grays + ink accent) and `minimal-night` (near-black + light ink). `minimal` is now the default theme for new profiles; every accent preset still recolors it. All four older themes keep their palettes but now render flat.
> - **Full-app UI modernization (4.2)** — the shared theme was overhauled from the ground up so *every* window gets the new look, not just the browser: elevated cards with hover states, a polished nav rail with checked-pill highlight, modern toggle/checkbox/radio indicators, `QProgressBar` + `QGroupBox` + `QTreeWidget` styling, and slimmer translucent scrollbars.
> - **Rebuilt surfaces (4.2.3)** — every window now uses one shared design system (`ui/components.py`: page headers, stat tiles, section headers, empty states). The Home dashboard, Library, History, Settings, AI Workspace, Personal Hub (overview + all six pages), and the browser new-tab web page were each rebuilt with consistent icon-led headers, big stat tiles, and cleaner spacing; the new-tab page gained tile hover-lift, focus rings, and a footer.
> - **Action-first shell (4.2.4)** — the app shell gained a proper top app bar (brand with glyph, theme pill, sync + insights), a floating sidebar with icon nav buttons, sync status and profile line, and a slim status footer. The Home dashboard now launches workspaces from a nine-button action grid plus quick-command chips; the browser window gained a glyph-led sidebar and an address hint that shows 🔒 Secure / ⚠ HTTP / 📁 Local states; the AI badge row shows live index/context status; every dialog shares the same design tokens.
> - **Café Focus (pomodoro)** — start a focus "pour" from Home, Personal, or `/focus 25`; track with `/status`; journal + dashboard minutes.
> - **Accent color picker** — brass / ember / teal / violet / sky / rose / slate, recolor across every theme.
> - **Four themes** — `cafe-night`, `cafe-day`, `ocean-night` (cool dark), `sand-day` (bright paper).
> - **Time-aware café greeting** on the speed dial (hero copy changes by time of day).
> - **Per-site zoom memory** — restored per host; *Reset zoom* clears it.
> - **Forced dark mode reworked** — profile-scoped DocumentReady script paints dark from first render (respects built-in dark themes).
> - English UI throughout.

## Current build

- Version **0.6.8.0** (pre-1.0: the feature set is deep but the 1.0 bar - signed builds, docs, long-term API stability - has not been reached yet)
- `AppShell` as the master shell for workspace navigation
- `Browser` for web browsing: tabs, imports, workspaces, privacy, downloads
- `Personal Hub` for notes, tasks, boards, files, sites, calendar
- `AI Workspace` for Q&A and context extraction from the profile
- `Library`, `History`, `Settings`, `Home`
- Two shell windows running side by side for two browser workspaces
- Chrome/Opera GX extension bridge → Mei for tab transfer

This document is written to reflect the current implementation in the repo with maximum coverage: features, architecture, data flow, file storage, slash commands, imports, graphs, build, and the relationships between the parts.

## Self-hosted sync

Point Mei at a tiny HTTP endpoint you run yourself. The app never talks to a cloud —
requests carry a `Bearer` token and a JSON snapshot of your local data.

Endpoints the app calls (base = your endpoint URL):

- `POST {base}/api/sync/push` — body is the JSON snapshot bundle; return `{"ok": true}`.
- `GET {base}/api/sync/latest` — return the latest stored snapshot body.

A minimal server in Python (save as `sync_server.py`, run with `python sync_server.py`):

```python
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

STORE = {"bundle": None}
TOKEN = "change-me"

class H(BaseHTTPRequestHandler):
    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send(401, b'{"error":"unauthorized"}')
        n = int(self.headers.get("Content-Length") or 0)
        STORE["bundle"] = self.rfile.read(n)
        self._send(200, b'{"ok":true}')
    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send(401, b'{"error":"unauthorized"}')
        if STORE["bundle"]:
            self._send(200, STORE["bundle"])
        else:
            self._send(404, b'{"error":"no snapshot"}')
    def log_message(self, *a):
        pass

HTTPServer(("0.0.0.0", 8901), H).serve_forever()
```

Then in Mei → Settings → Self-hosted sync: enable, set endpoint `http://<your-pc-ip>:8901`,
paste the same token, and press **Sync now**. Run the same on the second machine to pull.

## Android Bridge Plan

Mei is positioned as the central browser of the ecosystem; the next development direction
is a dedicated Android app acting as a remote manager + data bridge for the Browser.

That Android app is not yet implemented in the current code. It is specified as a planned component
that sends data from the phone into Mei over `LAN/Wi-Fi + shared token`, instead of writing
files directly into the profile.

Dedicated spec document (archived): `docs/legacy/ANDROID_BRIDGE_SPEC.md`

---

## 1. System overview

Mei is a multi-workspace desktop app. When it starts it opens **two AppShell windows** in
parallel, each carrying its own `SearchWindow` bound to a different browser workspace.

The three largest layers of the application:

1. `Entry + Runtime`
   - `browser.py`
   - `litebrowser/main.py`
   - `litebrowser/core/app_paths.py`
   - `litebrowser/core/prefs.py`

2. `UI / Shell`
   - `litebrowser/ui/app_shell.py`
   - `litebrowser/ui/main_window/window.py`
   - `litebrowser/ui/personal_window.py`
   - `litebrowser/ui/ai_window.py`
   - `litebrowser/ui/shell/pages.py`
   - `litebrowser/ui/theme.py`
   - `litebrowser/ui/dialogs/*`

3. `Services / Data / Browser Core`
   - `litebrowser/browser/tab_manager.py`
   - `litebrowser/browser/browser_page.py`
   - `litebrowser/browser/adblock.py`
   - `litebrowser/services/*`

### 1.1 Overall architecture graph

```mermaid
graph TD
    A[browser.py] --> B[litebrowser.main.main]
    B --> C[QApplication]
    B --> D[Profile selection + ensure layout]
    D --> E[ensure_dual_workspaces]
    E --> F[AppShell primary]
    E --> G[AppShell secondary]

    F --> H[Home]
    F --> I[Browser/SearchWindow]
    F --> J[History]
    F --> K[AI Workspace]
    F --> L[Personal Hub]
    F --> M[Library]
    F --> N[Settings]

    G --> O[Home]
    G --> P[Browser/SearchWindow]
    G --> Q[History]
    G --> R[AI Workspace]
    G --> S[Personal Hub]

    I --> T[TabManager]
    T --> U[BrowserPage]
    U --> V[QWebEngineProfile]
    V --> W[QtWebEngine Chromium runtime]

    I --> X[extension_bridge]
    I --> Y[workspace_manager]
    I --> Z[download_mgr]
    I --> AA[history_service]

    L --> AB[personal_service]
    L --> AC[life_service]

    K --> AD[ai_service]
    AD --> AE[retriever]
    AD --> AB
    AD --> AC

    M --> AE
    J --> AA
    N --> AF[update_service]
```

### 1.2 Workspace UI system

`AppShell` is the master shell. Each shell has:

- a left rail to switch workspaces
- a center stack holding the current page
- a compact status strip / omnibar at the bottom
- a right insight panel with AI quick actions

Current workspaces:

- `home`
- `browser`
- `history`
- `ai`
- `personal`
- `library`
- `settings`

### 1.3 Two shell windows

The app creates:

- `AppShell(window_slot="primary", browser_workspace_id=PRIMARY_WORKSPACE_ID)`
- `AppShell(window_slot="secondary", browser_workspace_id=SECONDARY_WORKSPACE_ID)`

Purpose:

- run two browsing areas side by side
- split the screen 50/50
- bind each browsing area to its own browser workspace
- share the same profile data layer

---

## 2. Startup flow

### 2.1 Sequence

1. `browser.py` calls `litebrowser.main.main()`
2. set Qt/Chromium flags
3. create `QApplication`
4. find the previous profile, or create `Default`
5. `workspace_manager.ensure_dual_workspaces(profile_dir)`
6. register bundled support sites (e.g. `Cục Quản Lý`) if present
7. clean old GPU caches in `BrowserData`
8. create 2 `AppShell`s
9. show both windows

### 2.2 Startup graph

```mermaid
sequenceDiagram
    participant User
    participant BrowserPy as browser.py
    participant Main as litebrowser.main
    participant Prefs as prefs.py
    participant WS as workspace_manager.py
    participant Shell1 as AppShell primary
    participant Shell2 as AppShell secondary

    User->>BrowserPy: python browser.py
    BrowserPy->>Main: main()
    Main->>Prefs: get or create profile
    Prefs-->>Main: profile_dir
    Main->>WS: ensure_dual_workspaces(profile_dir)
    Main->>Shell1: create
    Main->>Shell2: create
    Shell1-->>User: show
    Shell2-->>User: show
```

---

## 3. Folder structure and storage

App data is split into two layers:

- **repo/runtime root**
- **profile dir**

### 3.1 Runtime root

Usually:

- running from source: `runtime_data/profiles/...`
- running the exe: `%LOCALAPPDATA%/Mei/runtime_data/...`

### 3.2 Profile dir

Each profile has the following files/folders:

```text
profiles/<ProfileName>/
  prefs.json
  profile_meta.json
  session.json
  history.txt
  bookmarks.json
  workspaces.json
  permissions.json
  downloads_list.json
  proxy_config.json
  extension_imports.json
  ai_index.json
  ai_settings.json
  activity_history.json
  tab_sets.json
  BrowserData/
  Downloads/
  Extensions/
  SafeVault/
    notes/
    passwords.enc
```

### 3.3 Storage blocks

| Path | Role |
|---|---|
| `prefs.json` | startup mode, shell theme, shell density, hibernate seconds, https only, dark web, block third-party cookies, passcode hash/salt, personal sites, personal root, window geometry |
| `profile_meta.json` | profile schema metadata |
| `session.json` | browser session state and recently closed |
| `history.txt` | browser history text log |
| `bookmarks.json` | bookmarks |
| `workspaces.json` | workspace list and current id |
| `permissions.json` | site permissions |
| `downloads_list.json` | download records |
| `proxy_config.json` | proxy/VPN configuration |
| `extension_imports.json` | tab batches received from extension/import file/query payload |
| `ai_index.json` | AI retrieval index |
| `ai_settings.json` | provider/model/API local settings |
| `tab_sets.json` | saved tab sets / snapshots |
| `BrowserData/` | cookies, cache, persistent web engine state |
| `Downloads/` | download target dir |
| `Extensions/` | local JS injection extensions + unpacked bridge extension folder |
| `SafeVault/notes/` | Personal Hub notes |
| `SafeVault/passwords.enc` | encrypted credentials when the password manager is enabled |

### 3.4 Data layer graph

```mermaid
graph LR
    App[Mei App] --> Prefs[prefs.json]
    App --> Session[session.json]
    App --> History[history.txt]
    App --> Bookmarks[bookmarks.json]
    App --> Workspaces[workspaces.json]
    App --> Permissions[permissions.json]
    App --> DownloadsList[downloads_list.json]
    App --> Proxy[proxy_config.json]
    App --> ExtImports[extension_imports.json]
    App --> AIIndex[ai_index.json]
    App --> AISettings[ai_settings.json]
    App --> TabSets[tab_sets.json]
    App --> BrowserData[BrowserData/]
    App --> Vault[SafeVault/]
    Vault --> Notes[notes/]
    Vault --> Passwords[passwords.enc]
```

---

## 4. AppShell

`litebrowser/ui/app_shell.py`

AppShell is the navigation center and runtime shell.

### 4.1 Main functions

- hosts the navigation rail
- hosts the stacked workspace pages
- hosts the omnibar command box
- hosts the right insight panel
- initializes embedded browser/personal/ai pages
- saves/restores geometry for primary and secondary shells
- performs quick actions
- routes slash commands
- routes library items to the right workspace
- updates the compact layout by width

### 4.2 Insight panel

The insight panel shows:

- ambient insights
- sleeping tabs list
- Assistant quick-ask area

The AI quick ask has:

- `Ask here`
- `Whole profile`
- a quick text box
- a short answer preview

### 4.3 Omnibar and slash commands

The omnibar currently supports:

- `/home`
- `/browser`
- `/history`
- `/ai`
- `/personal`
- `/library`
- `/settings`
- `/cql`, `/cuc-quan-ly`, `/cu`, `/cuc`, `/quanly`, `/quan-ly`
- `/guide`, `/help`
- `/ask ...`
- `/task ...`
- `/note ...`
- `/board ...`
- `/save-page`
- `/freeze` — suspend all background tabs
- `/save-tabs <name>` — save current tabs as a named set
- `/summarize` — summarize the active page with AI
- `/brief` — popup Morning Brief
- `/agent summary` / `/agent tasks a | b` / `/agent review` — AI agent actions
- `/group-tabs` — assign a domain group to each tab
- `/sync` — push + pull self-hosted sync

#### The `/note` command

The slash note command is now richer:

- `/note Title`
- `/note Category/Title`
- `/note Category | Title | Content`

Behavior:

- creates a note in `SafeVault/notes/<Category>/`
- opens Personal Hub
- auto-selects the newly created note

### 4.4 Geometry and compact shell

AppShell is compact-first:

- smaller minimum size
- smaller left rail
- thinner status strip
- insights panel scales with width
- browser workspace hides `insights` by default

---

## 5. Browser / SearchWindow

`litebrowser/ui/main_window/window.py`

This is the main browser.

### 5.1 Structure

- left sidebar
- top bar
- inline AI panel
- web container
- QStackedWidget holding tabs

### 5.2 Core browser features

#### Tabs

- new tab
- incognito tab
- close tab
- duplicate tab
- pin/unpin tab
- auto hibernate
- optimize memory / freeze all inactive
- quick switcher
- audio state indicator

#### Navigation

- back
- forward
- reload
- home
- search engine picker
- URL/search bar
- go
- AI page question
- page menu
- import center

#### Content actions

- find in page
- reader mode
- highlight text to copy (with copy bubble)
- bookmark page
- save current page to library
- create note from current page
- screenshot
- extract text
- print page
- save PDF
- open externally
- dev tools

#### Sidebar panels

- Tabs
- Bookmarks
- History
- Downloads

#### Browser workspace filter

Each tab carries a `workspace_id`.
The sidebar tab list only shows tabs belonging to the current browser workspace.

### 5.3 Import Center for extension/browser bridge

Tab import from extensions is wired into the browser.

Data sources can be:

- hand-pasted JSON payload
- `.json` file via the file picker
- `importBatchData` query parameter

The Import Center offers:

- `Refresh`
- `Import File`
- `Store Payload`
- `Import Selected Batch`

Data is stored in `extension_imports.json`.

### 5.4 Tab import flow

```mermaid
sequenceDiagram
    participant Ext as Chrome/Opera GX extension
    participant File as JSON file or clipboard
    participant Browser as SearchWindow Import Center
    participant Bridge as extension_bridge.py
    participant Tabs as TabManager

    Ext->>File: export payload
    File->>Browser: paste or import file
    Browser->>Bridge: import_from_json_text / import_from_file
    Bridge->>Bridge: normalize batch + tabs
    Bridge->>Bridge: save extension_imports.json
    Browser->>Bridge: load_batches
    User->>Browser: Import Selected Batch
    Browser->>Tabs: add_tab per payload item
```

### 5.5 Browser page runtime

`litebrowser/browser/browser_page.py`

- creates child tabs when a site requests a popup/new window
- handles permissions
- routes new tabs into `TabManager`
- hosts the profile-level scripts (Chrome-compat shim, forced dark, text highlight)

### 5.6 TabManager

`litebrowser/browser/tab_manager.py`

Responsibilities:

- create `QWebEngineView`
- create incognito profile when needed
- add/remove/change tabs
- save tab metadata
- hibernate tabs
- wake tabs
- tab memory bubble (non-native overlay)
- update visual pinned/hibernated/icon/title state
- walk tab state to save the session

Metadata roles:

- `TAB_WIDGET_ROLE`
- `TAB_PINNED_ROLE`
- `TAB_META_ROLE`

### 5.7 New Tab page

`litebrowser/browser/new_tab_page.py`

Responsibilities:

- build the local HTML for a new tab
- combine bookmarks + recent history
- speed-dial style home

### 5.8 Browser security and privacy

#### Adblock / request interception

`litebrowser/browser/adblock.py`

- built-in blocked domains
- optional custom filter file
- `https_only` mode
- DNT-style control injection

#### Password manager

`litebrowser/services/password_manager.py`

- stores credentials encrypted in `SafeVault/passwords.enc`
- autofills when the page has loaded and the user has unlocked

#### Site permissions

- stored in `permissions.json`
- BrowserPage handles feature permission requests

#### Third-party cookie policy

- preference persisted
- applied to the profile when the backend supports it

#### Proxy / VPN

- config stored in `proxy_config.json`
- applied via `QNetworkProxy` (+ `--proxy-server` Chromium flag when needed)

---

## 6. Personal Hub

`litebrowser/ui/personal_window.py`

Personal Hub contains:

- Overview
- Notes
- Tasks
- Calendar
- Boards
- Files
- Sites

### 6.1 Overview

- pending task stats
- upcoming events
- total boards
- total notes
- recent focus list
- recent timeline list

### 6.2 Notes

The notes section is much richer than before.

#### Currently available

- search notes
- editable category combo
- font size selector
- new note
- delete note
- save note
- ask AI about note
- note list
- note editor
- neural graph animation

#### Category notes

Category is real data:

- notes are stored under category folders
- examples:
  - `SafeVault/notes/General/...`
  - `SafeVault/notes/Work/...`
  - `SafeVault/notes/Study/Math/...`

Purpose:

- let the `/note` slash command create a note in any category
- allow changing a note's category in Personal Hub
- allow filtering the notes list by category

#### Neural graph in Notes

A `NeuralGraphWidget` was added to the notes panel.

It is a custom-painted animation:

- nodes moving along orbit/phase paths
- lines drawn between nodes
- a simulated “3D neural / memory lattice” effect
- runs inside the Personal Hub notes area

Goal:

- build a “moving neural diagram graph”
- keep the note workflow intact
- never push the browser out of Personal Hub

### 6.3 Tasks

`life_service` handles:

- add task
- mark complete
- buckets
- save and refresh

Tasks can also be created from:

- the `/task` slash command
- AI answer → create task

### 6.4 Calendar

- event list
- date selection
- event details
- events stored in life data

### 6.5 Boards

Boards are a whiteboard / sticky-note system.

Includes:

- board list
- board view
- sticky cards
- ink strokes
- pan / draw / link modes
- board position saving

#### Graph board architecture

```mermaid
graph LR
    BoardsUI[PersonalWindow Boards UI] --> BoardScene[QGraphicsScene]
    BoardScene --> Sticky[StickyCardItem]
    BoardScene --> Ink[InkStrokeItem]
    BoardView[BoardView] --> BoardScene
    BoardView --> SavePositions[save board positions]
```

### 6.6 Files

- choose the personal root
- search root entries
- list files/folders
- open with the default app / Explorer

### 6.7 Sites

- personal sites stored in prefs
- add/remove sites
- preview a site in a `QWebEngineView`
- open a site in the browser shell when needed
- “Ask AI” reads the site's real content

### 6.8 Auto save state

Personal Hub:

- has `get_current_state()`
- auto-saves a personal tab set
- `closeEvent` saves the open note and board positions

---

## 7. AI Workspace

`litebrowser/ui/ai_window.py`

### 7.1 Goal

The AI Workspace is used to:

- answer questions on the current context
- retrieve from the profile
- save AI sessions
- create notes/tasks from answers

### 7.2 UI

- hero card
- provider selection
- model selection
- API key field
- ask bar
- reindex
- session history
- answer thread
- sources + prompt library

### 7.3 Providers

Available providers:

- `rag`
- `openrouter`
- `ollama`
- `llama_cpp`

### 7.4 Data and retrieval

`litebrowser/services/ai_service.py`
`litebrowser/services/retriever.py`

Context sources:

- browser history
- bookmarks
- downloads
- saved pages
- personal sites
- notes
- tasks
- boards
- events

### 7.5 AI flow

```mermaid
graph TD
    User[User question] --> AIWin[AIWindow]
    AIWin --> Settings[ai_settings.json]
    AIWin --> AIService[ai_service.py]
    AIService --> Retriever[retriever.py]
    Retriever --> History[history]
    Retriever --> Notes[SafeVault notes]
    Retriever --> Tasks[tasks]
    Retriever --> Boards[boards]
    Retriever --> Pages[saved pages]
    Retriever --> Sites[personal sites]
    AIService --> Provider[RAG/OpenRouter/Ollama/llama.cpp]
    Provider --> Answer[final answer]
    Answer --> AIWin
```

### 7.6 Session management

- save the current AI session into `tab_sets`
- load prompt templates
- save answer to note
- create task from answer

---

## 8. Library

`litebrowser/ui/shell/pages.py` -> `LibraryPage`

Library is the unified results layer.

Data sources:

- saved pages
- notes
- tasks
- retriever results
- events
- boards

On double-click:

- opens the browser if the item is a URL/page/site
- opens Personal Hub if the item is a note/task/event/board

---

## 9. History

`HistoryPage` + `history_service.py`

### 9.1 Activity log

Tracks:

- browser visit
- bookmark
- note create/update/delete
- task
- calendar
- board
- download
- AI question
- account state

### 9.2 Backup / import

The History page supports:

- export profile backup
- import profile backup

The backup includes:

- notes
- tasks
- calendar
- boards
- bookmarks
- AI questions
- browser-related data

---

## 10. Settings

The Settings page currently has:

- account display name
- email
- sync-ready flag
- shell density
- shell theme + accent (9 themes, 7 accents)
- **Interface extras** (6.1): steam animation, café time-greeting, Morning Brief card
- **Max live tabs** (5.3): max concurrent live tabs (1–32, default 10)
- **Self-hosted sync** (6.2): endpoint + Bearer token + “Sync now” button (push + pull)
- open help tools
- check updates
- install update
- open release page

The update flow uses:

- `update_service.check_for_updates`
- `download_update_package`

---

## 11. Home

`HomeDashboardPage` is the main dashboard:

- quick launch Browser
- Ask AI
- Open Personal
- Quick Task
- Help
- stats cards
- recent notes
- today focus

---

## 12. Extension bridge Chrome / Opera GX

Folder:

- `Extensions/tab-window-bridge/manifest.json`
- `Extensions/tab-window-bridge/popup.html`
- `Extensions/tab-window-bridge/popup.js`

### 12.1 Purpose

Pull tabs from a Chrome-family browser into Mei.

### 12.2 Behavior

- captures tabs of the `currentWindow`
- stores each window as a separate batch in `chrome.storage.local`
- can:
  - copy JSON
  - download JSON
- Mei's Import Center reads that file/JSON

### 12.3 Extension → browser flow

```mermaid
graph LR
    Chrome[Chrome/Opera GX Window] --> Popup[tab-window-bridge popup]
    Popup --> Storage[chrome.storage.local]
    Popup --> Export[Copy JSON or Download JSON]
    Export --> ImportCenter[Mei Import Center]
    ImportCenter --> Bridge[extension_bridge.py]
    Bridge --> BatchStore[extension_imports.json]
    BatchStore --> SearchWindow[Import Selected Batch]
    SearchWindow --> Tabs[TabManager add_tab]
```

---

## 13. Notes system details

`litebrowser/services/personal_service.py`

### 13.1 Notes dir

- root: `SafeVault/notes`
- notes are stored as `.md` / `.txt` files

### 13.2 Data shape

Notes do not use a database.

Instead:

- folder = category
- filename = safe-named title
- file content = note body

Example:

```text
SafeVault/notes/General/Untitled-note.md
SafeVault/notes/Work/Meeting-brief.md
SafeVault/notes/Study/Math/Integral-summary.md
```

### 13.3 Current API

- `notes_dir(base_dir)`
- `list_notes(base_dir, query="")`
- `read_note(base_dir, note_id)`
- `create_note(base_dir, title, content="", category="General")`
- `save_note(base_dir, note_id, content)`
- `update_note(base_dir, note_id, content, category=None)`
- `delete_note(base_dir, note_id)`
- `list_note_categories(base_dir)`
- `list_root_entries(base_dir, query="")`

### 13.4 Notes system graph

```mermaid
graph TD
    SlashNote[/note command] --> Create[personal_service.create_note]
    NoteUI[Personal Notes UI] --> Read[read_note]
    NoteUI --> Update[update_note]
    NoteUI --> Delete[delete_note]
    Read --> Files[SafeVault/notes category folders]
    Create --> Files
    Update --> Files
    Delete --> Files
```

---

## 14. Browser imports and extension imports

`litebrowser/services/extension_bridge.py`

### 14.1 Import sources

- JSON text
- JSON file
- base64 query payload (`importBatchData`)

### 14.2 API

- `load_batches`
- `save_batches`
- `upsert_batch`
- `import_from_json_text`
- `import_from_file`
- `import_from_encoded_query`
- `mark_batch_imported`

### 14.3 Batch shape

```json
{
  "id": "chrome_window_123",
  "window_id": "123",
  "source_browser": "chrome",
  "source_label": "Work Window",
  "created_at": 1234567890,
  "imported_at": null,
  "tab_count": 5,
  "tabs": [
    {
      "url": "https://example.com",
      "title": "Example",
      "active": true,
      "pinned": false
    }
  ]
}
```

---

## 15. Compact-first UI

The app was compacted in the following directions:

- smaller shell chrome
- smaller rail
- smaller status strip
- thinner browser sidebar
- more compact browser top bar
- AI / Personal / shell pages reduced margins, padding, radius
- responsive layout for narrow widths

Goal:

- give maximum space to the main content
- keep all features
- keep the UI centered and balanced

---

## 16. Theme and visual system

`litebrowser/ui/theme.py`

The palette has 2 modes:

- `cafe-night`
- `cafe-day`

The QSS covers:

- `QMainWindow`, `QWidget`
- omnibar
- inputs
- buttons
- nav
- status strip
- top bar
- sidebar
- list items
- menu
- splitter handle

Style concept:

- café / paper / brass tones
- rounded cards
- soft gradients
- compact tokens

---

## 17. Dialogs and utility UI

`litebrowser/ui/dialogs/*`

The dialog system covers:

- workspace management
- startup mode
- privacy / security
- VPN
- hibernate prefs
- quick switcher
- bookmarks
- downloads
- extensions
- guide/help/control center

---

## 18. Security gate / passcode

`litebrowser/services/security.py`

Used to:

- lock `AI` and `Personal` behind a passcode
- unlock for the session

The passcode stores only hash/salt/rounds in `prefs.json`, never the plain password.

---

## 19. Update system

`litebrowser/services/update_service.py`

Capabilities:

- compare the current version with the latest release
- build update status text
- download the update package

The shell Settings page routes through this service.

---

## 20. Run from source & build the desktop app

> **Official doc: `RUN_AND_BUILD.md`** — step-by-step guide: requirements, how to run
> (batch / `.venv` / module), common run errors, a post-launch testing checklist, and the full
> `.exe` build commands. Below is the short version.

### Quick run

```powershell
pip install -r requirements.txt
python browser.py
```

Or:

```powershell
python -m litebrowser
```

### Quick syntax check

```powershell
python -m py_compile litebrowser\ui\app_shell.py
python -m py_compile litebrowser\ui\main_window\window.py
python -m py_compile litebrowser\ui\personal_window.py
python -m py_compile litebrowser\ui\ai_window.py
```

---

## 21. Build exe (short version)

> The full build command (`--collect-all` for QtWebEngine is mandatory; without it the exe fails
> to initialize WebEngine) is in **`RUN_AND_BUILD.md` → section 5**. TL;DR:

```powershell
python -m PyInstaller --onefile --windowed --icon=icon.ico --name="Mei" `
  --collect-all PyQt6.QtWebEngineCore `
  --collect-all PyQt6.QtWebEngineWidgets `
  --collect-all PyQt6.QtWebChannel `
  browser.py
```

### Results and notes

- the exe lands in `dist/Mei.exe` (or `dist/Mei/` for a folder build)
- the browser extension folder does not “squeeze into” the exe via a CRX mechanism; the extension
  bridge remains a separate unpacked folder to load in Chrome/Opera GX
- profile/runtime data is created outside the exe when the app runs (source: `runtime_data/...`;
  exe: `%LOCALAPPDATA%/Mei/runtime_data/...`)

---

## 22. Using extension import

### On Chrome / Opera GX

1. Load the unpacked extension from:
   - `Extensions/tab-window-bridge`
2. Open the extension popup
3. `Capture This Window`
4. `Copy JSON` or `Download JSON`

### On Mei

1. Open Browser
2. Open `Import Center`
3. Choose:
   - `Store Payload` to paste JSON
   - `Import File` to pick a JSON file
4. Select the batch
5. `Import Selected Batch`

---

## 23. Using the new slash note

### Simple note

```text
/note Daily plan
```

### Note with category

```text
/note Work/Daily plan
```

### Note with category + title + content

```text
/note Work | Sprint summary | work items, blockers, next steps
```

Result:

- the note is created in `SafeVault/notes/Work/`
- Personal Hub opens
- the note is selected immediately

---

## 24. “Everything” Mermaid graph

```mermaid
graph TD
    subgraph Runtime
        Start[browser.py]
        Main[litebrowser.main]
        Prefs[prefs.py]
        Paths[app_paths.py]
        Theme[theme.py]
    end

    subgraph Shell
        Shell1[AppShell primary]
        Shell2[AppShell secondary]
        Home[HomeDashboardPage]
        Browser[SearchWindow]
        History[HistoryPage]
        AI[AIWindow]
        Personal[PersonalWindow]
        Library[LibraryPage]
        Settings[SettingsPage]
    end

    subgraph BrowserCore
        Tabs[TabManager]
        Page[BrowserPage]
        Web[QtWebEngine]
        Adblock[TrackingBlocker]
        Downloads[download_mgr]
        ExtBridge[extension_bridge]
        Workspaces[workspace_manager]
    end

    subgraph PersonalCore
        PService[personal_service]
        Life[life_service]
        Neural[NeuralGraphWidget]
        Boards[BoardView + Sticky + Ink]
    end

    subgraph AICore
        AIService[ai_service]
        Retriever[retriever]
    end

    subgraph Storage
        S1[prefs.json]
        S2[session.json]
        S3[history.txt]
        S4[bookmarks.json]
        S5[workspaces.json]
        S6[downloads_list.json]
        S7[extension_imports.json]
        S8[ai_index.json]
        S9[ai_settings.json]
        S10[tab_sets.json]
        S11[SafeVault/notes]
        S12[BrowserData]
    end

    Start --> Main
    Main --> Prefs
    Main --> Shell1
    Main --> Shell2
    Main --> Workspaces
    Shell1 --> Home
    Shell1 --> Browser
    Shell1 --> History
    Shell1 --> AI
    Shell1 --> Personal
    Shell1 --> Library
    Shell1 --> Settings
    Shell2 --> Browser
    Shell2 --> AI
    Shell2 --> Personal

    Browser --> Tabs
    Tabs --> Page
    Page --> Web
    Browser --> Adblock
    Browser --> Downloads
    Browser --> ExtBridge
    Browser --> Workspaces

    Personal --> PService
    Personal --> Life
    Personal --> Neural
    Personal --> Boards

    AI --> AIService
    AIService --> Retriever
    Retriever --> PService
    Retriever --> Life

    Prefs --> S1
    Browser --> S2
    Browser --> S3
    Browser --> S4
    Workspaces --> S5
    Downloads --> S6
    ExtBridge --> S7
    AIService --> S8
    AIService --> S9
    Browser --> S10
    Personal --> S10
    AI --> S10
    PService --> S11
    Browser --> S12
```

---

## 25. Small features that exist

Easily missed points that are still in the code:

- auto browser session restore
- recently closed windows/tabs in session state
- lazy-loaded bookmark/history/download sidebar panels
- browser page compatibility patch for some AI/web app hosts
- local support page `Cục Quản Lý`
- quick switcher
- save current tab sets for Search/AI/Personal
- save note from page
- save answer to note
- create task from AI answer
- passcode gating for AI/Personal
- local-only retrieval mode
- OpenRouter / Ollama / llama.cpp modes
- import/export profile backup
- native dark title bar on Windows
- SHA1-URL favicon cache
- per-site permission persistence
- extension JS injector system in `Extensions`

---

## 26. Limitations and practical notes

- Some old text in the repo still carries mojibake/encoding artifacts, especially in old docs and
  some old UI literals.
- Notes categories currently use a folder structure instead of database metadata.
- The neural graph in notes is a custom visual animation, not a real 3D engine.
- The extension bridge is currently a JSON/import-center workflow, not a native messaging host.
- The app keeps growing, so this README prioritizes behavior-level accuracy and data flow over
  line-by-line code enumeration.

---

## 27. Quick verification directions

### Browser

- open 2 windows
- open a tab
- switch workspaces
- import a tab batch from a JSON file

### Personal

- `/note Work | Demo | hello`
- go to Personal > Notes
- change the category and save
- confirm the neural graph is running

### AI

- ask a question in the insight panel
- switch to the AI workspace
- save the answer to a note

### History / Library

- create a note/task/page save
- refresh Library
- refresh History

---

For even deeper documentation, the reasonable next step is splitting out:

- `ARCHITECTURE.md` for module architecture
- `DATA_MODEL.md` for file storage/schema
- `COMMANDS_AND_IMPORTS.md` for slash commands + extension bridge
- `PERSONAL_HUB.md` for notes/tasks/boards neural graph

For now, this README is the most complete single document for reading the whole system top-down.

---

*Previous README content preserved as the historical changelog. New development notes go in this file.*
