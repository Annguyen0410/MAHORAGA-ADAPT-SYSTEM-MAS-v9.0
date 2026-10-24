"""Page monitor: watch a public http(s) page for changes and toast when it shifts.

``monitors.json`` (per profile) is user data and must be treated as untrusted:

    {"version": 1, "monitors": [
      {"id": "...", "url": "...", "title": "...", "hash": "...",
       "last_checked": unix, "enabled": true, "last_error": ""}
    ]}

Checks run on the shell's executor every few minutes: fetch the URL with
``urllib`` (raw HTML — pages that need JS are a known limitation), hash the
body, and compare with the stored hash. The first successful check seeds the
hash without alerting.

Safety rules:

* only explicit ``http``/``https`` targets are accepted; loopback, private,
  link-local and ``.local``/``.internal`` hosts are refused so this feature
  cannot become a local-network scanner;
* redirects are re-validated against the same rule;
* responses are capped in bytes and time, and a failed check never updates the
  stored hash. A failure is recorded in ``last_error`` and shown separately
  from “unchanged”;
* one malformed row is skipped instead of disabling every other watched page.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked
from litebrowser.core.storage_utils import read_json, write_json

_log = get_logger("page_monitor")

SUPPORTED_SCHEMES = frozenset({"http", "https"})
MAX_URL_CHARS = 2048
MAX_MONITORS = 200
MAX_TITLE_CHARS = 120
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0
CHECK_INTERVAL_SECONDS = 15 * 60
MAX_ERROR_CHARS = 300

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MONITOR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".internal")


class MonitorError(ValueError):
    """The URL cannot be a safe, explicit watch target."""


class MonitorFetchError(RuntimeError):
    """A check failed before a reliable content hash could be produced."""


def _path(base_dir: str) -> str:
    return os.path.join(base_dir, "monitors.json")


def _title(value, fallback: str) -> str:
    text = str(value or "").strip()
    text = _CONTROL_RE.sub(" ", text)
    text = " ".join(text.split())
    return (text or fallback)[:MAX_TITLE_CHARS]


def _parse_last_checked(value, now: int) -> int:
    """A stored timestamp is a hint, never a reason to crash or spin."""
    try:
        stamp = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(stamp, now))


def _is_local_host(hostname: str) -> bool:
    host = (hostname or "").strip().rstrip(".").lower()
    if not host:
        return True
    if host == "localhost" or host.endswith(_LOCAL_HOST_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def normalize_url(url: str) -> str:
    """Return a canonical ``http(s)`` watch URL or raise :class:`MonitorError`.

    Parsing is done with :func:`urllib.parse.urlsplit`, so a query-only URL
    (``https://example.com?sort=1``) keeps its query instead of growing a path,
    and fragments are dropped because a server never receives them. Scheme and
    hostname are lowercased, default ports are removed, and a non-root path
    loses one trailing slash so ``/page`` and ``/page/`` are one target.
    """
    text = str(url or "").strip()
    if not text:
        raise MonitorError("Enter an http:// or https:// page to watch.")
    if len(text) > MAX_URL_CHARS:
        raise MonitorError("That URL is too long to watch.")
    if _CONTROL_RE.search(text) or any(char.isspace() for char in text):
        raise MonitorError("That URL contains spaces or control characters.")
    scheme_prefix = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", text)
    if "://" not in text:
        if scheme_prefix and scheme_prefix.group(1).lower() not in SUPPORTED_SCHEMES:
            raise MonitorError("Only http:// and https:// pages can be watched.")
        # A pasted bare host is common; assume https rather than silently
        # treating the whole string as a relative path.
        text = "https://" + text

    try:
        parts = urllib.parse.urlsplit(text)
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise MonitorError("That URL could not be parsed. Check it and try again.") from exc
    scheme = (parts.scheme or "").lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise MonitorError("Only http:// and https:// pages can be watched.")
    if not hostname:
        raise MonitorError("That URL has no host name.")
    if parts.username or parts.password:
        raise MonitorError("Remove the username or password from the watched URL.")
    if port is not None and not (1 <= port <= 65535):
        raise MonitorError("That URL has an invalid port.")
    if _is_local_host(hostname):
        raise MonitorError("Local and private addresses cannot be watched.")

    try:
        ascii_host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise MonitorError("That URL's host name is not valid.") from exc
    netloc = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit((scheme, netloc, path, parts.query, ""))


def load_monitors(base_dir: str) -> list[dict]:
    """Read the watch list, skipping malformed rows instead of aborting it."""
    data = read_json(_path(base_dir), {"version": 1, "monitors": []})
    if not isinstance(data, dict):
        _log.warning("monitors.json in %s is not an object; ignoring it", os.path.basename(base_dir))
        return []
    rows = data.get("monitors")
    if not isinstance(rows, list):
        return []
    now = int(time.time())
    monitors: list[dict] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            url = normalize_url(raw.get("url") or "")
        except MonitorError as exc:
            _log.info("skipping malformed monitor row: %s", exc)
            continue
        monitor_id = str(raw.get("id") or "").strip()
        if not _MONITOR_ID_RE.match(monitor_id) or monitor_id in seen_ids:
            _log.info("skipping monitor row with a missing or duplicate id")
            continue
        if url in seen_urls:
            continue
        seen_ids.add(monitor_id)
        seen_urls.add(url)
        stored_hash = raw.get("hash")
        enabled = raw.get("enabled", True)
        monitors.append(
            {
                "id": monitor_id,
                "url": url,
                "title": _title(raw.get("title"), url),
                "hash": stored_hash[:128] if isinstance(stored_hash, str) else "",
                "last_checked": _parse_last_checked(raw.get("last_checked"), now),
                "enabled": enabled if isinstance(enabled, bool) else True,
                "last_error": str(raw.get("last_error") or "")[:MAX_ERROR_CHARS].strip(),
            }
        )
    return monitors


def save_monitors(base_dir: str, monitors: list[dict]) -> None:
    rows = [row for row in (monitors or []) if isinstance(row, dict)][:MAX_MONITORS]
    with profile_locked(base_dir):
        write_json(_path(base_dir), {"version": 1, "monitors": rows})


def add_monitor(base_dir: str, url: str, title: str = "") -> dict:
    """Add a watch target; returns ``{}`` when the URL is already watched."""
    normalized = normalize_url(url)
    monitors = load_monitors(base_dir)
    if any(monitor["url"] == normalized for monitor in monitors):
        return {}
    if len(monitors) >= MAX_MONITORS:
        raise MonitorError(f"Mei can watch up to {MAX_MONITORS} pages at a time. Remove one first.")
    monitor = {
        "id": os.urandom(6).hex(),
        "url": normalized,
        "title": _title(title, normalized),
        "hash": "",
        "last_checked": 0,
        "enabled": True,
        "last_error": "",
    }
    monitors.append(monitor)
    save_monitors(base_dir, monitors)
    return monitor


def remove_monitor(base_dir: str, monitor_id: str) -> bool:
    target = str(monitor_id or "").strip()
    if not target:
        return False
    monitors = load_monitors(base_dir)
    kept = [row for row in monitors if row.get("id") != target]
    if len(kept) == len(monitors):
        return False
    save_monitors(base_dir, kept)
    return True


class _HttpOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when the destination is still a public http(s) URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        try:
            safe = normalize_url(target)
        except MonitorError as exc:
            raise MonitorFetchError("The page redirected to an unsupported or local address.") from exc
        return super().redirect_request(req, fp, code, msg, headers, safe)


def _open_url(url: str, timeout: float):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mei/7 page-monitor",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
        },
    )
    opener = urllib.request.build_opener(_HttpOnlyRedirect())
    return opener.open(request, timeout=timeout)


def _fetch_page(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS, max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    safe_url = normalize_url(url)
    try:
        with _open_url(safe_url, timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status and int(status) >= 400:
                raise MonitorFetchError(f"The server returned HTTP {int(status)}.")
            declared = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
            if declared:
                try:
                    if int(declared) > max_bytes:
                        raise MonitorFetchError("The page is too large to watch safely.")
                except (TypeError, ValueError):
                    pass
            body = response.read(max_bytes + 1)
    except MonitorFetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise MonitorFetchError(f"The server returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", "") or "connection failed")
        raise MonitorFetchError(f"Could not reach the page ({reason[:120]}).") from exc
    except (OSError, ValueError) as exc:
        raise MonitorFetchError(f"Could not read the page ({type(exc).__name__}).") from exc
    if len(body) > max_bytes:
        raise MonitorFetchError("The page is too large to watch safely.")
    return body


def fetch_and_hash(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Raw HTML hash; ``None`` on failure (kept for existing callers/tests)."""
    try:
        body = _fetch_page(url, timeout=timeout)
    except MonitorFetchError as exc:
        _log.debug("page monitor fetch failed for %s: %s", url, exc)
        return None
    return hashlib.blake2s(body, digest_size=16).hexdigest()


def due_monitors(base_dir: str, interval_seconds: int = CHECK_INTERVAL_SECONDS) -> list[dict]:
    try:
        interval = max(60, int(interval_seconds or CHECK_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        interval = CHECK_INTERVAL_SECONDS
    now = int(time.time())
    return [
        monitor
        for monitor in load_monitors(base_dir)
        if monitor.get("enabled") and now - int(monitor.get("last_checked", 0) or 0) >= interval
    ]


def record_check(base_dir: str, monitor_id: str, content_hash: str) -> str:
    """Store the new hash; returns ``changed`` | ``same`` | ``seeded`` | ``missing``."""
    digest = str(content_hash or "").strip()[:128]
    if not digest:
        return "missing"
    monitors = load_monitors(base_dir)
    outcome = "missing"
    for monitor in monitors:
        if monitor.get("id") != monitor_id:
            continue
        old = str(monitor.get("hash") or "")
        if not old:
            outcome = "seeded"
        elif old != digest:
            outcome = "changed"
        else:
            outcome = "same"
        monitor["hash"] = digest
        monitor["last_checked"] = int(time.time())
        monitor["last_error"] = ""
        break
    if outcome != "missing":
        save_monitors(base_dir, monitors)
    return outcome


def record_failure(base_dir: str, monitor_id: str, message: str) -> bool:
    """Record a failed check without touching the stored content hash."""
    monitors = load_monitors(base_dir)
    for monitor in monitors:
        if monitor.get("id") != monitor_id:
            continue
        monitor["last_checked"] = int(time.time())
        monitor["last_error"] = str(message or "The check failed.")[:MAX_ERROR_CHARS]
        save_monitors(base_dir, monitors)
        return True
    return False


def check_monitor(
    base_dir: str,
    monitor_id: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> dict:
    """Fetch one watched page and update its row.

    Returns ``{"status": "changed"|"same"|"seeded"|"error"|"missing",
    "error": "..."}``. A failed fetch is recorded as ``error`` and keeps the
    previous hash, so the next successful check still reports the real change.
    """
    monitor = next((row for row in load_monitors(base_dir) if row.get("id") == monitor_id), None)
    if monitor is None:
        return {"status": "missing", "error": "That watched page no longer exists."}
    try:
        body = _fetch_page(monitor["url"], timeout=timeout, max_bytes=max_bytes)
    except MonitorFetchError as exc:
        record_failure(base_dir, monitor_id, str(exc))
        return {"status": "error", "error": str(exc)}
    digest = hashlib.blake2s(body, digest_size=16).hexdigest()
    return {"status": record_check(base_dir, monitor_id, digest), "error": ""}


__all__ = [
    "CHECK_INTERVAL_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_MONITORS",
    "MAX_RESPONSE_BYTES",
    "MonitorError",
    "MonitorFetchError",
    "SUPPORTED_SCHEMES",
    "add_monitor",
    "check_monitor",
    "due_monitors",
    "fetch_and_hash",
    "load_monitors",
    "normalize_url",
    "record_check",
    "record_failure",
    "remove_monitor",
    "save_monitors",
]
