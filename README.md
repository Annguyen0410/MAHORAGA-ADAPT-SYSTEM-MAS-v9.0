# Mei

[![CI](https://github.com/Annguyen0410/Mei/actions/workflows/ci.yml/badge.svg)](https://github.com/Annguyen0410/Mei/actions/workflows/ci.yml)

**Mei is a desktop browser and personal study workspace.** It brings web research,
notes, planning, flashcards, and AI assistance into one application, so information
can move from the page you are reading into the work you want to do next.

Mei is designed around a local profile and connected workflows: capture a source,
organize it in a research workspace, make a plan, study, and review. It runs on
QtWebEngine and supports the PyQt5 and PyQt6 compatibility paths.

## Highlights

- **Browser:** Chromium-based tabs, tab groups, split view, reader tools, downloads,
  incognito profiles, and optional web panels.
- **Research workspaces:** save regular tabs as a named desk and link existing notes,
  tasks, saved pages, and flashcards without duplicating those records.
- **Home and planning:** see current work, due items, unfinished tasks, and the next
  suggested step; plan courses, deadlines, and focus blocks in the Weekly Plan.
- **Personal workspace:** notes with wiki links, quick tasks, calendar, boards, saved
  pages, and SM-2 flashcard review.
- **Quick Capture:** create a note, task, saved page, or flashcard from a compact form
  and link it to the active research desk.
- **AI workspace:** use local retrieval, Ollama, llama.cpp, or OpenRouter. Browser and
  research context are opt-in settings; page content is treated as untrusted input,
  and private-page content is excluded.
- **Themes and accessibility:** multiple theme families and accents, customizable
  Home cards, and reduced-motion preferences.
- **Optional integrations:** folder sync, an Android bridge, and the Mei browser
  extension. These features are configured by the user and are not required to use
  the desktop app.
- **Credential protection:** on Windows, the AI provider key, Google token cache,
  sync token, bridge token, and proxy password are protected with the signed-in
  user's Windows credentials (DPAPI). They are excluded from backups, sync and
  diagnostics.

## Download

Download the Windows application and release notes from
[GitHub Releases](https://github.com/Annguyen0410/Mei/releases). Releases may include
`Mei.exe`, a `web_support` archive, and `update.json`. When a companion archive is
provided, extract it beside `Mei.exe` and keep the `web_support` directory in place.

Mei stores its profile separately from the executable, so replacing the application
does not replace the profile. Back up the profile folder before moving to another
device or troubleshooting storage issues.

## Run from source

The project is developed and tested with Python 3.11 on Windows. Create an
environment, install dependencies, and start the application:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe browser.py
```

For packaging instructions and platform-specific troubleshooting, see
[`RUN_AND_BUILD.md`](RUN_AND_BUILD.md).

## Privacy and data

Mei has no required account or hosted data service. Profile data is stored locally
on the device. Optional folder sync uses a location selected by the user.

AI providers can receive the context selected for a request. Ollama and llama.cpp
send requests to their configured endpoints; remote providers such as OpenRouter
send the selected request and context to that provider. The AI
workspace provides separate controls for browser and research context. Review those
controls before submitting sensitive material. A Mei passcode gates workspaces but
does not encrypt every profile file at rest.

Credentials (AI provider key, Google token cache, self-hosted sync token, mobile
bridge token, and proxy password) are kept in `secrets.dat` inside the profile. On
Windows they are protected with DPAPI for the current Windows user, so another
Windows account cannot read them; on other platforms Mei uses owner-only file
permissions and reports that the file is not encrypted. `secrets.dat` is deliberately
**not** included in profile backups, folder/self-hosted sync, or diagnostics bundles.
If protection fails, Mei keeps the previous value rather than silently signing you
out. Log files are credential-redacted before they are written, and the diagnostics
archive contains only versions, store shapes, and the redacted log tail.

The Android bridge defaults to loopback (this PC only). LAN mode uses plain HTTP;
Mei warns before enabling it, and rotating the bridge token disconnects every phone
or extension paired with the old token. Treat a pairing code as a credential.

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Command and shortcut reference](docs/COMMAND_REFERENCE.md)
- [Run and build guide](RUN_AND_BUILD.md)
- [Architecture](ARCHITECTURE.md)
- [Major update audit](docs/reports/MAJOR_UPDATE_AUDIT.md)
- [Changelog](docs/CHANGELOG.md)
- [Why Mei](docs/WHY_MEI.md)

## Development checks

Run the test suite and lint checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
.\.venv\Scripts\ruff.exe check --select F401,F811,F841,F821 litebrowser tests tools
```

GitHub Actions runs the test suite on Windows with both supported Qt bindings. The
release workflow also builds the frozen executable with PyInstaller, validates the
`web_support` archive, launches the packaged app against a throwaway data root with
`--smoke-test`, and requires the ready marker before publishing.

## Project layout

```text
browser.py                 Desktop entry point
litebrowser/core/           Product identity, preferences, storage, and shared logic
litebrowser/services/       Research, AI, planning, sync, and integration services
litebrowser/ui/             Browser shell and desktop workspaces
web_support/                Local web applications and supporting assets
Extensions/                 Mei browser extension
tests/                      Python regression suite
```

## Release process

The application version is defined in [`litebrowser/core/product.py`](litebrowser/core/product.py).
Release notes come from [`docs/CHANGELOG.md`](docs/CHANGELOG.md), and
[`tools/publish_release.py`](tools/publish_release.py) validates the tag and build
version before publishing the executable, companion assets, and update manifest.
Pushing a four-part version tag starts the Windows release workflow; a tag with a
suffix, such as `v1.0.0.0-alpha.1`, is published as a pre-release. The publisher
requires a SHA-256 and a plausible size for the executable, and the `web_support`
ZIP is re-read before upload to reject private files, traversal entries, or a
missing `hub/index.html` entry point. Earlier good files are preserved when either
check fails.
