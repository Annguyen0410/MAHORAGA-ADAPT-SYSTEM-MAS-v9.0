# Mei Window Bridge (extension v1.2)

Load this folder as an **unpacked extension** in Chrome or Opera GX. It has two
jobs: send what you are looking at straight into Mei, and move a whole browser
workspace (all tabs, all monitors) over to Mei as a file.

## What it does

**Send straight to Mei** (Mei must be open, with its mobile bridge switched on)

- **Send this tab to Mei** — the tab you are on lands in Mei's saved pages.
- **Send selection** — the text you highlighted becomes, your choice of:
  a **note** (Clippings), a **flashcard** (front = page title), or a **saved
  page**. Tags from the box become deck tags (`#networking`) for cards and
  `# tag` lines for notes, matching how Mei writes them itself.
- Everything is one click, in the popup, on the page you are reading — no file,
  no import step, no losing your place.

**Take the whole workspace with you** (works even when Mei is closed, even on
another machine)

- **Capture This Window** — grab every tab in the current browser window.
- **Capture ALL Windows** — grab every tab in every browser window. Each window
  is treated as one monitor/screen, ordered left→right, so a dual-screen setup
  becomes `Screen 1` (e.g. 50 tabs) + `Screen 2` (e.g. 32 tabs).
- Exports as a **single JSON** (`workspace.json`) or a **ZIP** containing one
  JSON per screen. Tab titles/URLs keep full Unicode (Vietnamese, emoji, …).

## Install

1. Open `chrome://extensions` (or `opera://extensions`).
2. Enable **Developer mode**.
3. Click **Load unpacked** and select **this** folder (`Extensions\tab-window-bridge`).
4. Or extract `Extensions\MeiBridge-extension.zip` and load the extracted folder.

> ℹ️ Version 1.2 adds the `scripting` permission, which is only used to read the
> text you highlighted on the tab you are viewing when you press **Send
> selection**. Chrome re-asks for permissions when you reload an unpacked
> folder — reload the folder once and accept.

> ⚠️ **"Cannot load extension with file or directory name _legacy"** means
> you selected the **Mei repository root** rather than the extension folder.
> That folder contains `_legacy` (leading underscores are forbidden by the
> browser) and has no extension manifest. Select `Extensions\tab-window-bridge`,
> which contains `manifest.json`, instead.

## Pair with Mei (once)

1. In Mei: **Settings → Mobile bridge** → tick *Enable mobile bridge receiver*
   (port `18444` by default) → **Save mobile bridge settings**.
2. Click **Copy pairing code** — the code looks like
   `MEI1|192.168.1.7|18444|a1b2c3…` (the same code the QR shows for Mei Remote).
3. Paste it into the extension's **① Connect to Mei** box and press **Connect**.

The extension keeps only two things: the token, and whether it should talk to
`127.0.0.1`. The pairing code carries the LAN address so a phone can reach the
desktop; the extension runs on that same machine, so it rewrites the address to
`127.0.0.1` and never needs the bridge opened to the network.

If Mei is not running you get a sentence, not a mystery: *"Could not reach Mei at
http://127.0.0.1:18444 …"* — open Mei, Settings → Mobile bridge, and try again.

## Export flow (two screens → two Mei workspaces)

1. Click the extension icon, then **Capture ALL Windows**.
2. Click **Download ZIP all** (or **Download JSON all**).
3. In Mei, open the sidebar menu → **Extension Import Center**.
4. Click **Import File** and choose the `.zip` (or `.json`).
5. Click **Import All as Workspaces** — Screen 1 lands in Workspace 1,
   Screen 2 in Workspace 2, and extra screens get new workspaces.

You can also keep a single window: **Capture This Window → Copy JSON → Store
Payload → Import Selected Batch** imports it into the current workspace.

## Security (why it is safe to leave installed)

- Requests go to `POST/GET /api/mobile/ingest|ping` with
  `Authorization: Bearer <token>`; without the token the bridge answers 401.
- Mei only answers CORS to a **browser extension** origin
  (`chrome-extension://…`), so a web page cannot read bridge replies even if it
  learns the port. The token is what stops it doing anything; CORS is what stops
  it quietly trying.
- The token never leaves your machine (`chrome.storage.local`).
- If you regenerate the token in Mei, pair again — the old token stops working.

## Files

| File | Role |
| --- | --- |
| `manifest.json` | MV3 manifest, permissions: tabs / storage / downloads / scripting |
| `popup.html`, `popup.js` | the popup: pairing, send, capture, export |
| `bridge.js` | pure bridge helpers (pairing code, envelopes, reply wording); CommonJS-loadable, covered by `tests/js/bridge.test.js` |
| `zip.js` | dependency-free ZIP writer (STORE) used by the export flow |
