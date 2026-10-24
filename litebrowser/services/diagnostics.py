"""One zip that makes a bug report actionable — and safe to hand over.

A report that says "it broke" cannot be debugged. A report that carries the log,
the exact versions of every moving part and the *shape* of the profile stores
usually can, and the person sending it should not have to decide which files are
private.

So the bundle is deliberately evidence, not data:

* **included** — the tail of ``mei.log``, Python/platform/app versions, and for
  each store in the profile its size, modification time, schema version and how
  many records it holds;
* **excluded by construction** — note text, task and event titles, planner
  contents, bookmarks and history entries, passwords, vault contents, AI index
  and sync token.

The only thing that can carry user text is the log tail itself (Mei logs page
titles and URLs at debug level), which ``README.txt`` inside the archive states
plainly, so the sender can read it before sharing.
"""
import json
import os
import platform
import sys
import time
import zipfile
from datetime import datetime

from litebrowser.core import app_paths, product, secret_store

# The newest log is the one that matters; older rotated files add size, not
# signal. 256 KB is several thousand lines.
LOG_TAIL_BYTES = 256 * 1024

# The PyQt6-WebEngine branch ships Chromium 122+; the PyQt5 fallback pins Qt
# 5.15, which is Chromium 87. Below this line the engine is old enough that
# sign-in and "are you a bot" flows start treating the browser as unsupported,
# and the number is worth showing rather than hiding in a bundle.
OLD_CHROMIUM_MAJOR = 120

README = """Mei diagnostics bundle

What this is
  Evidence for a bug report: versions, the shape of your profile stores, and the
  tail of the application log.

What it does NOT contain
  Note text, task/event titles, planner contents, bookmarks, browsing history,
  passwords, vault files, your AI index or your sync token. The inventory records
  sizes, schema versions and record counts only.

What to check before sharing
  logs/mei.log is the real log. Mei writes page titles and URLs there at debug
  level, so it can name the sites you had open. Read it (or trim it) if that
  matters to you.

Where to send it
  Attach it to an issue at https://github.com/Annguyen0410/Mei/issues
"""


def versions_payload(ui: dict | None = None) -> dict:
    """Version facts for the bundle; ``ui`` carries what only the GUI can know.

    Qt and Chromium can only be asked from inside the application (and the answer
    differs between PyQt5 and PyQt6), so the caller passes them in. Nothing here
    imports Qt: this module sits in ``services/``, which must stay importable
    without a display.
    """
    return {
        "app": {
            "name": product.APP_NAME,
            "version": product.APP_VERSION,
            "update_channel": product.UPDATE_METADATA_URL or "not configured",
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": os.path.basename(sys.executable or ""),
        },
        "machine": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "ui": dict(ui or {}),
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }


def engine_notice(ui: dict | None = None) -> str:
    """One line naming the engine, with a caution when it is the old branch.

    The caller passes what only the running GUI can know — ``binding``, ``qt``,
    ``chromium``, exactly as :func:`versions_payload` takes them — because this
    module has to stay importable without a display. Returns "" when the caller
    could not read any of it, so the page shows nothing rather than a guess.
    """
    facts = dict(ui or {})
    chromium = str(facts.get("chromium") or "").strip()
    qt = str(facts.get("qt") or "").strip()
    binding = str(facts.get("binding") or "").strip()
    if not (chromium or qt or binding):
        return ""
    parts = [part for part in (f"Qt {qt}" if qt else "", binding) if part]
    line = "Engine: Chromium " + (chromium or "unknown")
    if parts:
        line += " · " + " · ".join(parts)
    try:
        major = int(chromium.split(".")[0])
    except (TypeError, ValueError, IndexError):
        major = 0
    # PyQt5 has no qWebEngineChromiumVersion() to ask at all, so on that branch
    # the number is missing rather than low — and it is exactly the branch the
    # caution is for: Qt 5.15 is Chromium 87.
    old_branch = (major and major < OLD_CHROMIUM_MAJOR) or (not major and qt.startswith("5"))
    if old_branch:
        engine_version = chromium or "87.0.4280.144 (Qt 5.15)"
        line += (
            f"\nThis build runs the old engine branch (Chromium {engine_version}): "
            "some sites refuse it. Installing PyQt6-WebEngine moves Mei onto the new one."
        )
    return line


def _json_shape(raw) -> dict:
    """Record counts, never values. Schema, not content."""
    if not isinstance(raw, dict):
        return {"type": type(raw).__name__}
    shape = {"keys": len(raw)}
    try:
        shape["version"] = int(raw.get("version", 0) or 0)
    except (TypeError, ValueError):
        shape["version"] = 0
    collections = {}
    for key, value in raw.items():
        if isinstance(value, list):
            collections[key] = len(value)
        elif isinstance(value, dict):
            collections[key] = len(value)
    if collections:
        shape["counts"] = collections
    return shape


def _file_entry(path: str, name: str) -> dict:
    stat = os.stat(path)
    entry = {"name": name, "bytes": stat.st_size, "modified": int(stat.st_mtime)}
    if name.lower().endswith(".json"):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                entry.update(_json_shape(json.load(handle)))
        except (OSError, ValueError):
            entry["error"] = "unreadable json"
    return entry


def profile_inventory(base_dir: str) -> dict:
    """The profile's stores by shape: sizes, versions and record counts.

    Only the profile's own files are described — ``BrowserData`` (the Chromium
    profile, hundreds of MB) is reported as a total, never walked.
    """
    base_dir = os.path.abspath(base_dir or ".")
    stores = []
    try:
        names = sorted(os.listdir(base_dir))
    except OSError:
        names = []
    for name in names:
        path = os.path.join(base_dir, name)
        if name == secret_store.FILENAME:
            # Do not describe the credential store at all: its name and mtime are
            # not needed to debug Mei, and "not in the bundle" should be literal.
            continue
        if os.path.isfile(path):
            stores.append(_file_entry(path, name))

    folders = {}
    for name in names:
        path = os.path.join(base_dir, name)
        if not os.path.isdir(path):
            continue
        total = 0
        count = 0
        for root, _dirs, files in os.walk(path):
            for filename in files:
                try:
                    total += os.path.getsize(os.path.join(root, filename))
                    count += 1
                except OSError:
                    continue
        folders[name] = {"files": count, "bytes": total}

    return {
        "profile": os.path.basename(base_dir.rstrip("\\/")) or base_dir,
        "schema_version": int(app_paths.APP_SCHEMA_VERSION),
        "stores": stores,
        "folders": folders,
    }


def default_bundle_name(version: str = "") -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"mei-diagnostics-{version or product.APP_VERSION}-{stamp}.zip"


def _log_tail(log_dir: str, max_bytes: int) -> tuple[str, bytes]:
    """The newest log file, tail only."""
    path = os.path.join(log_dir, "mei.log")
    if not os.path.isfile(path):
        return "", b""
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        return "mei.log", handle.read()


def build_bundle(
    base_dir: str,
    out_path: str,
    *,
    app_dir: str = "",
    ui: dict | None = None,
    max_log_bytes: int = LOG_TAIL_BYTES,
) -> dict:
    """Write the diagnostics archive and describe what went into it."""
    log_dir = os.path.join(app_paths.data_root(app_dir or None), "logs")
    log_name, log_bytes = _log_tail(log_dir, max_log_bytes)
    payloads = {
        "README.txt": README.encode("utf-8"),
        "versions.json": json.dumps(versions_payload(ui), indent=2).encode("utf-8"),
        "inventory.json": json.dumps(profile_inventory(base_dir), indent=2).encode("utf-8"),
    }
    members = list(payloads)
    if log_bytes:
        payloads[os.path.join("logs", log_name)] = log_bytes
        members.append(f"logs/{log_name}")

    directory = os.path.dirname(os.path.abspath(out_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in payloads.items():
            bundle.writestr(name, data)

    return {
        "path": out_path,
        "bytes": os.path.getsize(out_path),
        "members": members,
        "log_bytes": len(log_bytes),
    }
