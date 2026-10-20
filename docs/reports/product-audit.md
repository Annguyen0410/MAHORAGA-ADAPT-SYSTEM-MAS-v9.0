# Mei product audit — stabilization and Study Café UX

Date: 2026-09-30. Changes remain local and unreleased; no commit, push, deployment, installation or release publication was performed. API keys, private environment files, real profiles and production session stores were not read or modified. Desktop QA used disposable profiles; browser QA used a loopback-only static preview. Earlier journeys used incognito data; the final persistence/cross-tab recheck used synthetic data on a fresh ephemeral localhost origin in regular tabs because this host's incognito preview cleared storage on reload.

## Architecture

- **Desktop:** Python service layer with JSON/Markdown profile stores, a Qt workspace shell and QtWebEngine browser views. This environment runs Qt 6.11.2 / Chromium 140.0.7339.225 through the existing Qt façade. The application also retains its Qt5 compatibility path; this pass did not rerun the entire suite on Qt5.
- **Web:** bundled local-first apps keep data in localStorage/IndexedDB. MAS additionally has an Express REST service. Its server tests use temporary stores, ephemeral loopback listeners and disabled environment loading.
- **Android/extension:** a versioned bearer-token bridge receives captures and serves the same desk model used by Home. The extension uses the matching pairing/parser contract. The Kotlin/Compose MeiRemote source and signing materials are absent, so a signed APK and phone UI cannot be verified here.
- **Shared navigation:** [the packaged manifest](../../litebrowser/data/chain.json) is canonical; [the asset builder](../../tools/build_shared_assets.py) generates six public manifest/script mirrors and the extension archive. Stable app IDs, URLs and Unicode directory names were preserved.

## Bugs Fixed

- Serialized profile read/modify/write transactions, atomic finite JSON writes and schema checks prevent lost updates and accidental overwrite of corrupt/future stores. Focus, scheduler, planner, card and study-credit edge cases now have focused regression coverage.
- Desktop backup import is bounded and path-safe, with staged sparse restore and byte rollback. Export preserves an existing destination on failure, escapes titles, rejects unsafe URL schemes and writes current HTML notes rather than carrying deleted pages forward.
- Sync pulls before pushing, handles bootstrap safely, preserves conflicting notes and does not advance folder baselines after failed publication. Password matching now respects scheme, host and port; captured credentials are not saved against a navigated-away page.
- Concurrent note editors no longer silently overwrite newer content: autosave retains the draft, and explicit Save preserves both versions. Failed persistence cancels close; quit/update/restart preflight saves rather than abandoning drafts.
- Private workspaces and cached context are cleared/hidden on lock, including late AI results, Home insights and private history controls. Passcode gating is not full vault encryption.
- Mobile bridge framing, UTF-8/JSON, finite payloads, depth, filenames, URLs, concurrency and request deadlines are checked. The extension awaits downloads, bounds fetch/body waits and recovers controls after errors.
- MAS validates malformed local data, backup size/schema, quota failures and server writes/origins. Blank check-in scores no longer become zero-valued records; validation retains the typed draft. LinkLumina waits for committed IndexedDB transactions, preserves failed-save forms, recovers corrupt layouts/rules and confines service-worker caching to owned static assets.
- Management Export Studio previously crashed for non-full report modes and scoped exports. All **84 scope × mode × format combinations** now render. Project Hub cards no longer nest alternate-link anchors, which created empty grid cells in the live browser. Restore validates all values before writing, bounds files, checks simple-ZIP payload CRC and rolls back partial storage failures.
- Management catalog/Visualgraph now escape imported HTML, validate records without overwriting unreadable bytes, save before changing memory, retain drafts on quota failure and refresh across tabs. Graph geometry is derived from content instead of trusting imported node/style fields; deleted graphs clear stale export summaries. Reduced-motion users get a static graph.
- World Leaderboard validates imported input fields before applying them, bounds scoring and preserves corrupt history/unsaved input on storage failures. MAS discards late create/assessment/deep-analysis replies after their session is replaced or cleared, and clear/template actions retain memory on failed writes.
- Failed note moves restore raw reference stores; if a second disk failure blocks rollback, both note files are retained to keep references resolvable. Folder-sync Preview now runs through the existing background relay and recovers controls without publishing data.
- Desktop web-copy and release-ZIP paths share a public-asset filter. Backend stores, keys, profile directories, dependencies, symlinks and the personal legacy report are excluded. Generated-output cleanup also removes old non-public payloads without reading their contents, and blocked cleanup/copy is a build failure. Only temporary test destinations were cleaned during this audit; real build output was not pruned.

## Desktop UI/UX

- Study Café Home puts the next step first, with Go/Enter navigation, a minute-updated clock and secondary reporting/launch controls collapsed until needed.
- Responsive cards and size hints prevent horizontal scroll deadlocks. Wide **1440×900** and narrow **800×640** layouts were reviewed; notes switch to a vertical split and hide secondary category tools when narrow.
- Note tools are collapsible; save status, within-note search, image controls and deep links are clearer. Switching notes/workspaces flushes pending edits, and deep links clear stale filters.
- Icon navigation has accessible names. Library filters work without requiring a query; quick Inbox capture is refreshed immediately. Onboarding preserves the current appearance, supports a real Skip, and continues correctly after import.
- Shipped Desktop labels, café drink names, commands, bridge/extension messages, Management Hub screens, export output labels, reference defaults and shared app subtitles are English. LinkLumina date formatting and progress wording are English too. Existing user content, proper names, Unicode search support, IDs, directory paths, historical documents and the legacy personal birth-chart report remain unchanged, as requested in the scope confirmation.

## User Experience QA

| Verification | Final result |
|---|---:|
| Full Python regression | **863 passed; 749 subtests passed** |
| LinkLumina Node suite | **32 passed** |
| MAS suite, including real temporary HTTP CRUD | **11 test files passed** |
| Management export/restore harness | **84 export combinations plus validation/rollback checks passed** |
| Management/Leaderboard reliability harnesses | Malicious data, corruption, quota, cross-tab, deletion, reduced-motion and bounded-scoring checks passed |
| Packaging regression | Public-copy/ZIP filtering, stale private cleanup, blocked cleanup/copy and ignored-source guards passed |
| Native Desktop journeys | **19/19 passed** |
| Engine smoke | **24/24 passed** |
| Ruff F/E9 and Python compilation | Passed |
| JavaScript syntax | 44 public/extension JavaScript files passed; inline-script checks passed in the earlier pass |
| Generated assets | Six manifest mirrors match canonical JSON; extension ZIP matches source bytes |

Evidence: [full test results](final-tests.xml), [native journey results](product-qa/journeys.json), [web journey record](product-qa/web-journeys.json), [screenshot gallery](product-qa/gallery.html), [wide Home](product-qa/home-wide.png), [narrow Home](product-qa/home-narrow.png), [wide notes](product-qa/notes-wide.png), [narrow notes](product-qa/notes-narrow.png).

Native checks covered locked Home, note switching, deep links, concurrent draft conflict, Library refresh/filter, linked study start, narrow/wide bounds, repeated-navigation timer counts, asynchronous folder preview/control recovery, profile-wide multiwindow locking, failed-close persistence, normal shutdown and reopening saved content. Browser checks covered LinkLumina capture/search/edit persistence; MAS example→local plan→evolution, blank-score draft retention and valid zero discomfort; English Management Hub navigation; scoped exports; Visualgraph creation/persistence; and an eight-card Hub grid with no empty cards or nested anchors. The final live recheck created a synthetic Visualgraph topic, reloaded it, reopened its graph, observed it in Export Studio in a second tab, then deleted it and verified the export preview and active summary cleared without refresh. Both tabs had no captured console errors. A flaky event-filter probe was isolated from onboarding, updates, tray and hotkeys before the final successful full rerun.

The static preview intentionally has no application backend: MAS health probes return 404 and local mode remains usable. No external AI invocation occurred. An earlier engine-smoke process crashed at interpreter teardown despite its assertions passing. The harness now explicitly destroys pages before profiles and flushes deferred deletes; the final native Windows-platform rerun passed all 24 facts and exited zero. GPU-context warnings still appeared with GPU intentionally disabled; hardware acceleration is not certified. This project has no configured static typechecker, so lint/compile checks are not represented as a typecheck.

## Features Added

- Safe concurrent-note draft preservation instead of silent data loss.
- English interface regression guards while retaining legacy identifiers and Unicode user content.
- A deterministic cross-app navigation/extension asset builder and key-free QA tooling.
- Asynchronous folder-sync preview, reduced-motion graph rendering and cross-tab catalog/graph/export refresh.
- Public web asset/vendor ignore exceptions and shared copy/ZIP filtering, so maintained sources can be tracked without including backend stores or keys.
- Truthful file-catalog and export guidance: the Management Hub records **metadata only**. Its 10 GB figure is a planning target, not allocated storage; selecting a file does not upload or back up its contents.
- Explicit missing-source states for optional World Monitor/MiroFish integrations, with reference instructions rather than misleading launch links.

## Performance & Reliability

- Atomic writes, bounded imports/HTTP payloads, guarded origin matching and save-before-shutdown improve failure recovery.
- Desktop timers, executors, listeners, event filters and hotkeys shut down with their owners. AI work does not repopulate locked private surfaces.
- Web request deadlines and storage-before-memory ordering avoid hanging controls and false-success writes. Optional bookmark metadata is time-bounded and no longer causes repeated full-library writes.
- Responsive grid minimum-size fixes remove narrow-window overflow. Existing Visualgraph glow sprites/node lookup and hidden-page animation suspension remain in place, with reduced-motion rendering added. Folder preview no longer blocks the GUI thread.
- Performance claims are limited to exercised flows: this pass did not perform a long-duration memory soak, device battery benchmark, cloud load test or packaged installer certification.

## Remaining Technical Debt

1. **Real Android QA is blocked:** MeiRemote source/build configuration/signing and a test device are needed for installation, pairing, rotation/background lifecycle and mobile accessibility checks. Bridge contract tests are not a substitute for this.
2. **External integrations remain unverified:** cloud AI/auth, HTTPS sync against a real provider, production deployments, missing World Monitor/MiroFish source, hardware GPU behavior, actual process restart and a fresh packaged installer were not run.
3. **Privacy is gating, not full encryption:** ordinary JSON/Markdown profile data and web storage remain readable at rest. A passcode does not make every workspace store encrypted.
4. **Sync semantics:** HTTPS snapshot sync is not a server-side compare-and-swap/tombstone protocol. Folder preview is now asynchronous, but large-vault stress testing and cross-process/cloud conflict races still require dedicated validation/design.
5. **Management apps:** the file catalog is not a real file vault. Malicious-content, malformed-record, quota and cross-tab regressions now pass, but localStorage provides no compare-and-swap for simultaneous writers. Restore rollback is best effort if the browser refuses rollback writes, and this case reports an explicit recovery warning. Very large records/collections need stress tests.
6. **Bundled-source delivery:** public app foundations/styles/vendor assets and backend source/dependency manifests now have precise ignore exceptions, while backend stores/private configuration remain ignored. Guards verify public bundle sources are not ignored and copy/ZIP tests share the same filtering policy. These additions remain uncommitted; no clean-checkout dependency install, fresh executable build or installer certification was performed. Dependency/license inventory and a reproducible release build remain release work.
7. **Language scope:** personal data, historical documents, legacy reports, proper names, compatibility paths and external websites keep their original language. Newly shipped interfaces are English; saved user-customized site titles are not overwritten.
8. **Coverage limits:** no formal accessibility audit, all-device browser matrix, long-running real-data soak or static typecheck was performed. Tested evidence is recorded above, not generalized into a production-readiness claim.
