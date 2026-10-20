# Mei

[![CI](https://github.com/Annguyen0410/Mei/actions/workflows/ci.yml/badge.svg)](https://github.com/Annguyen0410/Mei/actions/workflows/ci.yml)

**Mei** is one tidy window for a study day: the pages you read, the plan you keep, the cards you review, the notes you write. It is built on **PyQt5/PyQt6 + QtWebEngine** — a real Chromium underneath — and runs on both Qt bindings through the `litebrowser/qt_compat.py` shim: **PyQt6-WebEngine 6.11 (Chromium 140)** when it is installed, PyQt5 otherwise — and Settings refuses to be quiet about which one you got, because the fallback is Qt 5.15, which is Chromium 87.

It is deliberately not the best tool at any one job. It is the most convenient one. A full Chromium browser, a weekly planner, an SM-2 deck, notes with `[[wiki-links]]`, an AI workspace, a library and a settings center live in one process, because a **browser is where your reading already happens and a study desk is where it should end up**. There is no account and no cloud of ours: every byte stays in your profile folder, and the pieces talk to each other instead of to a server.

> **Docs**
> - 🚀 **Run & package** the app → [`RUN_AND_BUILD.md`](RUN_AND_BUILD.md)
> - 🧭 **User guide** (day-to-day usage) → [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)
> - ⌨️ **Command & shortcut reference** → [`docs/COMMAND_REFERENCE.md`](docs/COMMAND_REFERENCE.md)
> - 🏗️ **Architecture** → [`ARCHITECTURE.md`](ARCHITECTURE.md)
> - ⭐ **Structure & strengths** (vs. other browsers / planner / study apps) → [`docs/WHY_MEI.md`](docs/WHY_MEI.md)
> - 📜 **Changelog** → [`docs/CHANGELOG.md`](docs/CHANGELOG.md)

---

## Table of contents

1. [Download & install](#download--install-no-python-needed)
2. [Highlights](#highlights)
3. [Requirements & installation](#requirements--installation)
4. [First launch](#first-launch)
5. [The shell](#the-shell)
6. [The omnibar & feature finder](#the-omnibar--feature-finder)
7. [Workspaces](#workspaces)
   - [Home](#home)
   - [Browser](#browser)
   - [History](#history)
   - [AI](#ai)
   - [Personal Hub](#personal-hub)
   - [Library](#library)
   - [Settings](#settings)
8. [Themes & accents](#themes--accents)
9. [Focus & wellbeing](#focus--wellbeing)
10. [Privacy & security](#privacy--security)
11. [Data & local-first](#data--local-first)
12. [Text is copyable everywhere](#text-is-copyable-everywhere)
13. [Automation & interop](#automation--interop)
14. [Keyboard shortcuts](#keyboard-shortcuts)
15. [Development](#development)
16. [Troubleshooting](#troubleshooting)

---

## Download & install (no Python needed)

Every version is published as a GitHub Release with three files:

| File | What it is |
|---|---|
| `Mei.exe` | the whole app in one file (~170 MB) — run it, no installer |
| `Mei-<version>-web_support.zip` | the offline site folders Mei serves locally (~10 MB). **Unpack it next to `Mei.exe`**, so the folder reads `web_support\…` |
| `update.json` | the update manifest — version, download URL and the `sha256` of the exe |

Download from **[Releases](https://github.com/Annguyen0410/Mei/releases/latest)**. Data lives outside the exe
(`%LOCALAPPDATA%\Mei\runtime_data`), so replacing the file never touches your profile.

**Self-update.** From 0.7.0.0 on, Settings → *Updates* polls
`releases/latest/download/update.json`. A new build is offered as a dialog (a manual
*Check for updates* pre-selects **Yes**, a startup check pre-selects **No**), the download
is verified against the `sha256` published in the manifest **before** anything is replaced,
and the swap keeps `Mei.exe.bak` for a 15-second rollback window. A machine with no
internet can upgrade from a folder instead: copy `update.json` + `Mei.exe` into
`update\` next to the exe (`RUN_AND_BUILD.md` §5.5).

> Releases before 0.7.0.0 pointed at an update URL that was never deployed, so those
> installs cannot self-update — download 0.7.0.0 (or newer) once by hand; from there the
> channel works.

---

## Highlights

- **One loop, five stations** — capture → plan → study → review → reflect. Home reads every store (planner, deck, captures, pour journal, links) and offers the single next step with a **▶ Continue** button; `/flow` does the same from the omnibar.
- **One desk, not a menu** — Home opens on four blocks: what is on the plate **today**, what is **due** (late or landing this week), what you left **unfinished**, and the loop's one **next step** with ▶ Continue. The launcher grid is one click away behind **☰ All features**, not the first thing you see.
- **A search box that reaches your work** — the omnibar (`Ctrl+K`) finds app features *and* your own notes, cards, planner rows, tasks, saved pages and courses; Enter opens the item where it lives, not the workspace it lives in.
- **A study session you can sit down to** — **☕ Study session** on Home asks which cup (every cup is a pace: 15/25/45/50 minutes) and what you will finish before the timer starts; the pour lands in the same journal the weekly review reads.
- **Two directions, no cloud** — Settings → **Folder sync** merges this profile with a folder you already sync (OneDrive, Dropbox, a USB stick): *Preview* shows the plan, *Apply* keeps a backup and writes only what changed, and an edit always wins over a deletion.
- **Open doors** — the **Mei Bridge extension** (`Extensions/tab-window-bridge`) pairs with the same code as the phone and sends the current tab or your selection into Mei; `GET /api/mobile/today` lets **MeiRemote** open on today's desk; Settings → **Plugins** imports/exports Todoist, TickTick, notes and deck CSV from manifests that declare fields instead of running code.
- **Seven workspaces** behind one left rail — Home, Browser, History, AI, Personal, Library, Settings (`Ctrl+1…7`).
- **Omnibar feature finder** — type any letters (`b`, `s`, `per…`) into the search box and get a live list of every matching feature; Enter or click jumps there. Works for *every* letter.
- **Text selection everywhere** — every label is selectable with the mouse, every button has right-click **Copy text**.
- **Full Chromium browser** — tab desk with workspace tabs, colored tab groups, split view, web panels (Telegram, WhatsApp, Discord…), tab hibernation, memory saver, zen mode.
- **Personal Hub** — notes with Obsidian-style `[[wiki-links]]` and a neural graph, a **weekly student planner** (courses, deadlines, focus blocks, ▶ Study sessions that credit their minutes back), tasks, **SM-2 flashcard review**, calendar with ICS, sticky boards, files, sites.
- **AI workspace** — RAG-local, OpenRouter, Ollama and llama.cpp providers, passcode-gated.
- **20 café themes** — including *Rainy Day / Rainy Night*, *Sunrise* and *Autumn Table* — with auto day/night pairing and 9 accent presets.
- **Privacy-first** — adblock, https-only, third-party cookie blocking, VPN/proxy support, incognito tabs, password vault, per-site permissions.
- **Local-first** — all data lives on your machine under the profile folder; no mandatory accounts or cloud.

---

## Requirements & installation

- **Python 3.11+** (Windows Store or python.org).
- The repo ships a virtual environment (`.venv`) with PyQt5, PyQt6, QtWebEngine, cryptography, etc.

```powershell
# From the project folder (the one containing browser.py / run.bat / .venv):
.\run.bat
# or directly:
.\.venv\Scripts\python.exe browser.py
```

Recreating the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Building a standalone `.exe` (PyInstaller), packaging and troubleshooting are
> covered in [`RUN_AND_BUILD.md`](RUN_AND_BUILD.md).

---

## First launch

The first run opens a 3-step **onboarding wizard** (once per profile):

1. **Theme** — pick a café palette with a live preview.
2. **Import** — optionally pull tabs from another browser.
3. **Bridge** — enable the Android bridge or the global hotkey.

Afterwards you land on the **Home** dashboard. If you already have saved tabs, it opens the **Browser** workspace instead.

---

## The shell

- **Left rail** — workspace switcher with a profile label. The rail itself can be **collapsed** (click the «/» button), **expanded**, and **dragged wider/narrower**.
- **Top bar** — brand, the **omnibar** (search box), and the Snapshot / Insights buttons.
- **Status strip** — theme pill, sync state, status hints (e.g. command descriptions as you type).

### The omnibar & feature finder

The search box at the top is the command center of the whole app:

| You type | What happens |
|---|---|
| `python.org` | Navigates to the URL |
| `best coffee recipes` | Web search with the active engine (Google, Bing, DuckDuckGo, …) |
| `b` / `per` / any letters | **Feature finder** — live list of matching workspaces, Personal pages, sites and slash commands |
| `/task Buy milk` | Runs a slash command (creates a task) |

**Feature finder behaviour**

- Any **letter or word** filters the registry: titles, categories and keywords are all searched (`b` → Browser, Boards, Bookmarks…; `fortune` narrows to Fortune & Reflection).
- A single letter that matches nothing shows the **whole registry**, so the list is never empty — keep typing to zoom in.
- `↑` / `↓` move through results, `Esc` closes, **Enter or click** jumps to the feature.
- **Password-protected areas** (AI, Personal) prompt for the passcode first, then open automatically.
- The omnibar keeps keyboard focus while the list is open, so you can keep typing to narrow.
- Slash commands keep their own autocomplete (`/tas` → `/task …`), and argument-taking commands prefill the box (`/task `) so you finish them by typing.

> The full command list is in [`docs/COMMAND_REFERENCE.md`](docs/COMMAND_REFERENCE.md).

---

## Workspaces

### 🏠 Home

The dashboard: time-of-day greeting, a **“Your Week”** 7-day activity chart, quick-launch tiles, version badge, recent notes / today's tasks / recently closed pages, and a “Where time goes” breakdown. Everything scrolls naturally — no squished cards.

Home also carries a **This Week** card — the reflect station with numbers: a seven-day text spark, minutes poured, days studied, your streak, and the rows nothing touched this week ("overdue 3d", "never studied"), with **▶ Study the oldest one** turning that reading into a pour.

The **Today** card is the entrance to the loop: one merged agenda (planner deadlines, planner time blocks, quick inbox rows — overdue first, each badged *Planner* / *Inbox*), the loop line (*“1 overdue · 5 card(s) due · next: ▶ Study “Late essay” (40 min)”*), **▶ Continue** (runs the recommended step — including starting the pour) and **→ Planner** (promotes the selected inbox row into the Weekly Plan, keeping a task↔item link). Double-click any row to open it where it lives. The **Morning Brief** below ends with **▶ Next step** and **📝 Save as note** writes the whole briefing — next step included — into the vault.

### 🌐 Browser

The Chromium workspace.

- **Workspace tab desk** — the left desk holds your tabs, with group color dots, speaker chips for playing tabs, hibernation state, and a filter box (`Ctrl+Shift+F`).
  - The divider between desk and page: **click once** to collapse/expand, **drag** to resize, **double-click** to toggle. The rail never disappears and can always be brought back.
- **Tabs** — new (`Ctrl+T`), incognito (`Ctrl+Shift+N`), reopen closed (`Ctrl+Shift+T`), duplicate (`Ctrl+Shift+D`), middle-click to close, groups that fold/unfold and survive session restore.
- **Split view** — “Show beside” puts two live pages side by side.
- **Web panels** — ◫ docks Telegram, WhatsApp, Discord, Messenger, Spotify, YouTube Music, Instagram, Gmail or any URL in a slim right rail sharing the main profile (logins persist).
- **Zen mode** (`Ctrl+Shift+Z`) — hides every chrome surface for pure reading; Esc exits.
- **Performance** — background tabs auto-hibernate after an idle limit; the memory saver freezes tabs when the process working set grows (`Ctrl+Shift+M` to optimize now).
- **Reading** — reader-friendly view, reading list, scroll-progress tracking on saved pages.
- **Downloads** — panel with toasts, stable IDs, incognito downloads supported.
- **Find bar** (`Ctrl+F`) — sticky Chrome-style bar with next/prev and match count.
- **Save & share** — screenshot (`Ctrl+S`), save as PDF (`Ctrl+Shift+S`), print (`Ctrl+P`), extract page text (`Ctrl+Shift+E`).
- **Devtools** (`F12`) — one reusable developer-tools window.
- **Clipboard history** (`Ctrl+Shift+V`) — last 20 copied entries, restore or paste & go.
- **Crash safety** — session autosave every 5 minutes; a dead renderer auto-reloads once, then marks the tab `[Crashed]`.

### 🕐 History

Searchable browsing history. Rows open in the current tab or in background tabs (middle-click), with deduplication.

### ✨ AI

Ask one assistant across the current page, your notes, tasks, saved pages or the whole workspace.

- Providers: **RAG local only**, **OpenRouter**, **Ollama**, **llama.cpp**.
- `/ask <question>` asks with the current workspace context; the Insights panel shows what the AI is reading.
- Thread history, prompt templates, “save answer to note / task”, export.
- The workspace is **passcode-gated**: first open sets a passcode, later opens prompt for it.

### ◧ Personal Hub

Eight pages behind their own nav rail (which is also **collapsible and draggable** like the browser desk):

- **Overview** — today at a glance plus a **12-week focus-streak heatmap** (one cell per day, month/year axis, today ringed with the date).
- **Notes** — SafeVault notes with Obsidian-style `[[wiki-links]]` (autocomplete, Ctrl+click to open/create, backlinks panel), categories, a neural-graph view, find & replace, autosave, move-by-drag. A **Related** panel links the note to planner items (`🔗 Link…` / **Unlink**); cards made from the note appear there too.
- **Weekly Plan** — courses (name, code, colour, schedule, credits) and assignments/exams/projects on a week board; pick a course when adding items or blocks, drag to reschedule, double-click a block to edit, **▶ Study** pours a focus session for the selected entry and the minutes are credited back to it (the label then points at the deck: `next: 🧠 Review …`). *Planner first*: dated deadlines live here, **Tasks** is the quick inbox, and Home's **Today** card shows both — with a one-click promotion from inbox to plan.
- **Tasks** — quick inbox with due dates; “⇄ Make flashcard” turns selected note text into a study card. Dated study deadlines belong on the **Weekly Plan** instead.
- **Review** — **SM-2 spaced-repetition flashcards**. Browse with `←`/`→` or the ‹ › buttons, flip with Space or a click, grade **Again / Hard / Good / Easy** (keys `1–4`), switch **Due / All cards** mode, delete cards, watch the position counter. `/review` opens it from anywhere.
- **Calendar** — events with **ICS import/export** (stdlib parser, no cloud).
- **Boards** — sticky idea boards with links between cards.
- **Files** — your personal root directory.
- **Sites** — your own site list, separate from browser bookmarks. **Add site** keeps private links handy; **Include bundled sites** toggles the seeded shortcut tiles (off = only sites you added — nothing is ever deleted by the toggle).

### 📚 Library

Saved pages, bookmarks, downloads, reading list and RSS feeds — the “save for later” home. `/save-page` stores the active page; `/read` and `/reading-list` manage reading progress.

### ⚙️ Settings

- **Theme & accent** pickers with live swatches, plus auto day/night.
- **VPN / proxy** — enable, auto-connect, PAC URLs, smart restart, leak test.
- **Privacy** — adblock filter file & subscriptions, https-only, third-party cookie blocking, tracking blocker.
- **Permissions** — per-origin camera/mic/notifications decisions.
- **Profiles** — separate profiles with their own data, passcodes and preferences.
- **Startup** — new tab / restore / home page; startup tabs.
- **Extensions** — user scripts; **Routines** scheduler; **RSS**; import/export.

---

## Themes & accents

16 café palettes:

- **Light (day):** `minimal` (Latte Cream), `latte`, `rose-day`, `dawn`, `matcha-day`, `sand-day`, `lavender-day`, `cocoa-day`
- **Dark (night):** `cafe-night`, `minimal-night`, `ocean-night`, `forest-night`, `midnight-ember`, `lavender-night`, `blueberry-night`, `mocha-mint`

9 accents: `brass` (default), `caramel`, `ember`, `teal`, `violet`, `sky`, `rose`, `matcha`, `slate`.

- Switch instantly: `/theme <id>` and `/accent <id>`.
- **Auto day/night** flips to each theme's sibling palette at 06:00 / 18:00 (e.g. Sakura ↔ Ember Night).
- Text/colors are WCAG contrast-audited; the new-tab page, dialogs, find bar, toasts and custom widgets all follow the active theme + accent.

---

## Focus & wellbeing

- `/focus <minutes>` starts a **café pour**; the **distraction shield** blocks social/autoplay hosts while it runs (or “always on” in Settings).
- `/status` shows the timer; `/cafe` opens the focus journal/controls.
- **20-20-20 eye-break** nudges during long pours.
- **System tray** — quick note, 25-minute pour, VPN status.
- **Native Windows toasts** for downloads, focus events, monitors and routines.

---

## Privacy & security

- **Adblock & tracking** — filter lists and subscriptions, https-only (auto-upgrade http), third-party cookie blocking.
- **VPN / proxy** — status card with visible IP/country/ISP, auto-connect, PAC URLs, and a **leak test** comparing the OS path with the browser path.
- **Incognito tabs** — private profiles, downloads work, no session persistence.
- **Password vault** — save logins after form submit; master-passcode protected with atomic writes.
- **Passcode-gated workspaces** — AI and Personal require a passcode per profile.
- **Chrome-shape shim** — optional script that impersonates a real Chrome fingerprint for sites that block embedded browsers (Google, OpenAI, Anthropic…), togglable in privacy settings.

---

## Data & local-first

- Everything is stored under your **profile folder** (`BrowserData` inside the project data directory) — profiles, session, history, notes (SafeVault), tasks, boards, flashcards, preferences.
- **No mandatory accounts, no cloud**: “Snapshot” flushes local state to disk; `/sync` pushes/pulls a self-hosted snapshot only if you set one up.
- The app **never deletes your data on launch** — removals only happen from explicit user actions, and every destructive action asks for confirmation.
- Keep your profile folder to keep your data; the app does not touch files outside it.

---

## Text is copyable everywhere

Every label in the app (titles, subtitles, stats, hints) is **selectable with the mouse** and copyable with `Ctrl+C`. Buttons can't have selectable text in Qt, so every button also has a **right-click → “Copy text”** menu that copies its label to the clipboard.

---

## Automation & interop

- **Routines** — schedule daily automations (`/routines`), e.g. `07:30 Mon–Fri → /template daily` with a native toast.
- **Page monitor** — “Monitor this page” watches a page and toasts when it changes (15-min raw-HTML checks).
- **Export center** (`/export`) — notes → Markdown zip bundle or a themed static HTML mini-site.
- **Calendar ICS** — import/export without any cloud.
- **RSS reader** — RSS2 + Atom under the web-panel menu, items open as tabs.
- **Global hotkey** `Ctrl+Alt+M` — quick-note overlay from anywhere in Windows.
- **Android bridge** — push links, files and notes from your phone over Wi-Fi (optional); `GET /api/mobile/today` answers the other way, with the desk (today, due, unfinished, next step, cards due) so MeiRemote opens on today instead of an empty screen.
- **Mei Bridge extension** — `Extensions/tab-window-bridge` for Chrome / Opera GX sends the current tab or the selection straight into Mei as a note, a flashcard or a saved page (tags included), and still exports a whole multi-monitor workspace as JSON/ZIP for the Import Center.
- **Folder sync** — Settings → Folder sync merges Mei with a folder you already sync: three-way merge against a baseline, edits win over deletions, preview before writing, backup on every apply, and unwritable/unreadable folders are reported instead of half-applied.
- **Plugins** — Settings → Plugins lists the manifests in your profile's `plugins/` folder: Todoist / TickTick CSV in, notes or deck CSV out. Declarative only — no plugin runs code.
- **Self-update** — checks for new releases and can install them.

---

## Keyboard shortcuts

The complete list lives in [`docs/COMMAND_REFERENCE.md`](docs/COMMAND_REFERENCE.md). The essentials:

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Focus the omnibar |
| `Ctrl+1 … Ctrl+7` | Switch workspace |
| `Ctrl+T` / `Ctrl+Shift+T` | New tab / reopen closed tab |
| `Ctrl+Shift+N` | New incognito tab |
| `Ctrl+W` | Close tab |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Ctrl+L` | Focus the URL bar |
| `Ctrl+F` | Find bar |
| `Ctrl+Shift+V` | Clipboard history |
| `Ctrl+Shift+Z` | Zen mode |
| `Ctrl+Shift+K` | Quick switcher (commands, tabs, bookmarks, history) |
| `F12` | Developer tools |
| `Ctrl+Alt+M` | Quick note (global) |

---

## Development

```
browser.py                     Entry point
litebrowser/
  core/        prefs, command registry, app paths, storage, version
  services/    life service, AI, flashcards, focus, security, sync, …
  ui/          shell (AppShell + pages), browser window, Personal Hub, AI window,
               theme/QSS, dialogs (VPN, profiles, command palette, …)
  browser/     tab manager, new-tab page, page wrapper, adblock, downloads
tests/         pytest suite
```

```powershell
# Tests
.\.venv\Scripts\python.exe -m pytest tests/ -q

# Lint (the project enforces F-codes)
.\.venv\Scripts\ruff.exe check litebrowser/ tests/ --select F,E9
```

Architecture notes: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| App won't start / silent exit | Run `python browser.py` from a terminal and read the traceback; ensure you're in the project folder |
| Old behaviour after edits | Close **all** Mei windows (check the tray) and start one fresh instance — Python doesn't hot-reload |
| Font warnings at startup | Harmless: Qt no longer ships fonts; the OS fonts are used |
| Build the `.exe` | See [`RUN_AND_BUILD.md`](RUN_AND_BUILD.md) (PyInstaller with `--collect-all PyQt6.QtWebEngine*`) |
| Data locations | Everything under your profile folder (`BrowserData`); back it up to keep your data |

---

*Mei is its own application. Some shortcut tiles in Personal → Sites (and the corresponding `/…` commands) link out to separate web apps that Mei neither contains nor depends on.*