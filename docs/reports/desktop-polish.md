# Desktop polish and maturity assessment

Date: 2026-09-30. Scope: Desktop only. No Web/Android implementation audit or modifications, deployment, commit, push, real-profile inspection, API-key access, or authenticated external workflow testing. Existing bundled assets were only consumed by the normal EXE build. Disposable synthetic profiles were used for QA.

## Fixed

- Headers in AI, Weekly Plan, Review and neighboring surfaces now receive layout stretch instead of leaving unused width to a trailing spacer. Shared page/section headers use expanding size policies. Font reduction was not the wrapping fix.
- Compact glyph buttons no longer combine fixed 28px boxes with large horizontal padding. Calendar import/export are explicitly labeled; overflow and Review glyphs have usable content space.
- Overflow menus keep Qt parent/modal ownership, inherit the active window stylesheet at opening, and use connected native actions. Removed page-wide graphics opacity effects: their finished callback caused a reproducible native access violation when deleting the emitting effect during teardown. The compositing layer also complicated native popup interaction. Mouse and keyboard activation inside a modal dialog pass, and actual board More entries were clicked in native QA.
- Board saves preserve tool, opacity, paper and geometry records, return failure rather than discarding the canvas, and restore the original selection after a failed switch. Autosave is stopped before switching/deleting. Refresh and repeated deep links preserve Undo. External board changes are detected before overwriting; a Save canvas as a new board action preserves a conflict as a separate record.
- Settings had two distinct checkboxes assigned to the same attribute: account-local snapshot state was overwritten by remote-sync state. They are now independent. Routine refresh preserves unsaved form drafts.
- Browser Back/Forward reflect actual engine history; Reload becomes Stop while loading and resets even on failure. Escape stops loading. Zoom reset is a keyboard-focusable tool button rather than a clickable label. Permissions/hotkeys dialogs receive the proper parent.

## UI/UX

Shared foreground/surface tokens, compact input styles (including date/time editors), consistent named button roles, calmer hierarchy, expanded headers and intentional secondary controls reach Desktop workspaces. Advanced planner fields, course management and focus-block creation remain available behind clearly labeled expanders. All Settings capabilities remain available, grouped into focused categories rather than one long wall of cards.

Wide (1440 × 900) and narrow (800 × 640) screenshots cover Home, Notes, AI, Board, Calendar, Weekly Plan, Browser, Settings, Tasks, Review, Files, Sites, Overview, History and Library. [Screenshot gallery](product-qa/gallery.html). Small-window Board ink settings and the seven-day plan intentionally scroll horizontally instead of compressing controls/days into unusable hitboxes; zoom/navigation remain visible.

## Idea Board

- White default paper independent from light/dark chrome; custom paper selection persisted per board.
- Eight ink presets, swatches, arbitrary custom color selection and visible selected hex feedback.
- Pen, pencil, translucent marker, whole-stroke eraser, line, rectangle and ellipse. Size and opacity controls; marker/pencil have distinct width/opacity behavior.
- Zoom 10–400%, visible +/-/reset/Fit controls, Ctrl+wheel; fit on board load.
- Pan mode, normal scrolling, middle-drag and Space+drag; drawing uses scene coordinates through the view transform, not raw viewport coordinates. Shapes stay correctly positioned after zoom.
- Sticky cards remain draggable; links follow cards. Undo/Redo covers drawing, erasing, paper changes, cards, movement and links; Escape restores a cancelled gesture. History is session-local, capped at 40 steps and an approximate 8MB geometry budget.
- Not a professional illustration editor: whole-stroke erasing, finite 2200 × 1400 paper, and session-local history are intentional lightweight scope, not broken functionality.

## Calendar / Weekly Plan

The fourth supplied screenshot is Weekly Plan, not the month Calendar; both were addressed. Explicit Import .ics / Export .ics labels, accessible text month chevrons, theme-aware event marks, readable day hierarchy and upcoming-only event list replace missing glyphs and stale-event clutter. Calendar event time entry uses a native date/time picker instead of manually typed timestamps. Weekly Plan opens with the primary title/date/add workflow; type, deadline, priority, course and duration stay in Details. Focus blocks/courses have a separate expander. Start time reads HH:mm instead of an unexplained number of minutes; day labels use actual line breaks.

## Theme / Settings

Light, Dark, Windows System and legacy palette/scheduled modes are supported. Twenty existing palettes are retained; accent families now total fourteen, including sage, terracotta, iris, petrol and plum, plus arbitrary hex/custom picker accents. Surface, muted, soft, accent-text, filled-hover and accent-foreground roles are distinct. Automated contrast checks cover every palette × preset plus extreme custom accents, including normal/hover filled buttons and text on paper/cards/soft accents (4.5:1 target).

All embedded workspaces, browser inline chrome, internal new tabs, Calendar marks, tray and other open windows for the same profile refresh together. The System poll only compares small OS/preference state; it does not rebuild lists every two seconds. Existing automatic day/night preferences remain compatible. Appearance fields use a two-column layout; settings categories retain less-frequent functionality without showing every card at once.

## Browser

Navigation/loading state now communicates real browser state. Larger unpadded glyph hitboxes, responsive three-column sidebar controls on a narrow desk, vertically arranged New Tab/Control actions, short filter placeholder plus detailed tooltip, accessible zoom reset and proper dialog parenting remove clipped/overlapping chrome. The existing café new-tab identity is retained and follows custom appearance. Local engine-history Back/Forward and internal new-tab rendering were tested without external requests.

## Additional issues found and fixed

- Broad early theme substitution accidentally painted ordinary surfaces with accent foreground. Visual screenshot review caught it; corrected backgrounds and added a regression guard.
- Filled hover colors and soft-accent text needed distinct contrast treatment, especially for white/black custom accents.
- Refresh could destroy board history and stale deep links could leave newly created boards disabled.
- Calendar native white chevrons were indistinct on light paper; text-only arrows now use shared foreground tokens.
- Review's empty-state layout constrained text to a narrow central column despite available width. Vertical-only centering preserves full text width; Review header stretch and keyboard focus were repaired.
- Narrow browser footer actions overlapped, VPN text clipped, and five sidebar icons either clipped or shrank excessively. Responsive rows retain 32px controls.
- History search/actions overlapped and its technical summary clipped. Search and backup actions have separate rows; supporting text is compact, with detailed backup caveats in a tooltip.
- Sites controls clipped in narrow windows and its empty state incorrectly claimed the user's sites were hidden. Primary and preview options are separated, URLs wrap and wording correctly describes an empty personal list.
- Removed the unused immediate-persistence board-node helper after board creation moved to the undoable canvas snapshot path.

## Validation / limits of evidence

- Final full regression: **871 tests, 849 subtests passed**.
- **24 engine smoke checks passed** (loopback pages, interception/ad blocking, shared profiles, dark-script behavior, downloads and storage). Native focused regression also passed: **35 tests, 101 subtests**.
- Ruff F/E9 and Python compile checks passed. No configured static typechecker is present; compilation is not represented as typechecking.
- **56 native Desktop journeys passed**, [machine-readable facts](product-qa/journeys.json), driven by [QA harness](../../tools/product_qa.py). Qt test mouse input/held-button move events go through the actual viewport event pipeline; menus are clicked, not merely triggered programmatically.
- Dedicated regression tests cover modal mouse/keyboard overflow interaction, extreme custom colors, mocked Windows System mode, malformed strokes, save failures, board external-edit conflict preservation and Settings drafts: [Desktop regressions](../../tests/test_desktop_polish.py).
- The native crash found during combined teardown was fixed by removing graphics-effect fades; the complete suite and native focused subset were rerun successfully afterward.
- QA uses Windows widgets with software-rendering flags. Chromium reports GPU-context fallback warnings in this environment; passing workflows do **not** certify hardware-accelerated graphics across drivers. A native child WebEngine surface can be omitted by QWidget.grab after hide/show: narrow browser evidence composes that child's direct grab, and separately verifies its DOM/viewport. This is an evidence-capture limitation, not concealed as a passing screenshot.
- Live sign-in, provider AI, external sync endpoints and update downloads were not exercised with real credentials. Existing mocked/service regressions are not end-to-end certification of those services.

## Delivered Desktop EXE

[Mei.exe](../../dist/Mei.exe), version 1.0.0.0, **208,026,391 bytes** (~198.4 MiB). Python 3.11.9 / PyInstaller 6.19.0 / Qt 6.11.2. Board canvas and changed Desktop modules are present in the archive; all four built-in CSV plugin manifests remain packaged.

SHA-256:

```text
1d915cd724025c9a403b0eb0bcee15b6514dd520f69f11b0db560538001f7445
```

Final staged and final-location hermetic 35-second startup smoke passed: native Mei workspace, live app, two QtWebEngine children. Disposable profile/TEMP/LOCALAPPDATA and nonexistent local update metadata were used; only owned test descendants were stopped. A timed-out intermediate packaging attempt was rejected after smoke failure and rebuilt; it was never promoted. The delivered EXE was subsequently rebuilt from a cleared PyInstaller work directory, smoke-verified in staging and again at its final location, and only then promoted. Superseded and pre-polish EXEs were deleted, leaving the staging directory empty; local update metadata and this report match the final bytes/hash. Version/channel URLs were not promoted or uploaded. Private preserved-web-data was untouched. Historical exe-rebuild report describes the previous artifact, not this one.

## Product completeness

**Final maturity: Polished MVP.** Core local-first workflows are professionally usable and significantly more coherent; this is no longer merely a collection of functional screens. Evidence is strong for everyday navigation, study/planning, notes, lightweight creative boards, appearance and local persistence. It is not enough to claim near-production deployment readiness across the breadth of the app.

| Dimension | Assessment |
| --- | --- |
| Feature completeness | Core local browsing, notes, tasks, calendar, planner, review, board, library and backup workflows are present. Rich illustration/collaboration are optional, not required core gaps. |
| UI/UX completeness | Primary/secondary hierarchy and progressive disclosure are coherent; explicit screenshot defects addressed. Nested rails remain a product-learning cost when many workspaces are used. |
| Interaction completeness | Native buttons/menus, drawing, history, save errors and loading feedback have direct evidence. No claim that every advanced external-provider path received end-to-end testing. |
| Visual polish | Calm café identity and shared geometry/palettes; wide/narrow screenshots reviewed. Full OS/DPI/font-scale matrix is not certified. |
| Reliability | Strong automated regression and isolated packaged startup; lost-draft and teardown paths hardened. No long-duration field/upgrade history for this new build. |
| Edge cases | Malformed stroke values, interrupted gestures, failed writes, duplicate refreshes, external-edit conflicts and locked private workspaces are covered. Large imported data sets need measured stress certification. |
| Consistency | Desktop chrome, Settings, calendar and custom accents adapt together; bounded scroll is preferred to crushed controls. Native/HTML rendering remain separate technologies. |
| Accessibility | Accessible navigation names, meaningful labels, real focusable zoom, keyboard drawing history and contrast gates improved. No NVDA/UI Automation/high-contrast certification, especially for graphical canvas content. |
| Performance | Repeated-use navigation does not accumulate timers; System appearance poll is lightweight. Long-term and large-board/profile latency/RAM budgets were not measured. |
| Product identity | Distinct café/local-first study desk rather than a generic dashboard. Advanced browser, sync and AI concepts still require clearer first-use expectations in user testing. |

## What prevents the next level (Near-production)

These are concrete release/product-assurance barriers, not excuses to add arbitrary features:

1. **Reliability / deployment:** signed distribution, trusted installer/update/rollback and clean-machine upgrade evidence are not established by a local PyInstaller build and 35-second smoke. No signing material or release permission was available; this task does not claim a public release.
2. **Accessibility:** actual screen-reader semantics for the graphical board and calendar, Windows high-contrast, 125–200% DPI/text scaling and keyboard-only cross-workspace journeys need an assistive-technology/device matrix, not only names and calculated colors.
3. **Performance / scale:** profile services still use JSON/file-oriented persistence and board Undo snapshots. Thousands of cards/strokes and large note/history imports need UI-latency/RAM budgets and measured stress/soak results; this pass proves normal synthetic workloads, not unlimited scale.
4. **External integration reliability:** authenticated browser compatibility, AI provider errors/rate limits, remote sync and real update transitions need isolated integration staging with explicitly supplied disposable credentials. Offline mock/contract tests cannot answer them completely.
5. **Product clarity / UX:** usability testing must establish whether the nested shell/Personal/browser navigation and overlapping task/planner concepts are intuitive for new users, and whether saved-content routing is understood without explanations. Redesigning away useful capabilities based on an untested guess would not be responsible polish.

## Highest-impact route to a higher level

**High impact, in priority order:** (1) a reproducible signed release/upgrade/rollback pipeline and clean-machine acceptance suite; (2) NVDA/high-contrast/DPI acceptance journeys, prioritizing board/calendar and icon rails; (3) deterministic large-profile/large-board load and soak benchmarks, moving measured slow work off the UI thread; (4) isolated authenticated-provider/sync/update contract and failure tests; (5) focused first-use usability sessions to validate navigation and task/planner distinctions.

**Optional, not core completion barriers:** more board shapes, infinite canvas, collaborative editing, professional illustration tools, a palette marketplace, extra decorative animation, or more dashboard panels. They would not substitute for the assurance gaps above.
