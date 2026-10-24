# Mei major update — audit and delivery report

Scope: reliability, data integrity, update safety, credential handling, integration
clarity, and release verification for Mei 1.0.0.0. The product, profile formats,
Qt/PyQt compatibility paths, and architecture boundaries are unchanged.

Status labels: **fixed** = code and regression test are in this tree; **verified** =
the stated command ran in this environment; **not run** = needs Windows packaging,
a real phone/LAN, an installer, or a second Qt binding not installed here.

## 1. Baseline and method

- Read `README.md`, `ARCHITECTURE.md`, `docs/CAPABILITIES.md`, `docs/CHANGELOG.md`,
  the relevant services, and their existing tests before editing.
- Existing mechanisms were reused: atomic JSON writes, profile transaction/lock,
  the versioned store registry, `AppShell.run_in_background`, the existing theme and
  dialog components, and the release/publish tools.
- The working tree had no known failing tests at the start of the change set. The
  first complete run *after* the changes caught one old fixture that built a
  `web_support` bundle without the newly required `hub/index.html`; the fixture was
  corrected, not the check.
- Local environment: Windows, Python 3.11, PyQt6 6.11.0 (Chromium 140) through the
  PyQt5 compatibility shim; PyQt5 5.15.2 is also installed but is not the active
  binding. The CI matrix separately installs both bindings.

## 2. Confirmed bugs and data-integrity risks (fixed)

### 2.1 Page Monitor split URLs by hand — **high**

`litebrowser/services/page_monitor.py` normalized watch URLs with string splitting,
so a query-only URL such as `https://example.com?sort=1` could lose the boundary
between path and query, fragments were mishandled, and a bare host was not given a
stable canonical form.

**Fix:** `normalize_url` now uses `urllib.parse.urlsplit`/`urlunsplit`; it lowercases
scheme and host, keeps explicit non-default ports, preserves query and fragment,
rejects credentials in the URL, and accepts only `http`/`https`. The UI reports the
rejection instead of silently adding a broken watch (`ui/main_window/window.py`).

**Evidence:** `tests/test_page_monitor.py` (query-only, fragment, default/trailing
slash, explicit port, upper-case scheme/host, malformed scheme, credentials,
overlong URL, duplicate monitor).

### 2.2 One corrupt `monitors.json` row disabled every watch — **high**

A bad `last_checked`, a non-object row, or an unexpected field could raise while
loading the whole list. The monitor timer then failed for every page.

**Fix:** `load_monitors` validates row shape, ID syntax, URL, title length and
timestamp range, skips malformed rows, deduplicates URLs, clamps `last_checked` to a
sane range, and logs the skipped count. `save_monitors` caps the list at
`MAX_MONITORS` and writes through the atomic JSON helper.

**Evidence:** `tests/test_page_monitor.py` (corrupt rows, future/past timestamps,
duplicate URLs, list cap).

### 2.3 Page Monitor treated failure as "unchanged" and could hang the worker — **high**

The old timer fetched every due monitor sequentially on one worker, with no
response-size cap, no redirect policy, and no distinction between "fetch failed" and
"page unchanged".

**Fix:** `check_monitor` returns a structured result (`changed`, `unchanged`,
`failed`), records `last_error` without touching the stored hash on failure, bounds
the response to 2 MiB and the request to 15 s, follows only HTTP(S) redirects, and
refuses loopback/private targets unless the user explicitly added them. The shell
checks four due pages per tick and will not start a second batch while one is
running; a worker exception clears the guard.

**Evidence:** `tests/test_page_monitor.py` (timeout, oversized page, redirect,
HTTP error, failed-fetch hash preservation); `tests/test_page_monitor.py` covers
the batching helper's status contract.

### 2.4 Folder sync trusted the payload's `_hash` — **high**

A stale or tampered `_hash` could make a record look unchanged, so a real edit was
dropped or a hostile payload was accepted.

**Fix:** `sync_folder._remote_store` recomputes the canonical hash from validated
content and compares it with the claimed hash. Inconsistent records are rejected
with a named store/record warning; the preview reports them and does not apply.
Payload limits are enforced before merge: 48 MiB total, 20,000 records per store,
4 MiB per string, 32 nesting levels, 256 keys per object, 256-character IDs.

**Evidence:** `tests/test_sync_folder.py` (tampered hash, stale hash, duplicate IDs,
malformed rows, oversized payload, deep nesting, future schema version).

### 2.5 Folder sync could leave a partially applied profile — **high**

A multi-store apply that failed halfway had no single recovery route.

**Fix:** `sync()` snapshots the affected stores before writing, writes only stores
that differ, and on failure restores the snapshot and raises `SyncApplyError` naming
the store. The existing per-store `backups/sync-<time>/` copy is retained. The
preview remains read-only; `Settings → Folder sync` displays warnings and a failed
apply says the backup is retained.

**Evidence:** `tests/test_sync_folder.py` (injected write failure restores previous
rows; preview leaves files byte-identical; backup exists after apply).

### 2.6 Self-hosted sync merged notes by `(title, category)` — **high**

Notes were exported with IDs, but `_merge_notes` also used title/category as
identity. Renaming a note created a conflict copy; two different notes with the
same title/category could collapse into one.

**Fix:** current-format notes merge by stable ID. The ID is authoritative: a
remote title change does not create a duplicate or conflict copy, and two notes
that share a title/category but have different IDs stay separate. Legacy rows
without IDs keep a tested `(title, category)` fallback that only adds or preserves
text. Duplicate IDs and malformed rows are rejected before merge.
`personal_service.create_note_with_id` gives sync a stable-ID writer.

**Evidence:** `tests/test_sync_service_safety.py` (rename, duplicate title, legacy
rows, conflicting edits, deletion/edit conflict, malformed bundle, size/depth caps).

### 2.7 Updater version policy was ambiguous — **high**

`_normalize_version` turned non-numeric chunks into zero, so `0.6.8.0-beta` compared
equal to `0.6.8.0`, and the manifest accepted shapes the installer could not use.

**Fix:** `parse_version` accepts exactly four numeric components (1–9 digits each)
and rejects suffixes. The channel manifest must carry that shape; a pre-release tag
is handled by `publish_release` (GitHub pre-release), never by a fake numeric
version. `_version_is_newer` compares the parsed tuple and refuses downgrades.

**Evidence:** `tests/test_version_scheme.py`, `tests/test_update_identity.py`,
`tests/test_publish_release.py`.

### 2.8 Update packages were not fully identity-checked — **high**

The download path could accept a wrong asset name, an absent/incorrect hash, a
declared size that did not match, a truncated file, or an HTML error page.

**Fix:** remote updates require `product == "mei"`, the exact `Mei.exe` asset name,
a 64-hex SHA-256, a positive declared size, and a size within
`MIN_PACKAGE_BYTES..MAX_PACKAGE_BYTES` (1 MB–512 MB). The downloaded file is checked
for declared size, actual size, `MZ` header, and final SHA-256 before installation;
partial files are deleted on failure. Local/manual channel packages keep an explicit,
narrow exception and still get the `MZ`/size check.

**Evidence:** `tests/test_update_identity.py` (missing/wrong hash, size mismatch,
truncated download, partial cleanup, malformed manifest, wrong product, wrong
asset).

### 2.9 Self-replacement interpolated paths into a `.cmd` — **high**

Spaces, quotes, `%`, `&`, `!`, Unicode and apostrophes in the install path could
break the replacement script or execute unintended text.

**Fix:** `_update_script_text` emits a PowerShell script with all paths passed as
single-quoted literals through `_ps_quote` (doubling apostrophes); no path is
interpolated into a batch line. The script waits for the old process, copies the
backup, replaces the executable, starts it with a health marker, and restores the
backup if the new process does not report healthy.

**Evidence:** `tests/test_update_identity.py` (apostrophe/space/percent/ampersand/
Unicode paths; backup restore path; health marker; no `.cmd` interpolation).

### 2.10 Update UI could show a token-bearing URL — **medium**

The "update available" dialog printed the raw download URL.

**Fix:** `update_service.redact_url` removes user-info, sensitive query parameters
(`token`, `secret`, `signature`, `key`, `password`, `auth`) and fragments before the
URL is shown. Download/verify/install states are now distinct strings, and hashing
and network work stay on the background executor.

**Evidence:** `tests/test_update_identity.py` (`redact_url` cases).

## 3. Security and privacy (fixed)

### 3.1 Credentials were ordinary JSON — **critical**

The OpenRouter key, Google token cache, self-hosted sync token, Android bridge token
and proxy password lived in `prefs.json`, `ai_settings.json` and
`proxy_config.json`. Those files are copied into backups, sync folders and support
archives.

**Fix:** `litebrowser/core/secret_store.py` stores them in `secrets.dat`.

- Windows: `CryptProtectData` (DPAPI, current-user scope). No custom crypto and no
  master key in the repository.
- Other platforms: owner-only (0600) file, and `status()` says it is not encrypted.
- `adopt()` protects, reads back, and only then removes the legacy plaintext. On
  failure the old value stays and `recovery_hint()` explains what happened.
- `prefs.py` routes all five credential families through the store. A failed write
  raises, so the UI keeps the previous setting and shows a recovery message.
- `secrets.dat` is excluded from profile backups, folder sync, self-hosted sync and
  diagnostics. Google sign-out deletes the protected entry.

**Evidence:** `tests/test_secret_store.py` (round-trip, idempotent adopt, failed
protection keeps the legacy value, corrupt store recovery, backup exclusion,
non-Windows permission fallback); `tests/test_android_bridge.py` (token through the
store); `tests/test_diagnostics.py`.

### 3.2 Logs and diagnostics could carry credentials — **high**

Provider errors and redirect URLs routinely include bearer tokens. The diagnostics
bundle includes the log tail.

**Fix:** the file handler now installs `log._RedactionFilter`, which masks known
secret values and recognisable credential shapes (`Bearer …`, `api_key=…`,
`token: …`, `password=…`, `https://user:pass@…`, `sk-…`, `ghp_…`, `ya29.…`) before
bytes are written. The diagnostics README and tests state that the log can still
name visited pages.

**Evidence:** `tests/test_diagnostics.py::TestLogRedaction` (handler-level masking,
known-value masking, archive scan finds no canary).

### 3.3 LAN bridge mode was under-explained — **high**

The bridge defaults to loopback, but the LAN switch enabled plain HTTP without a
clear warning, and rotating the token did not explain that paired devices would be
disconnected.

**Fix:** Settings explains loopback vs LAN, requires an explicit confirmation before
enabling LAN (plain HTTP, token capture risk), labels the pairing code as a
credential, confirms token replacement, and restarts the listener only after the
protected token write succeeds. The service still uses constant-time comparison,
rate limits, bounded workers, body limits, safe paths, private-network checks and
origin allowlisting; redirects remain blocked so the bearer token cannot be
forwarded.

**Evidence:** `tests/test_android_bridge.py` (unauthorized call, cleared token,
rotation rejects the old token and accepts the new one, oversized body, traversal,
CORS preflight, rate limit); `tests/test_extension_bridge_js.py`.

### 3.4 Backup/export redaction — **medium**

`export_profile_payload` now removes the sync token, bridge token, Google cache,
passcode verifier and provider key, strips the last-VPN password, and records the
removed field names in `redacted_fields`. Restore does not erase a current passcode
when the backup redacted it.

**Evidence:** `tests/test_secret_store.py` (redaction list); `tests/test_backup_export.py`
(round-trip and legacy payloads).

## 4. Performance and stability (fixed)

- **Page Monitor:** bounded response/time, four-page batch per tick, no overlapping
  worker runs, one failed page no longer blocks the others.
- **Sync:** size/depth/record caps are checked before merge; preview is read-only;
  only changed stores are written; a failed multi-store apply restores a snapshot.
- **Update:** download and hashing stay off the GUI thread; partial files are
  removed; the UI shows checking → available → downloading with a bounded
  percentage/byte count → verifying → installing → success/rollback instead of a
  single ambiguous string. Progress is reported about 20 times per package, not
  once per network chunk.
- **Background callbacks:** worker exceptions are logged and clear the guard, so a
  crash cannot permanently stop monitor checks.
- **Startup:** no new always-on timers or caches were added. `--smoke-test` writes
  its marker after both shells are shown and quits on a 400 ms timer.

Measurements: not claimed beyond the observed source smoke start (2.66 s to
"Mei ready" on this machine) and the test-suite duration. No large-profile benchmark
was run, so no speedup is claimed.

## 5. Release, CI, and product polish (fixed)

- **Version integrity:** existing `tests/test_version_consistency.py` already gates
  `core/product.py`, `pyproject.toml`, `installer.iss` and the changelog section.
  No duplicate version source was added.
- **Release workflow:** top-level `permissions: contents: read`, with `contents:
  write` only on the publish job; `actions/checkout` and `actions/setup-python` are
  pinned to their v5/v6 commits; the packaged executable hash is written to the job
  summary.
- **Packaged smoke test:** after PyInstaller, the workflow launches `dist/Mei.exe
  --smoke-test` with `LITEBROWSER_DATA_DIR` pointing at a temporary folder and
  `MEI_SMOKE_MARKER` set. It requires a clean exit within 120 s and the marker
  written after both shells are shown.
- **Dependency scanning:** `.github/dependabot.yml` opens weekly grouped PRs for
  pip and GitHub Actions. They are reviewable PRs, not part of the release gate.
- **`web_support` validation:** `publish_release.verify_web_support_zip` re-reads the
  finished archive, rejects private folders/files, absolute or traversal entries, and
  a missing `hub/index.html`. Validation happens on the temporary file before
  `os.replace`, so a failed check keeps the previous good ZIP.
- **UX:** Page Monitor failures are visible in the watch tooltip and via a status
  message; folder-sync warnings appear in the preview; sync endpoint validation
  refuses unsupported schemes and warns before saving a non-loopback HTTP endpoint;
  secret-storage failures are reported in Settings, AI settings, Google sign-out,
  sync and bridge pages instead of being swallowed.

## 6. Regression coverage added or updated

- `tests/test_page_monitor.py` — URL parsing, corrupt rows, bounds, failed checks.
- `tests/test_sync_folder.py` — tampered/stale hashes, limits, rollback, preview
  immutability, backups, duplicate IDs.
- `tests/test_sync_service_safety.py` — stable note IDs, renames, duplicate titles,
  delete/edit conflicts, malformed/oversized bundles, legacy fallback.
- `tests/test_version_scheme.py` — four-part parsing, prerelease rejection.
- `tests/test_update_identity.py` — manifest identity, hash/size/MZ checks,
  download cleanup, path-safe PowerShell, health/rollback.
- `tests/test_secret_store.py` — DPAPI/file round-trip, non-destructive adoption,
  corrupt-store recovery, backup redaction.
- `tests/test_diagnostics.py` — log redaction and no-canary archive scan.
- `tests/test_android_bridge.py` — token rotation invalidates the old token.
- `tests/test_release_artifacts.py` — only public assets, required Hub entry point,
  failed validation preserves the previous ZIP.
- `tests/test_publish_release.py` — updated fixture for the required entry point.

## 7. Verification (commands and results)

Run from `new browser/`:

```powershell
QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe -m pytest -p no:cacheprovider --no-header -q
.venv\Scripts\ruff.exe check --select F401,F811,F841,F821 litebrowser tests tools
```

- Full suite: **995 passed, 1,324 subtests passed** (106.35 s on the final run; the
  first post-change run took 105.70 s). The first full run
  after the change set was **993 passed, 1 failed**; the one failure was an old
  `web_support` fixture missing `hub/index.html`, not a product regression. The
  fixture was fixed and the complete suite re-ran green.
- Ruff: **All checks passed** (`F401,F811,F841,F821` over `litebrowser tests tools`).
  One unused local in `tests/test_sync_folder.py` was removed before the final run.
- Source startup smoke: `python -m litebrowser.main --smoke-test` with a temporary
  `LITEBROWSER_DATA_DIR` exited 0 and wrote `ok 1.0.0.0` after showing both shells
  (2.03 s on the final run; 2.66 s on the first).
- Qt bindings: PyQt6 6.11.0 (Chromium 140) ran here; PyQt5 5.15.2 is covered by the
  CI matrix but was **not the active local binding** in this environment.
- Packaged executable: built with PyQt6 6.11.0, 208,101,945 bytes, SHA-256
  `cab07bb9d5964b769c4824544fc6b14ebb8e12792a0bb9e76b8ee70ee9ad8b46`; the packaged
  `--smoke-test` exited 0 and wrote `ok 1.0.0.0`. The installer compile/install,
  real phone/LAN pairing, and the actual self-replacement flow were **not run**
  here. They are covered by automated tests at the service/script level and by the
  release workflow; a real Windows install/update and a physical phone remain
  manual checks.

## 8. Deferred or still manual

- **Real Windows upgrade:** run a published build, let it download a newer package,
  confirm the PowerShell helper replaces the exe, the new process writes the health
  marker, and the `.bak` is removed. Then force a failure (kill the new process) and
  confirm the backup is restored. The script and health logic are unit-tested; the
  end-to-end desktop flow needs a disposable VM.
- **Installer:** `installer.iss` still duplicates `MyAppVersion`; the consistency
  test fails on drift, but an actual `ISCC.exe` compile and install/uninstall test
  was not run.
- **Android/LAN:** pairing, token rotation and CORS are tested against loopback HTTP;
  a phone on a real Wi-Fi network and a browser extension in Chrome/Opera GX were not
  exercised here.
- **DPAPI cross-account:** tests verify round-trip and failure handling, but not a
  second Windows user trying to read the file.
- **Full-profile encryption:** deliberately not implemented. The passcode remains a
  workspace gate; documentation says so.
- **Performance budgets:** no representative large-profile benchmark was added, so
  no performance numbers are claimed beyond the bounded-work changes above.

## 9. Files changed

Core and services: `litebrowser/core/log.py`, `litebrowser/core/prefs.py`,
`litebrowser/core/secret_store.py` (new), `litebrowser/main.py`,
`litebrowser/services/page_monitor.py`, `history_service.py`,
`personal_service.py`, `sync_folder.py`, `sync_service.py`,
`update_service.py`.

UI: `litebrowser/ui/app_shell.py`, `ai_window.py`,
`main_window/window.py`, `shell/pages.py`.

Release/tooling: `.github/workflows/ci.yml`, `.github/workflows/release.yml`,
`.github/dependabot.yml`, `tools/publish_release.py`, `tools/sync_web_support.py`.

Docs: `README.md`, `ARCHITECTURE.md`, `docs/CAPABILITIES.md`,
`docs/CHANGELOG.md`, `docs/USER_GUIDE.md`, this report.

Tests: the files listed in §6.

No profile, secret, browser database, log, or generated build artefact is part of
the change set.
