"""Self-hosted sync — push/pull a profile snapshot to your own HTTP endpoint.

The endpoint is a tiny API you run yourself (see README "Self-hosted sync"):
POST /api/sync/push stores the latest snapshot, GET /api/sync/latest returns
it. Every request carries a Bearer token. The payload is one JSON bundle
containing the local data (tasks, events, boards, saved pages, notes,
bookmarks, history, the weekly planner, flashcards and entity links) so two
machines can stay in step without any cloud.
"""

from __future__ import annotations

import ipaddress
import json
import math
import urllib.error
import urllib.parse
from datetime import datetime
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from litebrowser.core import prefs
from litebrowser.core.profile_lock import profile_transaction
from litebrowser.services import (
    flashcard_service,
    life_service,
    link_service,
    personal_plan,
    personal_service,
)

SYNC_API_VERSION = 1

#: A snapshot is remote input. These caps are checked before anything is
#: applied, so an oversized or deeply nested body fails without touching the
#: local profile.
MAX_BUNDLE_ROWS = 20_000
MAX_BUNDLE_STRING = 4 * 1024 * 1024
MAX_BUNDLE_DEPTH = 24
MAX_BUNDLE_KEYS = 256


@dataclass(frozen=True)
class SyncEntity:
    """One syncable collection: how to publish it and how to merge it back.

    Both directions read this registry, so adding an entity (or a new store) is
    one entry here instead of edits in three places — the bundle, the merge and
    the applied-count report used to drift apart.
    """

    key: str  # key inside the bundle payload
    counter: str  # key in the "applied" report shown to the user
    build: Callable[[str], Any]  # local profile -> bundle value
    merge: Callable[[str, Any], int]  # (profile, remote value) -> rows applied


def _rows_entity(key: str, counter: str, load, save) -> SyncEntity:
    """A plain row list merged by id (last writer wins per row)."""

    def build(base_dir: str):
        return load(base_dir) or []

    def merge(base_dir: str, incoming) -> int:
        rows = _dict_rows(incoming)
        existing = load(base_dir)
        merged = _upsert(existing, rows)
        if merged != existing:
            save(base_dir, merged)
        return len(rows)

    return SyncEntity(key, counter, build, merge)


def _note_key(note_id) -> str:
    """Sync ids always use ``/``; local Windows ids use ``\\``."""
    return str(note_id or "").replace("\\", "/").strip("/")


def _note_identity(note: dict) -> tuple[str, str]:
    return (_text(note.get("title")), _text(note.get("category"), "General") or "General")


def _conflict_note(base_dir: str, title: str, category: str, content: str, known: list[dict]):
    """Keep the other device's differing text as a clearly named note once.

    The check is against the whole local list (including notes created earlier
    in this merge), so pulling the same unchanged remote snapshot repeatedly
    cannot grow a new conflict copy every time.
    """
    conflict_title = f"{title} (other device)"
    for note in known:
        if (
            _text(note.get("title")) == conflict_title
            and (_text(note.get("category"), "General") or "General") == category
            and (note.get("content") or "") == content
        ):
            return note
    created = personal_service.create_note(base_dir, conflict_title, content, category)
    if created:
        known.append(created)
    return created


def _merge_notes(base_dir: str, incoming) -> int:
    """Merge notes by stable id, with a non-destructive legacy fallback.

    The bundle has always carried a note ``id``, but this merge used to ignore
    it and match on ``(title, category)``. A rename therefore looked like a new
    note and two distinct notes that happened to share a title could collapse
    into one. Current-format records now merge by id: an edit updates the same
    note, a rename survives, and a genuinely divergent edit is preserved as a
    ``(other device)`` copy. Records from an older peer that lack an id keep the
    old title/category fallback, which only ever adds or preserves text.
    """
    applied = 0
    local_notes = [
        note for note in personal_service.list_notes(base_dir) if isinstance(note, dict) and note.get("id")
    ]
    by_id = {_note_key(note["id"]): note for note in local_notes}
    by_title: dict[tuple[str, str], dict] = {}
    for note in local_notes:
        by_title.setdefault(_note_identity(note), note)

    for note in _dict_rows(incoming):
        title = _text(note.get("title"))
        category = _text(note.get("category"), "General") or "General"
        content = note.get("content") if isinstance(note.get("content"), str) else ""
        note_id = _note_key(note.get("id"))

        if note_id and len(note_id) <= 512:
            existing = by_id.get(note_id)
            if existing is None:
                created = personal_service.create_note_with_id(base_dir, note_id, content)
                if created:
                    by_id[note_id] = created
                    by_title.setdefault(_note_identity(created), created)
                    local_notes.append(created)
                    applied += 1
                continue
            if (existing.get("content") or "") == content:
                continue
            remote_time = _timestamp(note)
            local_time = _timestamp(existing)
            if remote_time and (not local_time or remote_time > local_time):
                updated = personal_service.update_note(base_dir, existing["id"], content)
                if updated:
                    existing.clear()
                    existing.update(updated)
                    applied += 1
                continue
            _conflict_note(base_dir, title or _text(existing.get("title")) or "note", category, content, local_notes)
            applied += 1
            continue

        # Legacy peer: no id. Match by title/category only when the local note
        # is still in that location; otherwise a rename would be duplicated.
        if not title:
            continue
        existing = by_title.get((title, category))
        if existing:
            if (existing.get("content") or "") == content:
                continue
            _conflict_note(base_dir, title, category, content, local_notes)
            applied += 1
            continue
        created = personal_service.create_note(base_dir, title, content, category)
        if created:
            by_id[_note_key(created["id"])] = created
            by_title[_note_identity(created)] = created
            local_notes.append(created)
            applied += 1
    return applied


def _merge_bookmarks(base_dir: str, incoming) -> int:
    """Merge by URL. v6.4 replaced the local list wholesale, so pulling from a
    device with sparse data silently deleted bookmarks saved on this machine."""
    remote_bookmarks = _dict_rows(incoming)
    if not remote_bookmarks:
        return 0
    local_bookmarks = prefs.load_bookmarks(base_dir) or []
    local_by_url = {}
    for bm in local_bookmarks:
        if isinstance(bm, dict):
            url = _text(bm.get("url"))
            if url:
                local_by_url[url] = bm
    merged = list(local_bookmarks)
    for bm in remote_bookmarks:
        url = _text(bm.get("url"))
        if not url or url in local_by_url:
            continue
        merged.append(bm)
        local_by_url[url] = bm
    if merged != local_bookmarks:
        prefs.save_bookmarks(base_dir, merged)
    return len(remote_bookmarks)


def _merge_history(base_dir: str, incoming) -> int:
    """Merge (timestamp, url) tuples, newest first, capped generously."""
    remote_history = []
    items = incoming if isinstance(incoming, list) else []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        try:
            remote_history.append((int(item[0] or 0), str(item[1] or "")))
        except (TypeError, ValueError, OverflowError):
            continue
    if not remote_history:
        return 0
    existing = prefs.load_history_entries(base_dir)
    merged = existing + [item for item in remote_history if item not in existing]
    merged.sort(key=lambda item: -int(item[0] or 0))
    # Keep a generous cap: v6.4 trimmed to 1500, so one pull from a sparse
    # device could throw away months of local history.
    prefs.save_history_entries(base_dir, merged[:5000])
    return len(remote_history)


def _build_notes(base_dir: str):
    return [
        {
            "id": n.get("id", ""),
            "updated_at": n.get("updated_at", ""),
            "title": n.get("title", ""),
            "category": n.get("category", "General"),
            "content": n.get("content", ""),
        }
        for n in (personal_service.list_notes(base_dir) or [])
    ]


def _merge_plan(base_dir: str, incoming) -> int:
    """Merge a planner snapshot: incoming rows win per id, like every other
    collection. The semester header is only replaced when the remote actually
    carries one, so a pull from a profile that never configured it cannot
    blank a semester filled in on this machine."""
    if not isinstance(incoming, dict):
        return 0
    plan = personal_plan.load_plan(base_dir)
    applied = 0
    for key in ("items", "courses", "time_blocks"):
        rows = _dict_rows(incoming.get(key))
        plan[key] = _upsert(plan.get(key, []), rows)
        applied += len(rows)
    semester = incoming.get("semester")
    if isinstance(semester, dict) and any(_text(value) for value in semester.values()):
        plan["semester"] = semester
    if plan != personal_plan.load_plan(base_dir):
        personal_plan.save_plan(base_dir, plan)
    return applied


# Bundle key, report key, publish, merge — in the order the report shows.
SYNC_ENTITIES: tuple[SyncEntity, ...] = (
    _rows_entity("tasks", "tasks", life_service.load_tasks, life_service.save_tasks),
    _rows_entity("events", "events", life_service.load_events, life_service.save_events),
    _rows_entity("boards", "boards", life_service.load_boards, life_service.save_boards),
    _rows_entity("saved_pages", "pages", life_service.load_saved_pages, life_service.save_saved_pages),
    SyncEntity("notes", "notes", _build_notes, _merge_notes),
    SyncEntity("bookmarks", "bookmarks", lambda b: prefs.load_bookmarks(b) or [], _merge_bookmarks),
    SyncEntity(
        "history",
        "history",
        lambda b: [list(item) for item in (prefs.load_history_entries(b) or [])[:500]],
        _merge_history,
    ),
    SyncEntity("personal_plan", "planner", personal_plan.load_plan, _merge_plan),
    _rows_entity(
        "flashcards", "flashcards", flashcard_service.load_cards, flashcard_service.save_cards
    ),
    _rows_entity("entity_links", "links", link_service.load_links, link_service.save_links),
)


@profile_transaction
def _bundle(base_dir: str) -> dict:
    payload = {
        "app": "litebrowser",
        "kind": "snapshot",
        "api": SYNC_API_VERSION,
        "exported_at": int(time.time()),
    }
    for entity in SYNC_ENTITIES:
        payload[entity.key] = entity.build(base_dir)
    return payload


def _dict_rows(value) -> list[dict]:
    """Return independently-owned mapping rows from an external snapshot.

    Sync responses are remote input.  A malformed array must be ignored rather
    than making a pull crash halfway through applying the rest of the bundle.
    """
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _text(value, default: str = "") -> str:
    """Accept text-only fields from a remote snapshot without coercion."""
    return value.strip() if isinstance(value, str) else default


def _upsert(existing, incoming, key="id"):
    existing_rows = _dict_rows(existing)
    incoming_rows = _dict_rows(incoming)
    by_id = {}
    unkeyed = []
    for item in existing_rows:
        row_id = item.get(key)
        if isinstance(row_id, str) and row_id:
            by_id[row_id] = item
        else:
            unkeyed.append(item)
    for item in incoming_rows:
        row_id = item.get(key)
        if not isinstance(row_id, str) or not row_id:
            continue
        current = by_id.get(row_id)
        if current is None or _timestamp(item) >= _timestamp(current):
            by_id[row_id] = item
    return [*unkeyed, *by_id.values()]


def _timestamp(row):
    value = row.get("updated_at") or row.get("created_at") or 0
    try:
        result = float(value)
        return result if math.isfinite(result) else 0
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except (ValueError, OSError, OverflowError):
            return 0


@profile_transaction
def _apply_bundle(base_dir: str, bundle: dict) -> dict:
    """Merge a remote snapshot into the local profile (last-writer-wins per item).

    Each collection is merged by the rule in its ``SYNC_ENTITIES`` entry, so a
    new synced store only needs a registry entry — the bundle, the merge and the
    applied-count report can no longer drift apart.
    """
    applied = {entity.counter: 0 for entity in SYNC_ENTITIES}
    if not isinstance(bundle, dict):
        return applied
    for entity in SYNC_ENTITIES:
        if entity.key in bundle:
            applied[entity.counter] = entity.merge(base_dir, bundle[entity.key])
    return applied


def validate_endpoint(endpoint: str) -> tuple[str, str]:
    """Return ``(base_url, error)`` for a user-entered sync endpoint.

    Only explicit http(s) base URLs are accepted. Credentials in the URL,
    query strings and fragments are refused before the bearer token is ever
    attached; a redirect is still blocked separately in ``_NoRedirect``.
    """
    text = str(endpoint or "").strip().rstrip("/")
    if not text:
        return "", "No sync endpoint set."
    try:
        parsed = urllib.parse.urlsplit(text)
        _ = parsed.port
    except ValueError:
        return "", "The sync endpoint is not a valid URL."
    if parsed.scheme not in ("http", "https"):
        return "", "The sync endpoint must start with http:// or https://."
    if not parsed.hostname:
        return "", "The sync endpoint has no host name."
    if parsed.username or parsed.password:
        return "", "Remove the username or password from the endpoint; the bearer token is the credential."
    if parsed.query or parsed.fragment:
        return "", "Enter the base endpoint only, without a query string or fragment."
    return text, ""


def endpoint_warning(endpoint: str) -> str:
    """A clear caution for a non-loopback cleartext endpoint, else ``""``.

    The bearer token travels with every request. HTTP on a LAN is a deliberate
    small-server choice, not something Mei should hide from the user.
    """
    base, error = validate_endpoint(endpoint)
    if error:
        return error
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "http":
        return ""
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if host == "localhost":
        return ""
    try:
        if ipaddress.ip_address(host).is_loopback:
            return ""
    except ValueError:
        pass
    return (
        "This endpoint uses cleartext HTTP, so the bearer token and your notes travel "
        "unencrypted on the network. Use HTTPS, or an HTTP endpoint only on a trusted "
        "local network or through a VPN."
    )


def _bundle_within_limits(value, depth: int = 0) -> bool:
    """Bound a remote snapshot before any store is touched."""
    if depth > MAX_BUNDLE_DEPTH:
        return False
    if isinstance(value, str):
        return len(value) <= MAX_BUNDLE_STRING
    if isinstance(value, dict):
        return len(value) <= MAX_BUNDLE_KEYS and all(
            isinstance(key, str) and len(key) <= 256 and _bundle_within_limits(item, depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return len(value) <= MAX_BUNDLE_ROWS and all(
            _bundle_within_limits(item, depth + 1) for item in value
        )
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (bool, int))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A sync endpoint must not forward a profile/token to another host.
        return None


def _request(url: str, token: str, method: str = "GET", payload=None) -> tuple[bool, object, str]:
    try:
        headers = {
            "Authorization": "Bearer %s" % token,
            "X-Mei-Sync": "1",
            "Accept": "application/json",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=15) as resp:
            raw = resp.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                return False, None, "Sync snapshot is too large"
            body = raw.decode("utf-8")
            parsed = None
            if body.strip():
                try:
                    parsed = json.loads(body)
                except ValueError:
                    parsed = body
            return True, parsed, ""
    except urllib.error.HTTPError as exc:
        return False, None, "No snapshot yet" if exc.code == 404 else str(exc)
    except (OSError, ValueError, UnicodeError) as exc:
        return False, None, str(exc)


def push(base_dir: str, endpoint: str, token: str) -> tuple[bool, str]:
    endpoint, error = validate_endpoint(endpoint)
    if error:
        return False, error
    ok, _resp, err = _request(endpoint + "/api/sync/push", token, method="POST", payload=_bundle(base_dir))
    if not ok:
        return False, "Push failed: %s" % (err or "connection error")
    _record_sync(base_dir, pushed_at=int(time.time()))
    return True, "Pushed snapshot."


def pull(base_dir: str, endpoint: str, token: str) -> tuple[bool, str]:
    endpoint, error = validate_endpoint(endpoint)
    if error:
        return False, error
    ok, resp, err = _request(endpoint + "/api/sync/latest", token)
    if not ok:
        return False, "Pull failed: %s" % (err or "connection error")
    if not isinstance(resp, dict) or resp.get("kind") != "snapshot" or resp.get("api", 1) != SYNC_API_VERSION or resp.get("app", "litebrowser") not in ("litebrowser", "mei"):
        return False, "Remote did not return a snapshot."
    if not _bundle_within_limits(resp):
        return False, "Remote snapshot is malformed or too large. Nothing was changed."
    applied = _apply_bundle(base_dir, resp)
    _record_sync(base_dir, pulled_at=int(time.time()))
    counts = " · ".join("%s=%s" % (k, v) for k, v in applied.items() if v)
    return True, "Pulled snapshot. (%s)" % (counts or "no changes")


def sync_now(base_dir: str, endpoint: str, token: str) -> tuple[bool, str]:
    # Read before publishing: publishing first replaces the only remote copy
    # and silently discards changes from the other device.
    ok_pull, msg_pull = pull(base_dir, endpoint, token)
    if not ok_pull and "No snapshot yet" not in msg_pull:
        return False, msg_pull
    ok_push, msg_push = push(base_dir, endpoint, token)
    return ok_push, (msg_pull + " " + msg_push if ok_push else msg_push)


@profile_transaction
def _record_sync(base_dir: str, pushed_at: int | None = None, pulled_at: int | None = None):
    data = life_service.load_sync_state(base_dir)
    if pushed_at:
        data["last_push_at"] = pushed_at
    if pulled_at:
        data["last_pull_at"] = pulled_at
    data["last_sync_at"] = int(time.time())
    life_service.save_sync_state(base_dir, data)


def last_sync(base_dir: str) -> int | None:
    data = life_service.load_sync_state(base_dir)
    value = int(data.get("last_sync_at") or 0)
    return value or None
