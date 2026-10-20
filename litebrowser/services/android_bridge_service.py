"""Local HTTP receiver for LitebrowserRemote (Android). stdlib only."""
from __future__ import annotations

import base64
import email
import hmac
import ipaddress
import json
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from email import policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from litebrowser.core import app_paths, app_version, prefs
from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked, profile_transaction
from litebrowser.core.storage_utils import safe_child_path, write_json
from urllib.parse import unquote

_log = get_logger("android_bridge")
from litebrowser.services import (
    desk_service,
    extension_bridge,
    flashcard_service,
    history_service,
    life_service,
    open_request,
    personal_service,
)

# Contract version advertised to the phone app. Bump it when an action's payload
# or result shape changes so a future client can negotiate instead of guessing.
API_VERSION = 1

SUPPORTED_ACTIONS = (
    "create_note",
    "append_to_library",
    "create_task",
    "import_tabs_batch",
    "upload_file_reference",
    "save_page",
    "save_selection",
    "create_drawing",
    "open_app",
)

#: Origins allowed to read a bridge response. A browser extension runs on the
#: machine it is installed on, so letting *it* talk to the bridge is what turns
#: "export a file and import it by hand" into "send this tab to Mei". A web page
#: is never in this list: the token already stops one from doing anything, and
#: CORS is what stops it from quietly trying.
EXTENSION_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")

#: Anything here means the Origin is not a plain scheme://host and gets dropped.
_ORIGIN_JUNK_RE = re.compile(r"[\s,;\\]")


def _extension_origin(value: str | None) -> str:
    """
    The request's Origin when it is a browser extension, else an empty string.

    The value is rebuilt from the scheme and host only, so nothing a client sends
    (a path, a query, a stray space, an opaque "null") is ever echoed back.
    """
    origin = (value or "").strip()
    if not origin or _ORIGIN_JUNK_RE.search(origin):
        return ""
    for prefix in EXTENSION_ORIGIN_PREFIXES:
        if origin.startswith(prefix):
            bare = origin[len(prefix) :].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip()
            return prefix + bare if bare else ""
    return ""

# Chain app ids resolvable over the bridge: MeiRemote can say "open MAS" and
# the desktop resolves the deployed URL from chain.json (single source of truth).
_CHAIN_APP_IDS = ("linklumina", "cucquanly", "mas", "worldleaderboard", "bimat", "boitoan", "hub")
MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_FIELD_CHARS = 200_000
MAX_IMAGE_B64_CHARS = 9 * 1024 * 1024  # base64 chars (~6.7 MB decoded PNG)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REQUESTS_PER_MINUTE = 120
MAX_AUTH_FAILURES_PER_MINUTE = 8

# Windows-forbidden filename characters only; keep Unicode (e.g. Vietnamese) intact.
_WIN_FORBIDDEN_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_LONG_FIELD_KEYS = {"image_base64"}

_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None
_rate_lock = threading.Lock()
_requests: dict[str, deque[float]] = defaultdict(deque)
_auth_failures: dict[str, deque[float]] = defaultdict(deque)


class BridgeHTTPServer(ThreadingHTTPServer):
    """Holds profile_dir for handlers (read prefs per request)."""

    profile_dir: str
    allow_reuse_address = True
    # Per-request socket timeout: a client that opens a connection and then
    # dribbles bytes (slowloris) used to pin a thread forever — one thread per
    # request with no timeout meant unbounded thread accumulation (v6.4).
    timeout = 30
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, profile_dir: str, server_address, RequestHandlerClass):
        self.profile_dir = profile_dir
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(server_address, RequestHandlerClass)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.timeout)
        return connection, address

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


PAIRING_PREFIX = "MEI1"
PAIRING_MAX_TOKEN_CHARS = 512
#: A host that carries any of these cannot be rebuilt into a URL, so it is not a
#: host. Shared, character for character, with the extension's parser.
PAIRING_HOST_JUNK_RE = re.compile(r"[\s/\\|,?#@%]")


def _utc_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pairing_code(profile_dir: str, lan_ip: str = "") -> str:
    """Compact one-line code the Android app can paste or scan to connect.

    Format: ``MEI1|<host>|<port>|<token>``. Uses the LAN IPv4 so a phone on the
    same Wi-Fi can reach the desktop without typing anything.
    """
    host = (lan_ip or "").strip()
    if not host:
        host = prefs.get_mobile_bridge_host(profile_dir)
    if host in ("0.0.0.0", "127.0.0.1", "", "::"):
        host = lan_ip or "127.0.0.1"
    port = prefs.get_mobile_bridge_port(profile_dir)
    token = prefs.ensure_mobile_bridge_token(profile_dir)
    return f"{PAIRING_PREFIX}|{host}|{port}|{token}"


def pairing_qr_png(code: str, scale: int = 6) -> bytes:
    """Render a pairing code as PNG bytes (segno, pure Python)."""
    import io

    import segno

    qr = segno.make(code, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, dark="#2e271f", light="#fffdf8")
    return buf.getvalue()


def parse_pairing_code(code: str) -> dict[str, str] | None:
    """
    Parse a pairing code into host/port/token; None when malformed.

    The rules are shared with the browser extension's copy of this parser
    (``Extensions/tab-window-bridge/bridge.js``): four parts, the MEI1 prefix, a
    digit port inside the real TCP range, and a non-empty host and token. A code
    that survives here is a code that survives there.
    """
    if not isinstance(code, str):
        return None
    parts = code.strip().split("|")
    if len(parts) != 4 or parts[0] != PAIRING_PREFIX:
        return None
    host, port, token = parts[1].strip(), parts[2].strip(), parts[3].strip()
    if not host or len(host) > 253 or PAIRING_HOST_JUNK_RE.search(host):
        return None
    if ":" in host:
        if not re.fullmatch(r"(?:[0-9A-Fa-f]*:){2,}[0-9A-Fa-f.]*", host.strip("[]")):
            return None
    elif not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        return None
    if not re.fullmatch(r"[0-9]{1,5}", port) or not (1 <= int(port) <= 65535):
        return None
    if not token or len(token) > PAIRING_MAX_TOKEN_CHARS or re.search(r"[\r\n\x00]", token):
        return None
    return {"host": host, "port": port, "token": token}


def _json_error(code: str, message: str, details: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    else:
        err["details"] = None
    return {"ok": False, "error": err}


def _parse_bearer(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    parts = auth_header.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _auth_ok(profile_dir: str, auth_header: str | None) -> bool:
    expected = prefs.get_mobile_bridge_token(profile_dir)
    got = _parse_bearer(auth_header)
    if not expected or not got:
        return False
    try:
        return hmac.compare_digest(got.encode("utf-8"), expected.encode("utf-8"))
    except (TypeError, UnicodeEncodeError) as exc:
        _log.warning("mobile bridge auth check failed: %s", exc)
        return False


def _permit(bucket: dict[str, deque[float]], address: str, limit: int) -> bool:
    now = time.monotonic()
    with _rate_lock:
        if len(bucket) > 512:
            for key in list(bucket):
                if not bucket[key] or now - bucket[key][-1] >= 60:
                    del bucket[key]
        window = bucket[address]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True


def _client_allowed(profile_dir: str, address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if prefs.get_mobile_bridge_host(profile_dir) == prefs.MOBILE_BRIDGE_DEFAULT_HOST:
        return ip.is_loopback
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _payload_is_safe(value: Any, key: str = "", depth: int = 0) -> bool:
    """Bound nesting, field size, and numeric values before touching any store."""
    if depth > 20:
        return False
    if isinstance(value, str):
        limit = MAX_IMAGE_B64_CHARS if key in _LONG_FIELD_KEYS else MAX_FIELD_CHARS
        return len(value) <= limit
    if isinstance(value, dict):
        return len(value) <= 128 and all(
            isinstance(k, str) and len(k) <= 128 and _payload_is_safe(item, k, depth + 1) for k, item in value.items()
        )
    if isinstance(value, list):
        return len(value) <= 256 and all(_payload_is_safe(item, depth=depth + 1) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (bool, int))


def _tags_suffix(tags: Any) -> str:
    if not isinstance(tags, list) or not tags:
        return ""
    parts = [str(t).strip() for t in tags if str(t).strip()]
    if not parts:
        return ""
    return "\n\n" + "\n".join(f"# {p}" for p in parts)


def _card_tags(tags: Any) -> str:
    """Card bodies follow the deck convention: Anki tags carry no spaces (#tag)."""
    if not isinstance(tags, list) or not tags:
        return ""
    parts = [str(t).strip().lstrip("#").replace(" ", "-") for t in tags if str(t).strip()]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return "\n\n" + " ".join(f"#{p}" for p in parts)


def _safe_vault_target_dir(base_dir: str, relative_target: str) -> str | None:
    """Resolve relative_target under SafeVault; reject traversal."""
    rel = (relative_target or "").strip().replace("\\", "/").strip("/")
    if not rel:
        return None
    segments = [p for p in rel.split("/") if p and p != "."]
    if ".." in segments:
        return None
    return safe_child_path(base_dir, "SafeVault/" + "/".join(segments)) or None


def _safe_vault_filename(name: str) -> str:
    """Sanitize a filename for disk while preserving Unicode (Vietnamese, etc.)."""
    raw = (name or "").strip()
    raw = _WIN_FORBIDDEN_NAME_RE.sub("-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip(" .") or "upload"
    if len(raw) > 160:
        stem, dot, ext = raw.rpartition(".")
        if dot and len(ext) <= 20:
            raw = (stem[:120].rstrip(" .") or "upload") + dot + ext
        else:
            raw = raw[:120].rstrip(" .") or "upload"
    if raw.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raw = "_" + raw
    return raw


def _upload_dir(base_dir: str, relative_target: str) -> str | None:
    """Resolve an upload target under SafeVault/files; reject traversal."""
    files_root = safe_child_path(base_dir, "SafeVault/files")
    if not files_root:
        return None
    rel = (relative_target or "").strip().replace("\\", "/").strip("/")
    if not rel:
        rel = "Inbox"
    segments = [p for p in rel.split("/") if p and p != "."]
    if ".." in segments:
        return None
    return safe_child_path(files_root, "/".join(segments)) or None


def _unique_path(directory: str, name: str) -> str:
    """Return directory/name, deduping with a numeric suffix when it exists."""
    path = os.path.join(directory, name)
    if not os.path.exists(path):
        return path
    stem, dot, ext = name.rpartition(".")
    base = stem or name
    suffix = 2
    while True:
        candidate = f"{base}-{suffix}{dot + ext if dot else ''}"
        path = os.path.join(directory, candidate)
        if not os.path.exists(path):
            return path
        suffix += 1


@profile_transaction
def dispatch_ingest(profile_dir: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """
    Run one ingest envelope; returns Android-shaped body (HTTP 200 with ok true/false).
    """
    received = _utc_iso_z()
    if not isinstance(envelope, dict) or not _payload_is_safe(envelope):
        return {"ok": False, "action": None, "received_at": received, "result": None, "error": _json_error("invalid_payload", "Payload exceeds bridge limits")["error"]}
    action = envelope.get("action")
    if not isinstance(action, str) or not action.strip():
        return {
            "ok": False,
            "action": None,
            "received_at": received,
            "result": None,
            "error": _json_error("invalid_payload", "Missing or invalid action")["error"],
        }
    action = action.strip()
    payload = envelope.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return {
            "ok": False,
            "action": action,
            "received_at": received,
            "result": None,
            "error": _json_error("invalid_payload", "payload must be a JSON object")["error"],
        }
    p = payload if isinstance(payload, dict) else {}

    try:
        text_fields = ("title", "url", "category", "bucket", "filename", "mime_type", "relative_target", "as", "front", "label", "id", "summary")
        if any(key in p and p[key] is not None and not isinstance(p[key], str) for key in text_fields):
            raise ValueError("Text fields must be strings")
        if action == "create_note":
            category = (p.get("category") or "").strip()
            title = (p.get("title") or "").strip()
            body = p.get("body")
            body = body if isinstance(body, str) else ("" if body is None else str(body))
            if not category or not title:
                raise ValueError("create_note requires category and title")
            body = body + _tags_suffix(p.get("tags"))
            note = personal_service.create_note(profile_dir, title, body, category)
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"note_id": note.get("id"), "category": note.get("category")},
                "error": None,
            }

        if action == "append_to_library":
            kind = (p.get("kind") or "").strip()
            title = (p.get("title") or "").strip() or "Capture"
            body = p.get("body")
            body_s = body if isinstance(body, str) else ("" if body is None else str(body))
            source_url = (p.get("source_url") or "").strip()
            tags_line = _tags_suffix(p.get("tags"))
            summary = (body_s + tags_line).strip()
            if kind and kind != "external_capture":
                raise ValueError("append_to_library expects kind external_capture")
            if source_url:
                page = life_service.add_saved_page(profile_dir, title, source_url, summary=summary)
                return {
                    "ok": True,
                    "action": action,
                    "received_at": received,
                    "result": {"saved_page_id": page.get("id"), "url": page.get("url")},
                    "error": None,
                }
            body_full = body_s
            if tags_line:
                body_full = (body_full + tags_line).strip()
            note = personal_service.create_note(profile_dir, title, body_full, "Mobile/Captures")
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"note_id": note.get("id"), "category": note.get("category")},
                "error": None,
            }

        if action == "create_task":
            title = (p.get("title") or "").strip()
            if not title:
                raise ValueError("create_task requires title")
            raw_bucket = p.get("bucket")
            if raw_bucket is None or (isinstance(raw_bucket, str) and not raw_bucket.strip()):
                bucket = "Inbox"
            else:
                bucket = str(raw_bucket).strip()
            due_raw = p.get("due_at")
            notes = p.get("notes")
            notes_s = None if notes is None else (str(notes) if not isinstance(notes, str) else notes)
            task = life_service.add_task(profile_dir, title, bucket=bucket, due_at=due_raw, notes=notes_s)
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"task_id": task.get("id"), "bucket": task.get("bucket")},
                "error": None,
            }

        if action == "import_tabs_batch":
            batch = {
                "source_browser": (p.get("source_browser") or "android_remote").strip() or "android_remote",
                "source_label": (p.get("source_label") or "").strip() or "Android",
                "window_id": p.get("window_id"),
                "tabs": p.get("tabs"),
            }
            if batch["window_id"] is not None:
                batch["window_id"] = str(batch["window_id"]).strip() or None
            tabs = batch["tabs"]
            if not isinstance(tabs, list) or not tabs:
                raise ValueError("import_tabs_batch requires non-empty tabs array")
            out = extension_bridge.upsert_batch(profile_dir, batch)
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"batch_id": out.get("id"), "tab_count": out.get("tab_count")},
                "error": None,
            }

        if action == "upload_file_reference":
            filename = (p.get("filename") or "").strip()
            mime = (p.get("mime_type") or p.get("mimeType") or "").strip()
            rel_target = (p.get("relative_target") or "").strip()
            caption = p.get("caption")
            cap_s = "" if caption is None else str(caption)
            if not filename or not mime or not rel_target:
                raise ValueError("upload_file_reference requires filename, mime_type, relative_target")
            target_dir = _safe_vault_target_dir(profile_dir, rel_target)
            if not target_dir:
                raise ValueError("Invalid relative_target")
            os.makedirs(target_dir, exist_ok=True)
            base = re.sub(r"[^a-zA-Z0-9._-]+", "-", filename).strip("-._") or "upload"
            stub_name = f"{base}.pending-mobile-upload.txt"
            path = os.path.join(target_dir, stub_name)
            suffix = 1
            while os.path.exists(path):
                stub_name = f"{base}-{suffix}.pending-mobile-upload.txt"
                path = os.path.join(target_dir, stub_name)
                suffix += 1
            meta = {
                "filename": filename,
                "mime_type": mime,
                "relative_target": rel_target,
                "transport": p.get("transport") or "multipart",
                "caption": cap_s,
                "stub": "metadata_only_no_binary",
            }
            write_json(path, meta)
            history_service.log_event(
                profile_dir,
                "mobile-upload",
                filename,
                "File reference recorded (metadata only)",
                {"path": path, "mime_type": mime},
            )
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"stub_path": path, "note": "metadata_only"},
                "error": None,
            }

        if action == "create_drawing":
            title = (p.get("title") or "").strip()
            category = (p.get("category") or "Drawings").strip() or "Drawings"
            image_b64 = p.get("image_base64")
            if not title:
                raise ValueError("create_drawing requires title")
            if not isinstance(image_b64, str) or not image_b64.strip():
                raise ValueError("create_drawing requires image_base64")
            try:
                image_bytes = base64.b64decode(image_b64.strip(), validate=True)
            except ValueError as exc:
                raise ValueError("image_base64 is not valid base64") from exc
            if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Drawing content must be a PNG image")
            if len(image_bytes) > MAX_IMAGE_BYTES:
                raise ValueError("image_base64 too large")
            safe_title = _safe_vault_filename(title)
            draw_dir = _upload_dir(profile_dir, "Drawings")
            if not draw_dir:
                raise ValueError("Drawing folder points outside the profile")
            os.makedirs(draw_dir, exist_ok=True)
            path = _unique_path(draw_dir, f"{safe_title}-{int(time.time())}.png")
            with open(path, "wb") as f:
                f.write(image_bytes)
            rel_path = os.path.relpath(path, prefs.vault_path(profile_dir)).replace("\\", "/")
            body_s = p.get("body")
            body_s = body_s if isinstance(body_s, str) else ("" if body_s is None else str(body_s))
            note_body = (body_s + _tags_suffix(p.get("tags"))).strip()
            note_body = (note_body + f"\n\nAttachment: {rel_path}").strip() if note_body else f"Attachment: {rel_path}"
            note = personal_service.create_note(profile_dir, title, note_body, category)
            history_service.log_event(
                profile_dir,
                "mobile-drawing",
                title,
                "Drawing received",
                {"path": rel_path, "note_id": note.get("id")},
            )
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"note_id": note.get("id"), "category": note.get("category"), "image_path": rel_path},
                "error": None,
            }

        if action == "save_selection":
            url = (p.get("url") or "").strip()
            text = p.get("text")
            text = text if isinstance(text, str) else ""
            if not text.strip():
                raise ValueError("save_selection requires text")
            title = (p.get("title") or "").strip() or url or "Selection"
            as_what = (p.get("as") or "note").strip().lower()
            tags_line = _tags_suffix(p.get("tags"))
            if as_what == "card":
                front = (p.get("front") or "").strip() or title
                back = text.strip() + (f"\n\n{url}" if url else "") + _card_tags(p.get("tags"))
                card = flashcard_service.add_card(profile_dir, front, back)
                return {
                    "ok": True,
                    "action": action,
                    "received_at": received,
                    "result": {"card_id": card.get("id"), "front": card.get("front")},
                    "error": None,
                }
            if as_what == "saved_page":
                if not url:
                    raise ValueError("save_selection as saved_page requires url")
                page = life_service.add_saved_page(profile_dir, title, url, summary=(text.strip() + tags_line).strip())
                return {
                    "ok": True,
                    "action": action,
                    "received_at": received,
                    "result": {"saved_page_id": page.get("id"), "url": page.get("url")},
                    "error": None,
                }
            category = (p.get("category") or "Clippings").strip() or "Clippings"
            body = text.strip()
            if url:
                body = f"{body}\n\nSource: {url}"
            body = (body + tags_line).strip()
            note = personal_service.create_note(profile_dir, title, body, category)
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"note_id": note.get("id"), "category": note.get("category")},
                "error": None,
            }

        if action == "save_page":
            url = (p.get("url") or "").strip()
            if not url:
                raise ValueError("save_page requires url")
            title = (p.get("title") or "").strip() or url
            summary = (p.get("summary") or "").strip()
            src = p.get("source_app")
            if src:
                summary = (summary + "\n\n" if summary else "") + f"source_app: {src}"
            page = life_service.add_saved_page(profile_dir, title, url, summary=summary)
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"saved_page_id": page.get("id")},
                "error": None,
            }

        if action == "open_app":
            app_id = (p.get("id") or "").strip()
            url = (p.get("url") or "").strip()
            label = (p.get("label") or "").strip()
            if not url and app_id:
                # Resolve the deployed URL from chain.json, falling back to the
                # desktop's local file:// app. No hard-coded URLs.
                if app_id in _CHAIN_APP_IDS:
                    # Prefer the deployed chain URL, including the packaged
                    # fallback map when the beside-the-EXE manifest has blank
                    # remote fields. Fall back to the local bundled copy only
                    # when no deployed URL is available.
                    for app in app_paths.chain_remote_sites():
                        if app.get("key") == app_id and app.get("url"):
                            url = str(app["url"]).strip()
                            break
                    if not url:
                        if app_id == "hub":
                            url = app_paths.project_hub_url()
                        else:
                            url = app_paths.bundled_site_url(app_id)
            if not url:
                raise ValueError("open_app requires url, or a chain app id in " + ",".join(_CHAIN_APP_IDS))
            if not url.startswith(("http://", "https://", "file://")):
                raise ValueError("open_app url must be http(s) or a bundled local app")
            parsed_url = urlparse(url)
            if parsed_url.scheme in ("http", "https") and (not parsed_url.hostname or parsed_url.username or parsed_url.password):
                raise ValueError("Invalid app URL")
            if parsed_url.scheme == "file":
                local_apps = {app_paths.project_hub_url(), *[app_paths.bundled_site_url(key) for key in _CHAIN_APP_IDS if key != "hub"]}
                if unquote(url) not in {unquote(value) for value in local_apps if value}:
                    raise ValueError("Only bundled app files can be opened remotely")
            open_request.push_open_request(
                profile_dir,
                {
                    "source": "android.mei_remote",
                    "url": url,
                    "label": label or app_id or url,
                    "kind": app_id or "url",
                },
            )
            return {
                "ok": True,
                "action": action,
                "received_at": received,
                "result": {"url": url, "kind": app_id or "url", "note": "The desktop will open this in a few seconds"},
                "error": None,
            }

        return {
            "ok": False,
            "action": action,
            "received_at": received,
            "result": None,
            "error": _json_error("unknown_action", f"Unknown action: {action}")["error"],
        }

    except ValueError as e:
        return {
            "ok": False,
            "action": action,
            "received_at": received,
            "result": None,
            "error": _json_error("invalid_payload", str(e))["error"],
        }
    except Exception:  # noqa: BLE001  safety net: log, never echo detail to phone
        # Never return raw exception text to the phone: str(e) often embeds
        # local file paths (v6.4 leaked them).
        _log.exception("mobile bridge action '%s' failed", action)
        return {
            "ok": False,
            "action": action,
            "received_at": received,
            "result": None,
            "error": _json_error("service_failure", "The desktop app could not complete this action.")["error"],
        }


#: A ``day`` query parameter must look like a date before it is handed to the
#: desk, otherwise a junk value would reach datetime.strptime and become a 500.
DAY_PARAM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Row fields the phone is allowed to see. The desk's rows carry a couple more
#: internals (``command``, ``kind``) that mean nothing on a small screen.
PHONE_ROW_KEYS = ("title", "subtitle", "marker", "kind", "id")


def _read_day(value: str) -> str:
    """The requested day when it is a real ``YYYY-MM-DD`` date, else "" (today)."""
    day = (value or "").strip()
    if not DAY_PARAM_RE.match(day):
        return ""
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return ""
    return day


def desk_for_phone(profile_dir: str, day: str = "") -> dict:
    """
    The desk as the phone reads it — the other direction of the bridge.

    Ingest actions let the phone *write* into Mei. This answers “what should I
    study today?”: the same four blocks Home opens on (``desk_service.build_desk``),
    trimmed to what fits a small screen — one line per row, plus the four numbers
    a home-screen widget can print. Read-only: no store is written, nothing is
    created, so calling it in a loop costs nothing but JSON parsing.
    """
    desk = desk_service.build_desk(profile_dir, day=_read_day(day))
    blocks = []
    for block in desk.get("blocks", []):
        rows = [
            {key: row.get(key, "") for key in PHONE_ROW_KEYS if row.get(key, "")}
            for row in block.get("rows", [])
        ]
        blocks.append(
            {
                "key": block.get("key", ""),
                "title": block.get("title", ""),
                "count": int(block.get("count", 0) or 0),
                "unit": block.get("unit", ""),
                "empty": block.get("empty", ""),
                "rows": rows,
            }
        )
    next_block = desk_service.block_by_key(desk, "next")
    return {
        "generated_at": _utc_iso_z(),
        "protocol_version": API_VERSION,
        "date": desk.get("date", ""),
        "headline": desk.get("headline", ""),
        "pulse": desk.get("pulse", ""),
        "steps": list(desk.get("steps", [])),
        "next": next_block.get("flow") or None,
        "blocks": blocks,
        "numbers": {
            "on_the_plate": int(desk_service.block_by_key(desk, "today").get("count", 0) or 0),
            "waiting": int(desk_service.block_by_key(desk, "due").get("count", 0) or 0),
            "left_open": int(desk_service.block_by_key(desk, "in_progress").get("count", 0) or 0),
            "cards_due": len(flashcard_service.due_cards(profile_dir)),
        },
    }


def _parse_multipart(content_type: str, body: bytes) -> list[tuple[str, str, bytes | None, str | None]]:
    """Parse a multipart/form-data body into (field_name, text_value, binary, filename).

    Handles UTF-8 filenames via both plain ``filename`` and RFC 5987 ``filename*``.
    """
    if "boundary=" not in content_type.lower():
        raise ValueError("Missing multipart boundary")
    try:
        msg = email.message_from_bytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body,
            policy=policy.default,
        )
    except Exception as exc:  # noqa: BLE001  arbitrary malformed MIME input
        raise ValueError("Malformed multipart body") from exc
    if not msg.is_multipart():
        raise ValueError("Body is not multipart")
    parts = []
    for part in msg.iter_parts():
        if part.is_multipart():
            continue
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str):
            name = str(name or "")
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        if filename is None:
            parts.append((name, payload.decode("utf-8", errors="replace"), None, None))
        else:
            parts.append((name, "", payload, filename))
    return parts


def _handle_upload(profile_dir: str, content_type: str, body: bytes) -> dict:
    """Persist one uploaded binary file under SafeVault/files; returns Android-shaped body."""
    received = _utc_iso_z()
    if len(body) > MAX_UPLOAD_BYTES:
        return {
            "ok": False,
            "action": "upload_file",
            "received_at": received,
            "result": None,
            "error": _json_error("payload_too_large", "Upload exceeds 25 MB")["error"],
        }
    try:
        parts = _parse_multipart(content_type, body)
    except ValueError as e:
        return {
            "ok": False,
            "action": "upload_file",
            "received_at": received,
            "result": None,
            "error": _json_error("bad_request", str(e))["error"],
        }

    fields: dict[str, str] = {}
    file_name = None
    file_bytes = None
    for name, text, binary, filename in parts:
        if binary is not None:
            if file_name is None:
                file_name = filename
                file_bytes = binary
            continue
        fields[name] = text

    if file_bytes is None or not file_name:
        return {
            "ok": False,
            "action": "upload_file",
            "received_at": received,
            "result": None,
            "error": _json_error("invalid_payload", "multipart requires a file part with a filename")["error"],
        }
    if not file_bytes:
        return {
            "ok": False,
            "action": "upload_file",
            "received_at": received,
            "result": None,
            "error": _json_error("invalid_payload", "Uploaded file is empty")["error"],
        }

    target_dir = _upload_dir(profile_dir, fields.get("relative_target") or "")
    if not target_dir:
        return {
            "ok": False,
            "action": "upload_file",
            "received_at": received,
            "result": None,
            "error": _json_error("invalid_payload", "Invalid relative_target")["error"],
        }
    safe_name = _safe_vault_filename(fields.get("filename") or file_name)
    os.makedirs(target_dir, exist_ok=True)
    path = _unique_path(target_dir, safe_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    rel_path = os.path.relpath(path, prefs.vault_path(profile_dir)).replace("\\", "/")
    history_service.log_event(
        profile_dir,
        "mobile-upload",
        safe_name,
        "File uploaded from mobile",
        {"path": rel_path, "size": len(file_bytes), "mime": fields.get("mime_type") or ""},
    )
    return {
        "ok": True,
        "action": "upload_file",
        "received_at": received,
        "result": {
            "path": rel_path,
            "filename": safe_name,
            "size": len(file_bytes),
            "relative_target": os.path.relpath(target_dir, os.path.join(prefs.vault_path(profile_dir), "files")).replace("\\", "/"),
        },
        "error": None,
    }


class _BridgeRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        return

    def _send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")

    def end_headers(self) -> None:
        # CORS is answered for extension origins only, and every response carries
        # it — including the error replies, so a failed call is readable by the
        # extension instead of surfacing as an opaque network error.
        origin = _extension_origin(self.headers.get("Origin"))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
        self._send_security_headers()
        super().end_headers()

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self) -> bool:
        srv: BridgeHTTPServer = self.server  # type: ignore[assignment]
        address = self.client_address[0]
        client_key = f"{srv.profile_dir}\0{address}"
        if not _permit(_requests, client_key, MAX_REQUESTS_PER_MINUTE):
            self._send_json(429, _json_error("rate_limited", "Too many requests"))
            return False
        if not _client_allowed(srv.profile_dir, address):
            self._send_json(403, _json_error("forbidden", "Client is outside the configured network scope"))
            return False
        return True

    def _authorized(self, profile_dir: str) -> bool:
        address = self.client_address[0]
        if _auth_ok(profile_dir, self.headers.get("Authorization")):
            return True
        if not _permit(_auth_failures, f"{profile_dir}\0{address}", MAX_AUTH_FAILURES_PER_MINUTE):
            self._send_json(429, _json_error("rate_limited", "Too many failed authentication attempts"))
        else:
            self._send_json(401, _json_error("unauthorized", "Invalid or missing token"))
        return False

    def _content_length(self) -> int | None:
        try:
            values = self.headers.get_all("Content-Length", [])
            raw = values[0] if len(values) == 1 else None
            if raw is None or not re.fullmatch(r"[0-9]{1,12}", raw):
                return None
            return int(raw)
        except ValueError:
            return None

    def _read_body(self, length):
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                self._send_json(400, _json_error("bad_request", "Incomplete request body"))
                return None
            return raw
        except (OSError, TimeoutError):
            self._send_json(408, _json_error("request_timeout", "Request body timed out"))
            return None

    def _body_too_large(self) -> bool:
        length = self._content_length()
        return length is not None and length > MAX_BODY_BYTES

    def do_OPTIONS(self) -> None:
        """CORS preflight: answered for browser extensions, refused for the web."""
        if not _extension_origin(self.headers.get("Origin")):
            self._send_json(405, _json_error("method_not_allowed", "CORS is answered for browser extensions only"))
            return
        if not self._guard():
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        srv: BridgeHTTPServer = self.server  # type: ignore[assignment]
        profile_dir = srv.profile_dir
        path = urlparse(self.path).path.rstrip("/") or "/"

        if not self._guard():
            return
        if not path.startswith("/api/mobile"):
            self.send_error(404)
            return

        if not self._authorized(profile_dir):
            return

        if path == "/api/mobile/ping":
            host = prefs.get_mobile_bridge_host(profile_dir)
            mode = "lan" if host == prefs.MOBILE_BRIDGE_LAN_HOST else "local"
            self._send_json(
                200,
                {
                    "ok": True,
                    "app": app_version.APP_NAME,
                    "bridge": "litebrowser-mobile",
                    "version": app_version.APP_VERSION,
                    "protocol_version": API_VERSION,
                    "mode": mode,
                    "capabilities": list(SUPPORTED_ACTIONS),
                },
            )
            return

        if path == "/api/mobile/today":
            # The other direction: the phone asks what is on the desk. Read-only,
            # same token as every other call, and a junk ?day= falls back to today
            # instead of raising inside the desk builder.
            day = parse_qs(urlparse(self.path).query).get("day", [""])[0]
            try:
                self._send_json(200, {"ok": True, **desk_for_phone(profile_dir, day)})
            except (OSError, ValueError, TypeError):
                self._send_json(500, _json_error("service_failure", "The desk could not be read; local data was not changed"))
            return

        if path == "/api/mobile/capabilities":
            self._send_json(
                200,
                {
                    "ok": True,
                    "protocol_version": API_VERSION,
                    "actions": list(SUPPORTED_ACTIONS),
                    "read": {"today": "/api/mobile/today", "day_param": True},
                    "auth": {"mode": "bearer"},
                    "upload": {
                        "multipart": True,
                        "max_size_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
                        "endpoint": "/api/mobile/upload",
                        "utf8_filenames": True,
                    },
                },
            )
            return

        self.send_error(404)

    def do_POST(self) -> None:
        srv: BridgeHTTPServer = self.server  # type: ignore[assignment]
        profile_dir = srv.profile_dir
        path = urlparse(self.path).path.rstrip("/") or "/"

        if not self._guard():
            return
        if path not in ("/api/mobile/ingest", "/api/mobile/upload"):
            self.send_error(404)
            return

        if not self._authorized(profile_dir):
            return

        if self.headers.get("Transfer-Encoding"):
            self._send_json(400, _json_error("bad_request", "Chunked request bodies are not supported"))
            return
        length = self._content_length()
        if length is None:
            self._send_json(400, _json_error("bad_request", "A valid Content-Length is required"))
            return

        if path == "/api/mobile/upload":
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
                self._send_json(415, _json_error("unsupported_media_type", "Content-Type must be multipart/form-data"))
                return
            if length > MAX_UPLOAD_BYTES:
                self._send_json(413, _json_error("payload_too_large", "Upload exceeds 25 MB"))
                return
            raw = self._read_body(length)
            if raw is None:
                return
            with profile_locked(profile_dir):
                out = _handle_upload(profile_dir, self.headers.get("Content-Type", ""), raw)
                if out.get("ok"):
                    history_service.log_event(profile_dir, "mobile-upload", str(out.get("result", {}).get("filename") or ""), "Mobile upload accepted", {"client": self.client_address[0]})
            self._send_json(200, out)
            return

        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self._send_json(415, _json_error("unsupported_media_type", "Content-Type must be application/json"))
            return
        if self._body_too_large():
            self._send_json(413, _json_error("payload_too_large", "JSON body exceeds 10 MB"))
            return

        raw = self._read_body(length)
        if raw is None:
            return
        try:
            data = json.loads(raw.decode("utf-8") if raw else "{}")
        except (ValueError, UnicodeError, RecursionError):
            self._send_json(400, _json_error("bad_request", "Invalid JSON body"))
            return

        if not isinstance(data, dict):
            self._send_json(400, _json_error("bad_request", "Body must be a JSON object"))
            return

        with profile_locked(profile_dir):
            out = dispatch_ingest(profile_dir, data)
            if out.get("ok"):
                history_service.log_event(profile_dir, "mobile-ingest", str(out.get("action") or ""), "Android bridge action accepted", {"client": self.client_address[0]})
        self._send_json(200, out)


def stop() -> None:
    global _server, _server_thread
    with _lock:
        if _server is None:
            return
        try:
            _server.shutdown()
        except Exception as exc:  # noqa: BLE001  shutdown while not serving is a no-op
            _log.debug("mobile bridge shutdown raised: %s", exc)
        try:
            _server.server_close()
        except OSError as exc:
            _log.debug("mobile bridge close raised: %s", exc)
        if _server_thread is not None:
            _server_thread.join(timeout=5.0)
        _server = None
        _server_thread = None


def start(profile_dir: str) -> bool:
    """Start listener if prefs say enabled. Returns True if server is running after call."""
    global _server, _server_thread
    profile_dir = prefs.ensure_profile_layout(profile_dir)
    if not prefs.get_mobile_bridge_enabled(profile_dir):
        return False
    prefs.ensure_mobile_bridge_token(profile_dir)
    host = prefs.get_mobile_bridge_host(profile_dir)
    port = prefs.get_mobile_bridge_port(profile_dir)
    with _lock:
        if _server is not None:
            return True
        try:
            server = BridgeHTTPServer(profile_dir, (host, port), _BridgeRequestHandler)
            thread = threading.Thread(target=server.serve_forever, name="AndroidBridgeHTTP", daemon=True)
            thread.start()
        except OSError:
            return False
        _server = server
        _server_thread = thread
    return True


def start_from_prefs(profile_dir: str) -> bool:
    stop()
    return start(profile_dir)


def restart(profile_dir: str) -> bool:
    return start_from_prefs(profile_dir)


def is_running() -> bool:
    with _lock:
        return _server is not None


def listen_address() -> tuple[str, int] | None:
    """Host and port when the bridge is running; for tests and diagnostics."""
    with _lock:
        if _server is None:
            return None
        return _server.server_address
