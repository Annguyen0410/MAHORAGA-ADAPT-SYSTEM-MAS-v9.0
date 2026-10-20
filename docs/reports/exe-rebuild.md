# Mei EXE rebuild and old-build cleanup

Date: 2026-09-30. Local build only; no upload, deployment, installation, commit or push.

## Delivered files

- [Mei.exe](../../dist/Mei.exe): **1.0.0.0**, 208,001,990 bytes (198.4 MiB).
- [Web bundle ZIP](../../dist/Mei-1.0.0.0-web_support.zip): 87 public assets; keep the extracted `web_support` folder beside the EXE.
- [Release metadata](../../dist/update.json) and [release notes](../../dist/RELEASE_BODY.md) regenerated locally only. Remote URLs in the metadata describe a potential release; nothing was uploaded.

EXE SHA-256:

```text
d87dd4275d8abec418983fa2403f4591cd5c8c6f08732f7ed7b69fef7e5f7d2d
```

## Verification

- Built with Python 3.11.9, PyInstaller 6.19.0, PyQt6 / Qt 6.11.2.
- Built into a separate staging directory; the old primary EXE was retained until the new build passed startup checks.
- Staged and final-location startup smoke passed: native Mei workspace window, live application process and **two QtWebEngine child processes** after 35 seconds.
- Smoke used disposable workspace data/TEMP/LOCALAPPDATA, synthetic preferences and a nonexistent local update channel. It did not open real profiles or use external keys. Only test-owned process descendants were stopped.
- QtWebEngine executable, platform plugin, ICU data and canonical manifest are present in the archive.
- Found and fixed a packaging omission: all four built-in CSV plugin manifests now ship in the EXE and match source bytes. Batch/spec/Python-package declarations are covered by a new regression test.
- Final regression: **864 Python tests and 749 subtests passed**; Ruff F/E9 passed.
- Final EXE and web ZIP hashes match metadata. ZIP entries and bytes match the 87 public files in the final bundle.
- Startup verification is not a full installer, hardware-GPU or packaged workflow certification.

## Removed old build artifacts

After successful final-location startup, removed the replaced EXE backup, 0.7.1.0 web ZIP, old intermediate `build/Mei` and fresh packaging scratch output. Removed the old Qt spike application binaries/distributions and PyInstaller work directories (`Mei611`, debug and p19 variants), preserving the spike's scripts, logs, environments and evidence.

Removed artifact bytes: **2,626,324,615**. Removed 87 superseded public web assets: **4,290,903** bytes. Total removed: **2,630,615,518 bytes (~2.45 GiB)**, excluding temporary smoke files.

The old web bundle also contained non-public files. These were moved intact to `build/preserved-web-data` rather than deleted; their contents were not read. This preserves private/backend configuration, personal legacy reports, and other non-public files while keeping them out of the new distributable.

API keys, real profiles, notes, browser data and original web sources were not modified or deleted. No old installed application outside the workspace was removed.
