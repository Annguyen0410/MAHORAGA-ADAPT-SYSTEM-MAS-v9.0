"""Per-profile secrets, protected by the OS where the OS offers protection.

Mei kept its AI key, sync bearer token, Android bridge token, Google token cache
and proxy password in ordinary JSON (``prefs.json``, ``ai_settings.json``,
``proxy_config.json``). A desktop profile is a folder users copy, sync and zip
for support, so those values travelled further than intended.

This module is deliberately small:

* **Windows** — ``CryptProtectData`` (DPAPI, current-user scope). The key is
  managed by Windows; Mei never invents cryptography or ships a master key.
* **Other platforms** — no OS vault is guaranteed, so the same file is written
  with owner-only permissions (0600) and :func:`status` says plainly that it is
  not encrypted at rest.
* **No silent fallback on Windows** — if DPAPI fails, the write raises and the
  caller keeps the legacy value. A failed protection attempt must never quietly
  write a plaintext secret into a new place.
* **Non-destructive migration** — :func:`adopt` writes the protected value,
  reads it back, and only then calls the legacy-removal callback. If any step
  fails, the original value stays where it was and the reason is available in
  :func:`status`.

``secrets.dat`` is intentionally *not* part of folder sync, self-hosted sync,
backups or diagnostics. Each machine protects its own copy (DPAPI blobs are not
portable anyway); a restored profile asks the user to sign in again instead of
carrying credentials across machines.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import sys

from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked
from litebrowser.core.storage_utils import write_json

_log = get_logger("secret_store")

FILENAME = "secrets.dat"
STORE_VERSION = 1
MAX_SECRET_CHARS = 512 * 1024
#: A handful of credentials fit in a few KB. Anything larger is corruption or a
#: hostile file, and must not be loaded into memory or overwritten.
MAX_STORE_BYTES = 8 * 1024 * 1024

#: A key is an internal identifier, never user text. Keep it boring.
_ALLOWED_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")

_errors: dict[str, str] = {}

#: Values currently known to this process, so the log handler can mask them even
#: when they arrive inside an opaque provider message. Bounded: this is a
#: redaction aid, never a second copy of the store.
_known_values: list[str] = []
_KNOWN_LIMIT = 64


def _remember(value: str) -> None:
    text = str(value or "")
    if len(text) < 8:
        return
    try:
        _known_values.remove(text)
    except ValueError:
        pass
    _known_values.append(text)
    del _known_values[:-_KNOWN_LIMIT]


def known_secret_values() -> tuple[str, ...]:
    """Plaintext values this process has read, for log redaction only."""
    return tuple(_known_values)


class SecretStorageError(RuntimeError):
    """A secret could not be protected, read back, or stored safely."""


def path(base_dir: str) -> str:
    return os.path.join(base_dir, FILENAME)


def _backend() -> str:
    if sys.platform.startswith("win"):
        return "dpapi"
    return "file"


def backend_name() -> str:
    return _backend()


def _validate_key(key: str) -> str:
    text = str(key or "").strip()
    if not text or len(text) > 128 or any(char not in _ALLOWED_KEY_CHARS for char in text):
        raise SecretStorageError("Invalid secret name.")
    return text


def _validate_value(value: str) -> str:
    text = str(value or "")
    if len(text) > MAX_SECRET_CHARS:
        raise SecretStorageError("That value is too large to store as a secret.")
    return text


# --------------------------------------------------------------------------- #
# Windows DPAPI
# --------------------------------------------------------------------------- #
class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi_protect(data: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise SecretStorageError("DPAPI is only available on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _keep = _blob(data)
    out_blob = _DataBlob()
    # CRYPTPROTECT_UI_FORBIDDEN: never put a system prompt over the app.
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob), "Mei secret", None, None, None, 0x1, ctypes.byref(out_blob)
    ):
        raise SecretStorageError("Windows could not protect this secret.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise SecretStorageError("DPAPI is only available on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _keep = _blob(data)
    out_blob = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0x1, ctypes.byref(out_blob)
    ):
        raise SecretStorageError("Windows could not unlock this secret for this user.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _protect(data: bytes) -> str:
    if _backend() == "dpapi":
        return base64.b64encode(_dpapi_protect(data)).decode("ascii")
    return base64.b64encode(data).decode("ascii")


def _unprotect(value: str) -> bytes:
    raw = base64.b64decode(str(value or "").encode("ascii"), validate=True)
    if _backend() == "dpapi":
        return _dpapi_unprotect(raw)
    return raw


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
def _empty() -> dict:
    return {"version": STORE_VERSION, "backend": _backend(), "entries": {}}


def _load(base_dir: str) -> dict:
    file_path = path(base_dir)
    if not os.path.isfile(file_path):
        return _empty()
    try:
        if os.path.getsize(file_path) > MAX_STORE_BYTES:
            raise SecretStorageError("The secret store is too large to be valid.")
        with open(file_path, "r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
    except SecretStorageError:
        raise
    except (OSError, ValueError, UnicodeError) as exc:
        # Unlike an ordinary preference, a damaged secret file must not be
        # treated as empty: the next write would erase every still-recoverable
        # credential in it. Leave the bytes alone and report the failure.
        raise SecretStorageError("The secret store could not be read; the file was left untouched.") from exc
    if not isinstance(raw, dict):
        raise SecretStorageError("The secret store is not a JSON object.")
    try:
        version = int(raw.get("version", 0) or 0)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SecretStorageError("The secret store has an invalid version.") from exc
    if version > STORE_VERSION:
        raise SecretStorageError("This profile's secret store was written by a newer Mei.")
    if version < 1:
        raise SecretStorageError("The secret store has an invalid version.")
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        raise SecretStorageError("The secret store has no entry table.")
    clean: dict[str, dict] = {}
    for key, entry in entries.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        backend = str(entry.get("backend") or raw.get("backend") or "").strip()
        value = entry.get("value")
        if backend and isinstance(value, str):
            clean[key] = {"backend": backend, "value": value}
    return {"version": STORE_VERSION, "backend": _backend(), "entries": clean}


def _write(base_dir: str, data: dict) -> None:
    with profile_locked(base_dir):
        write_json(path(base_dir), data)
        try:
            os.chmod(path(base_dir), 0o600)
        except OSError:
            pass


def _record_error(base_dir: str, message: str) -> None:
    _errors[base_dir] = message
    _log.warning("secret store: %s", message)


def status(base_dir: str) -> dict:
    """Facts for Settings/diagnostics: backend, protection and failures.

    Never returns a secret value, not even a prefix. The ``entries`` list has
    names only so a support report can say *which* credential failed to load.
    """
    backend = _backend()
    info = {
        "backend": backend,
        "protected": backend == "dpapi",
        "location": os.path.basename(path(base_dir)),
        "entries": [],
        "error": _errors.get(base_dir, ""),
        "warning": "",
    }
    if backend != "dpapi":
        info["warning"] = (
            "This platform has no supported OS credential vault, so secrets use "
            "owner-only file permissions. They are not encrypted at rest."
        )
    try:
        info["entries"] = sorted(_load(base_dir)["entries"])
    except SecretStorageError as exc:
        info["error"] = str(exc)
        _errors[base_dir] = str(exc)
    return info


def get_secret(base_dir: str, key: str) -> str | None:
    """The stored value, or ``None`` when there is no readable entry.

    A decryption/corruption failure is recorded in :func:`status` and returns
    ``None`` — callers fall back to their legacy location rather than crashing
    the app or silently clearing a setting.
    """
    try:
        name = _validate_key(key)
        store = _load(base_dir)
        entry = store["entries"].get(name)
        if not entry:
            return None
        if entry.get("backend") != _backend():
            raise SecretStorageError(
                "This secret was protected by a different platform; it cannot be read here."
            )
        raw = _unprotect(entry["value"])
        value = raw.decode("utf-8")
        _remember(value)
        _errors.pop(base_dir, None)
        return value
    except (SecretStorageError, ValueError, UnicodeError, OSError) as exc:
        _record_error(base_dir, str(exc))
        return None


def set_secret(base_dir: str, key: str, value: str) -> None:
    """Protect and store a value; an empty value removes the entry."""
    name = _validate_key(key)
    text = _validate_value(value)
    store = _load(base_dir)
    if not text:
        store["entries"].pop(name, None)
        _write(base_dir, store)
        _errors.pop(base_dir, None)
        return
    protected = _protect(text.encode("utf-8"))
    # Read the fresh value back before acknowledging the write. This is the
    # difference between “we stored it” and “we hope we stored it”.
    if _unprotect(protected).decode("utf-8") != text:
        raise SecretStorageError("The protected secret did not read back correctly.")
    store["entries"][name] = {"backend": _backend(), "value": protected}
    _write(base_dir, store)
    _remember(text)
    _errors.pop(base_dir, None)


def delete_secret(base_dir: str, key: str) -> None:
    set_secret(base_dir, key, "")


def adopt(base_dir: str, key: str, legacy_value: str, clear_legacy) -> str:
    """Move a plaintext legacy value into the store without losing it.

    ``clear_legacy`` runs only after the protected value can be read back. When
    protection fails, the original value is returned unchanged and the caller
    must keep using it; :func:`status` carries the recovery message.
    """
    text = str(legacy_value or "")
    if not text:
        return ""
    try:
        set_secret(base_dir, key, text)
        if get_secret(base_dir, key) != text:
            raise SecretStorageError("The protected secret did not read back correctly.")
    except (SecretStorageError, ValueError, OSError) as exc:
        _record_error(
            base_dir,
            f"{key} could not be protected ({exc}). The existing value was kept in place.",
        )
        return text
    try:
        clear_legacy()
    except (OSError, ValueError, RuntimeError) as exc:
        # The protected copy exists; leaving the old copy is safer than raising
        # in the middle of a read. Status names the leftover so a later pass can
        # retry the cleanup.
        _record_error(base_dir, f"{key} was protected but its old plaintext copy could not be removed ({exc}).")
    return text


def recovery_hint(base_dir: str) -> str:
    """A user-facing sentence when the last secret operation failed."""
    error = _errors.get(base_dir, "")
    if not error:
        return ""
    return (
        "Mei could not protect a saved credential on this device. The previous value was "
        "kept so nothing is lost. Windows security (DPAPI) may be unavailable; check your "
        "user profile, then save the setting again. Details: " + error
    )


__all__ = [
    "FILENAME",
    "STORE_VERSION",
    "SecretStorageError",
    "adopt",
    "backend_name",
    "delete_secret",
    "get_secret",
    "known_secret_values",
    "path",
    "recovery_hint",
    "set_secret",
    "status",
]
