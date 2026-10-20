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

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Command and shortcut reference](docs/COMMAND_REFERENCE.md)
- [Run and build guide](RUN_AND_BUILD.md)
- [Architecture](ARCHITECTURE.md)
- [Changelog](docs/CHANGELOG.md)
- [Why Mei](docs/WHY_MEI.md)

## Development checks

Run the test suite and lint checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
.\.venv\Scripts\ruff.exe check --select F401,F811,F841,F821 litebrowser tests tools
```

GitHub Actions runs the test suite on Windows with both supported Qt bindings.

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
