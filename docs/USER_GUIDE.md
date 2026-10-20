# Mei — User Guide

A day-to-day walkthrough of the app. For the full command and shortcut list see
[`COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md); for running/building see
[`../RUN_AND_BUILD.md`](../RUN_AND_BUILD.md).

---

## 1. The shell (first thing you see)

- **Left rail** — switches workspaces: Home, Browser, History, AI, Personal, Library, Settings. Click the «/» button (or drag the divider, or press `Ctrl+1…7`) to switch; the rail itself can be collapsed/expanded and dragged wider.
- **Top bar** — brand, the **omnibar** (search box), Snapshot / Insights buttons.
- **Bottom status strip** — theme pill, sync state, status hints.

### Dialogs have one main button

Every window that opens from a button ends in the same row: the action it exists
for on the right (filled, and Enter runs it), at most one or two secondary
buttons beside it, a subdued **Close**, and a **“⋯ More”** menu holding the
occasional verbs — deleting history, importing bookmarks, renaming a tab set or a
workspace, the VPN leak test, and so on. Verbs you press rarely live in that menu;
destructive ones are marked with 🗑 and kept apart from the safe ones. Row-level chores
(tick a task off, remove a subscription, clear a board) are glyph buttons on the
list they act on.

### The omnibar is the command center

| What you type | What happens |
|---|---|
| `python.org` | Navigates to the URL |
| `best coffee recipes` | Web search with the active engine |
| `b` | **Feature finder** — a live list of matching features (workspaces, Personal pages, sites, commands). Enter/click jumps there |
| `/task Buy milk` | Runs the command (creates a task) |
| `/capture` | Opens a compact form for a note, task, saved link, or flashcard; page title, URL, and selected text are prefilled when available |
| `!` then a word | (if supported by the search engine) exact web search |

**Feature finder tips**

- Works for **any letter** — `s` → Settings, Sites, Sync…; if one letter matches nothing, the whole list is shown so you can browse.
- `↑`/`↓` move through results, `Esc` closes, Enter jumps.
- Password-protected areas (**AI**, **Personal**) ask for the passcode first and then open automatically.

## 2. The study loop — one process across the whole app

Mei has one work process, and every workspace is a station on it. Home shows where you
are and what is next; the other surfaces are where the step actually happens.

| Station | What lands there | Where it lives |
|---|---|---|
| **Capture** | A clipped page (`/save-page`, page menu → highlight clipping), a note (`/note`), a quick task (`/task`) | Library, Personal → Notes, Tasks |
| **Plan** | The dated commitment: an item with a course, a deadline, a focus block | Personal → **Weekly Plan** |
| **Study** | A Café Focus pour aimed at one item/block; elapsed minutes are credited back | **▶ Study**, `/focus`, `/status` |
| **Review** | The flashcard deck's due queue (SM-2) | Personal → **Review**, `/review` |
| **Reflect** | The Morning Brief, the saved brief note, the links between everything | Home card, `/brief` → **Save as note**, note **Related** panel |

**Home “Today” is the entrance.** Under the merged agenda (planner deadlines, planner time
blocks and quick inbox rows, overdue first) there is a loop line and two buttons:

- **▶ Continue** — runs the next step of the loop. It reads every store, so the button is
always the right one: *finish your pour → study the overdue item → today's block → review the
due cards → promote the inbox row → turn the clip into cards → plan the week*. The label
always says what will happen: if it offers a pour it starts one (with the duration shown), and
if it offers to plan a task it promotes that row into the Weekly Plan and opens the plan on it.
- **→ Planner** — promotes the selected inbox row into the Weekly Plan. The task is ticked off
and both sides stay linked, so nothing is lost and the row keeps a traceable history.

**`/flow` does the same thing from the keyboard**: it lists the five stations with their live
counts and then runs the next step. If a pour is already running, `/flow` reports it instead
of starting a second one.

The loop is closed at both ends: the **Morning Brief** ends with **▶ Next step** (the same
recommendation, in the daily note you can save with one click), the **planner** answers back
with `next: 🧠 Review 3 due card(s)` once a session is credited, and the **AI index** stores
the loop as a document, so `/ask what should I do next?` answers from your real state.

**This Week** (bottom of Home) is the reflect station with numbers: a seven-day text spark,
minutes poured, days studied, your streak, and the rows that got *nothing* this week —
"overdue 3d", "never studied". **▶ Study the oldest one** turns that reading into a pour.

**Mei will also start the step for you.** Settings → **Study reminders** picks how often a
native toast may carry the loop's next step (Off, 30 min … 8 h; default every 2 h). The loop
keeps its manners: it stays silent while a pour is running and between 22:00 and 08:00, and
if you already poured today and nothing is due, it says nothing at all.

---

## 3. Browser workspace

### Research workspaces

Open the browser's **Options → Sessions & Spaces → Save Research Workspace…** to save the current regular tabs as a named research collection and link one existing note and one existing task. The note and task remain in their original profile stores; the workspace records references, not copies. Incognito tabs are excluded. Use **Restore Tab Set…** to inspect saved collections and open one with **Open & merge**. The **⋯** menu includes **Replace current workspace…**; Mei asks before closing the tabs in the current browser workspace, and closed tabs remain available through Reopen Closed Tab.

Saving or restoring a research workspace makes it the active **Research desk** on Home. Home shows its linked items and offers **Resume tabs**, **Ask AI with context**, and **Capture to desk**. Captures from that desk link the new note, task, saved page, or flashcard back to the same collection. You can find named research workspaces from Ctrl+K by title.

The left desk holds your **workspace tabs** (groups with color dots, speaker chips for playing tabs, hibernation state). The divider between the desk and the page can be:

- **clicked once** → collapse/expand,
- **dragged** → resize,
- **double-clicked** → toggle.

Browser features worth knowing:

- **New tab** `Ctrl+T`, **incognito** `Ctrl+Shift+N`, **reopen closed** `Ctrl+Shift+T`, **duplicate** `Ctrl+Shift+D`.
- **Split view** — “Show beside” puts two live pages side by side.
- **Web panels** — ◫ docks Telegram/WhatsApp/Discord/Spotify/… beside the page (logins persist via the shared profile).
- **Tab groups** — color-coded, fold/unfold, session-persistent.
- **Zen mode** `Ctrl+Shift+Z` hides every chrome surface for pure reading; Esc exits.
- **Tab hibernation & memory saver** — idle background tabs freeze automatically; `Ctrl+Shift+M` optimizes memory now.
- **Address bar** — the connection chip in front of the address appears on web pages only
  (🔒 Secure / ⚠ HTTP). Internal pages (`about:`) and an empty field say nothing the address
  does not already show, so the chip stays out of the way.
- **Find bar** `Ctrl+F`, **PDF save** `Ctrl+Shift+S`, **screenshot** `Ctrl+S`, **print** `Ctrl+P`, **devtools** `F12`.
- **Help & Guide** `F1` — searchable list of every feature, shortcut and slash command;
  double-click a command to run it. It is generated from the same registries the app
  dispatches on, so it never documents something that does not exist.
- **Clipboard history** `Ctrl+Shift+V` — pick one of the last 20 copied items, restore or paste & go.

## 4. Personal Hub

The left rail inside Personal has its own collapse/expand (click the «/≫ button **or the divider** — the divider also drags to resize). Pages:

- **Overview** — today at a glance, a 12-week **focus streak heatmap** (each cell = one day, months + year on top, today ringed).
- **Weekly Plan** — courses (name, code, colour, schedule, credits) plus assignments, exams, projects and tasks on a weekly board. Pick the course when adding an item or a focus block, drag items between days to reschedule, double-click a block to edit it, and press **▶ Study** to pour a focus session for the selected item — its minutes are credited back to the item. *Planner first:* anything with a date or deadline belongs here; **Tasks** stays the quick inbox, and Home's *Today* card shows both side by side.
- **Notes** — SafeVault notes with Obsidian-style `[[wiki-links]]`, categories, a neural-graph view, find/replace, export. The **Related** panel under the editor links a note to a planner item (`🔗 Link…` / **Unlink**); cards made from the note appear there too, and deleting either side cleans the link up.
- **Tasks** — quick inbox with due dates; `⇄ Make flashcard` turns selected note text into a card. For study deadlines with a date, use the **Weekly Plan** instead.
- **Review** — SM-2 spaced-repetition flashcards. Browse with `←`/`→`, grade **Again/Hard/Good/Easy**, switch **Due / All cards**, delete cards, see the counter. `/review` opens it from anywhere, and the study label on the Weekly Plan hands you here (`next: 🧠 Review …`) once a pour is credited. The **⋯** button beside the counter moves the deck between here and Anki: **Import an Anki deck (.apkg)** brings a deck in — front, back, tags, and each card's interval/ease, so a deck you already studied keeps its schedule (every imported card is due now; media files stay in Anki; importing the same deck twice adds nothing) — and **Export as an Anki deck** writes the whole deck as an `.apkg` you open in Anki with *File → Import*. Decks exported by Anki 2.1.50+ are zstd-compressed and need `pip install zstandard`; the dialog says so instead of failing silently.
- **Calendar** — events, ICS import/export.
- **Boards** — sticky idea boards with links between cards.
- **Files** — your personal root directory.
- **Sites** — your own site list. **“Add site”** keeps private links separate from browser bookmarks; **“Include bundled sites”** toggles the seeded shortcut tiles (off = only sites you added; your data is never deleted either way).

## 5. AI workspace

- Providers: **RAG local only**, **OpenRouter**, **Ollama**, **llama.cpp**.
- **👁 Read my browser** (on by default) attaches the page you are reading — its real text, plus
the open tabs — to every question, labelled untrusted so the assistant reads it without obeying
it. Turn it off for purely local questions.
- **Use research desk** is off by default. Turning it on adds the active workspace's tab list and linked item contents to the next question, and keeps the preference for that profile. Linked note and task text may be sent to the selected AI provider; the checkbox tooltip discloses this, and the assembled context appears under **Show sources**. Mei treats those records as untrusted reference data. Incognito page contents are excluded even when **Read my browser** is enabled.
- **Capture tab** (Ollama only) grabs the visible page as an in-memory screenshot for local vision.
- `/ask your question` asks with the current workspace context; the Insights panel shows what the AI is reading.
- The workspace is passcode-gated: the first time you open it you set a passcode; later opens prompt for it.

## 6. Themes & focus

The theme picker includes additional art-directed families such as Aurora Glass, Sakura Twilight, Cyberpunk Neon, Midnight AMOLED, Arctic Aurora, Forest Sanctuary, Ocean Depths, Retro Terminal, Paper Studio, Monochrome Pro, Sunset Dusk, Dreamscape, Solarized Focus, High Contrast, and Glasshouse. The Glasshouse treatment uses opaque botanical surfaces for consistent readability across platforms. Themes recolor Mei's interface and new-tab page; they do not restyle third-party websites.

On Home, select **Customize Home** to hide, reorder (drag rows), or resize the four desk cards for the current profile. **Reset to default** restores only the dashboard layout.

In **Settings → Interface**, choose **Motion → System**, **Reduce**, or **Allow**.
System follows Windows' reduced-animation preference when the OS exposes it; on
other systems it keeps motion enabled unless you choose **Reduce**. This is saved
per profile. Reduce removes the new-tab page's animation and makes the browser tab
desk collapse immediately; it does not change animation or styling on websites.

- `/theme <id>` — 32 café and art-directed themes; `/accent <id>` — accent presets. **Auto day/night** flips paired palettes at 6:00/18:00; standalone art themes stay selected.
- **One theme, everywhere.** The dashboard charts, the tab desk, the connection chip and the
  new-tab page repaint when the theme changes (including the automatic 6:00/18:00 flip), so
  nothing is left in yesterday's colours. The "Your Week" and "Where time goes" charts sit on
  their card's own surface, so no panel ever shows a second shade of the theme behind the bars.
- **Dark web pages follow the app.** Pages are darkened while the app is in a dark palette;
  flipping **Menu → Privacy → Dark Mode on Web** stores your own choice either way.
- `/focus 25` — start a café pour; the **distraction shield** blocks social/autoplay hosts while it runs.
- `/cafe` — focus journal/controls; `/status` — timer state; 20-20-20 eye-break nudges during long pours.

## 7. Privacy & security

- **VPN / proxy** — Settings → VPN (or the shield card): status, auto-connect, PAC URLs, leak test.
- **Adblock** — filter lists, subscriptions, https-only, third-party cookie blocking.
- **Password vault** — save passwords after logins; master-passcode protected.
- **Permissions manager** — per-origin camera/mic/notifications decisions.
- **Google account** (Settings) — device-code sign-in; Mei never sees your password, and
  **Verify token** reuses the cached token without a network call whenever it is still fresh.
- **Passcode lock** (Settings) — **Lock now** re-locks Personal and AI without restarting Mei.
- **Diagnostics** (Settings) — the card names the engine you are running (Chromium, Qt, binding).
  If it says you are on the old branch — Qt 5.15 is Chromium 87 — some sites will refuse Mei,
  and installing the `PyQt6-WebEngine` package moves you onto the current engine.
  **Export diagnostics zip** writes one small archive with the log tail, every component version
  and the size/schema of each store, for a bug report. It never contains note text, passwords,
  vault files or browsing history; **Open log folder** shows where `mei.log` lives (that file
  does name pages you had open, so read it before sharing).

## 8. Sync, export & automation

- **Snapshot** (top bar) — flush local state to disk.
- **Routines** — schedule daily automations (`/routines`), e.g. a 07:30 daily plan note.
- **Page monitor** — “Monitor this page” toasts when a watched page changes; the list and
  removal live in Settings → **Watched pages**.
- **Export center** `/export` — notes → Markdown zip or a themed static HTML site.
- **The loop travels with your data** — planner items, courses, time blocks, flashcards and
  the link table ride backups (zip format v4) and self-hosted sync, so a restored profile
  resumes with the same next step. Old backups (v≤3) never wipe newer study data.
- **RSS** — mini-reader (RSS2 + Atom) under the web-panel menu.
- **Folder sync** (Settings → **Folder sync**) — point Mei at a folder you already sync
  (OneDrive, Dropbox, a USB stick). **Preview** shows what would move and writes nothing;
  **Apply** merges both sides, keeps a backup in `backups\sync-<time>\` and writes only the
  stores that changed. An edit beats a deletion; two different edits to the same row are
  kept as a conflict instead of one overwriting the other.
- **Send from your browser** — load `Extensions\tab-window-bridge` unpacked in Chrome or
  Opera GX, paste the code from Settings → **Quick pairing** (the same code as the phone),
  then use **Send this tab to Mei** or **Send selection** (note / flashcard / saved page,
  with tags). The multi-window JSON/ZIP export is still there for when Mei is closed.
- **Plugins** (Settings → **Plugins**) — drop a `plugin.json` manifest into your profile's
  `plugins\` folder to import (Todoist, TickTick CSV ship in the box) or export (notes,
  deck → CSV). Manifests declare fields; nothing executes code.
- **Your phone can read the desk** — after pairing, `GET /api/mobile/today` on the bridge
  answers with today's plate, what is due, what is left open, cards due and the loop's next
  step, so MeiRemote opens on today instead of an empty screen.

---

*Mei is its own application; shortcut tiles in Personal → Sites may link out
to separate web apps that Mei neither contains nor depends on.*
