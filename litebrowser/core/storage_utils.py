import json
import os
import secrets
import time
from typing import Any

from litebrowser.core.log import get_logger

_log = get_logger("storage_utils")
_JSON_ENCODER = json.JSONEncoder(ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False)


def safe_child_path(root: str, relative: str) -> str:
    """Resolve an untrusted child path without traversal or symlink escapes.

    Apply Windows restrictions on every platform so exchanged backups and
    bridge messages have the same interpretation on each device.
    """
    if not isinstance(relative, str) or not relative or "\x00" in relative or ":" in relative:
        return ""
    normalized = relative.replace("\\", "/")
    if normalized.startswith("/") or any(part in ("", ".", "..") for part in normalized.split("/")):
        return ""
    root_path = os.path.normcase(os.path.realpath(root))
    path = os.path.realpath(os.path.join(root_path, *normalized.split("/")))
    try:
        if os.path.commonpath([root_path, os.path.normcase(path)]) != root_path or os.path.normcase(path) == root_path:
            return ""
    except ValueError:
        return ""
    return path


def read_json(path: str, default: Any):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as exc:
            _log.warning("read_json failed for %s: %s", path, exc)
    return default


def _atomic_replace(tmp_path: str, final_path: str) -> None:
    """Replace a file atomically, tolerating short-lived Windows file locks.

    Antivirus scanners and Explorer previews can briefly hold a profile file
    open just as an atomic write is committed.  Retrying the final rename keeps
    the existing file intact while avoiding an unnecessary failed save.
    """
    for attempt in range(5):
        try:
            os.replace(tmp_path, final_path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))


def write_text_atomic(path: str, text: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    base_name = os.path.basename(path) or "file"
    fd, tmp_path = tempfile_mkstemp_same_dir(parent, base_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text or "")
            f.flush()
            os.fsync(f.fileno())
        _atomic_replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def tempfile_mkstemp_same_dir(parent: str, base_hint: str) -> tuple[int, str]:
    for _ in range(16):
        suffix = secrets.token_hex(4)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in base_hint)[:40] or "tmp"
        name = f".{safe}.{suffix}.tmp"
        candidate = os.path.join(parent, name)
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            return fd, candidate
        except FileExistsError:
            continue
    raise OSError("Could not create unique temp file")


def write_json(path: str, data: Any) -> None:
    # Encode before allocating a file descriptor: invalid payloads must not
    # leak handles or touch the previous on-disk value.
    serialized = _JSON_ENCODER.encode(data)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    base_name = os.path.basename(path) or "data.json"
    fd, tmp_path = tempfile_mkstemp_same_dir(parent or os.getcwd(), base_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        _atomic_replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
