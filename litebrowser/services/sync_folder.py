"""Folder sync — the same profile on two machines, through a folder you own.

``sync_service`` pushes a whole bundle to an HTTP endpoint you run yourself; that
is a *transport*, and it overwrites per row with no memory of what either side
looked like last time. This module is the other half of the promise: Mei should
sync through a folder you already have (OneDrive, Google Drive, a network share,
Syncthing) with **no server and no account**, and it must never lose a record
while doing it.

How it stays safe — a three-way merge against a *baseline*:

* every profile remembers the last state it agreed on (``sync_folder_state.json``:
  ``{store: {record_id: content_hash}}``) — this is the only thing that makes
  "deleted here" distinguishable from "never existed there";
* each record's content is hashed (volatile keys excluded per store, e.g. the
  planner rewrites ``updated_at`` on every save), so *changed* means the content
  changed, not the clock;
* per record: if one side changed and the other did not, the changed one wins;
  if both changed differently it is a **conflict**, and the store's policy decides
  — text-like records (notes, tasks, planner rows) keep *both* versions, while
  scheduling records (cards) keep the local copy. Either way nobody's edit is
  silently dropped, and the conflict is reported;
* deletes travel: a record that is in the baseline, gone locally, and unchanged
  remotely is published as a tombstone so the other machine removes it too. A
  record deleted on one side but *edited* on the other comes back instead of
  disappearing;
* before anything is written, the affected stores are copied into
  ``<profile>/backups/sync-<stamp>/`` — the merge is a write, and a write you
  cannot undo is the one thing this feature must never be;
* ``compute()`` (or ``sync(apply=False)``) works the whole merge out and writes
  **nothing**, so the Settings card can show what a sync would do before it is
  allowed to do it.

Scope is deliberate: personal and study stores travel (tasks, calendar, boards,
saved pages, the planner, the deck, entity links, notes). Browser history,
bookmarks, cookies, passwords and the pour timer do not — they are per-machine
by nature, and saying so is better than pretending.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from litebrowser.core import prefs, storage_utils
from litebrowser.core.profile_lock import profile_transaction
from litebrowser.services import (
    flashcard_service,
    life_service,
    link_service,
    personal_plan,
    personal_service,
)

PAYLOAD_NAME = "mei-sync.json"
STATE_NAME = "sync_folder_state.json"
PAYLOAD_KIND = "mei-folder-sync"
PAYLOAD_VERSION = 1
STATE_VERSION = 1

#: Preference holding the chosen folder (empty = folder sync switched off).
FOLDER_PREF = "sync_folder"
#: Preference holding this profile's device id, so a payload can say who wrote it.
DEVICE_PREF = "sync_device_id"

BACKUP_DIRNAME = "backups"
BACKUP_PREFIX = "sync-"

#: A folder that is itself a block-synced cloud drive needs the user's attention:
#: those clients sync whole files and can hand us a half-written payload.
CLOUD_HINTS = ("onedrive", "google drive", "googledrive", "dropbox", "icloud", "box sync")

#: Rows are published as plain JSON, so a store cannot grow without bound by
#: accident; notes carry content and are counted separately in the report.
MAX_RECORDS_PER_STORE = 20_000


@dataclass(frozen=True)
class StoreAdapter:
    """One syncable collection and how to read/write/duplicate its records.

    ``load`` returns the current records (each with an ``id``); ``replace``
    writes a whole merged collection back through the store's own writer, which
    is what keeps this module from touching files directly. ``ignore`` lists keys
    excluded from the content hash — only for keys a *save* rewrites without the
    user having changed anything.
    """

    key: str
    label: str
    load: Callable[[str], list[dict]]
    replace: Callable[[str, list[dict]], None]
    ignore: frozenset = frozenset()
    keep_both_on_conflict: bool = True
    duplicate: Callable[[str, dict], dict | None] | None = None


#: Never part of a record's identity: the absolute path a note happens to live
#: at on *this* machine, the derived snippet, and the hash itself. ``_kind`` is
#: *not* here — it is what tells the planner's flat records apart again.
VOLATILE_KEYS = frozenset({"path", "snippet", "_hash"})


def _hash_record(row: dict, ignore: frozenset) -> str:
    skip = ignore | VOLATILE_KEYS
    payload = {key: value for key, value in row.items() if key not in skip}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.blake2s(text.encode("utf-8", "surrogatepass"), digest_size=12).hexdigest()


def _cell(row: dict, ignore: frozenset = frozenset()) -> dict:
    """A record without the keys that describe *this machine's* copy.

    ``path`` and ``snippet`` are derived (the absolute file a note happens to
    live at, a search snippet); the adapter's ``ignore`` keys are the ones a save
    rewrites on its own — a note's ``updated_at`` is its file mtime, so publishing
    it would make two machines differ forever over a timestamp nobody set.
    """
    skip = ignore | VOLATILE_KEYS
    return {key: value for key, value in row.items() if key not in skip}


# --------------------------------------------------------------------------- #
# Store adapters
# --------------------------------------------------------------------------- #
def _list_store(key: str, label: str, load, save, ignore=frozenset()) -> StoreAdapter:
    """A plain row list: merge by id, then hand the merged list to ``save``."""

    def replace(base_dir: str, rows: list[dict]) -> None:
        save(base_dir, [_cell(row) for row in rows])

    return StoreAdapter(key=key, label=label, load=load, replace=replace, ignore=ignore)


def _plan_records(base_dir: str) -> list[dict]:
    """The plan as flat records: ``item:``/``course:``/``block:`` + id."""
    plan = personal_plan.load_plan(base_dir)
    rows: list[dict] = []
    for kind, collection in (
        ("item", plan.get("items", [])),
        ("course", plan.get("courses", [])),
        ("block", plan.get("time_blocks", [])),
    ):
        for record in collection:
            if isinstance(record, dict) and record.get("id"):
                rows.append({**record, "id": f"{kind}:{record['id']}", "_kind": kind})
    return rows


def _replace_plan_records(base_dir: str, rows: list[dict]) -> None:
    plan = personal_plan.load_plan(base_dir)
    buckets: dict[str, list[dict]] = {"item": [], "course": [], "block": []}
    for row in rows:
        record = _cell(row)
        raw_id = str(record.get("id", ""))
        # ``_kind`` is published, but a hand-written payload may only carry the
        # prefixed id — accept both rather than dropping the record on the floor.
        kind = str(row.get("_kind", "")) or (raw_id.split(":", 1)[0] if ":" in raw_id else "")
        if kind not in buckets:
            continue
        record["id"] = raw_id.split(":", 1)[-1]
        buckets[kind].append(record)
    plan["items"] = buckets["item"]
    plan["courses"] = buckets["course"]
    plan["time_blocks"] = buckets["block"]
    personal_plan.save_plan(base_dir, plan)


def _duplicate_plan_record(kind: str):
    def duplicate(base_dir: str, row: dict) -> dict | None:
        record = _cell(row)
        record.pop("id", None)
        title = str(record.get("title") or "").strip() or "Untitled"
        record["title"] = f"{title} (other machine)"
        fields = {k: v for k, v in record.items() if k not in {"title", "created_at", "updated_at", "_kind"}}
        if kind == "item":
            return personal_plan.create_item(base_dir, record["title"], **fields)
        if kind == "course":
            return personal_plan.create_course(base_dir, record["title"], **fields)
        return personal_plan.create_time_block(
            base_dir,
            record["title"],
            record.get("date") or datetime.now().strftime("%Y-%m-%d"),
            int(record.get("start_minutes", 0) or 0),
            **{k: v for k, v in fields.items() if k not in {"date", "start_minutes"}},
        )

    return duplicate


def _note_records(base_dir: str) -> list[dict]:
    rows = []
    for note in personal_service.list_notes(base_dir):
        if isinstance(note, dict) and note.get("id"):
            rows.append(dict(note))
    return rows


def _replace_notes(base_dir: str, rows: list[dict]) -> None:
    """Notes are one file each: write every desired note, delete the rest.

    Applied per note id so a partial failure cannot empty the vault, and the
    baseline is rebuilt from what is actually on disk afterwards, which keeps a
    note whose file name had to change from being re-published forever.
    """
    desired = {str(row.get("id")): row for row in rows if row.get("id")}
    existing = {note["id"]: note for note in _note_records(base_dir)}
    for note_id, row in desired.items():
        title = str(row.get("title") or "").strip() or "note"
        category = str(row.get("category") or "General").strip() or "General"
        content = row.get("content") if isinstance(row.get("content"), str) else ""
        if note_id in existing:
            if (existing[note_id].get("content") or "") != content or existing[note_id].get("category") != category:
                personal_service.update_note(base_dir, note_id, content, category)
            continue
        personal_service.create_note(base_dir, title, content, category)
    for note_id in existing:
        if note_id not in desired:
            personal_service.delete_note(base_dir, note_id)


def _duplicate_note(base_dir: str, row: dict) -> dict | None:
    title = str(row.get("title") or "note").strip() or "note"
    content = row.get("content") if isinstance(row.get("content"), str) else ""
    category = str(row.get("category") or "General").strip() or "General"
    return personal_service.create_note(base_dir, f"{title} (other machine)", content, category)


#: Volatile keys a save rewrites without the user changing anything: the planner
#: normalizes every record on write and stamps ``updated_at`` with *now*.
PLAN_IGNORE = frozenset({"updated_at", "created_at"})

ADAPTERS: tuple[StoreAdapter, ...] = (
    _list_store("tasks", "Quick tasks", life_service.load_tasks, life_service.save_tasks, frozenset({"created_at"})),
    _list_store("events", "Calendar", life_service.load_events, life_service.save_events, frozenset({"created_at"})),
    _list_store("boards", "Idea boards", life_service.load_boards, life_service.save_boards, frozenset({"created_at"})),
    _list_store(
        "saved_pages",
        "Saved pages",
        life_service.load_saved_pages,
        life_service.save_saved_pages,
        frozenset({"created_at"}),
    ),
    StoreAdapter(
        key="planner",
        label="Weekly planner",
        load=_plan_records,
        replace=_replace_plan_records,
        ignore=PLAN_IGNORE,
        duplicate=lambda base_dir, row: _duplicate_plan_record(str(row.get("_kind", "item")))(base_dir, row),
    ),
    StoreAdapter(
        key="cards",
        label="Flashcard deck",
        load=flashcard_service.load_cards,
        replace=lambda base_dir, rows: flashcard_service.save_cards(base_dir, [_cell(row) for row in rows]),
        # A card edited on both machines is a scheduling question, not a text
        # one: duplicating it would put the same question in the deck twice.
        keep_both_on_conflict=False,
    ),
    _list_store("links", "Entity links", link_service.load_links, link_service.save_links),
    StoreAdapter(
        key="notes",
        label="Notes",
        load=_note_records,
        replace=_replace_notes,
        ignore=frozenset({"updated_at"}),
        duplicate=_duplicate_note,
    ),
)

ADAPTERS_BY_KEY = {adapter.key: adapter for adapter in ADAPTERS}


# --------------------------------------------------------------------------- #
# Folder + state
# --------------------------------------------------------------------------- #
def get_folder(base_dir: str) -> str:
    """The chosen sync folder (empty when folder sync is off)."""
    return str(prefs.get_pref(base_dir, FOLDER_PREF, "") or "").strip()


def set_folder(base_dir: str, folder: str) -> dict:
    """Remember the folder (creating it when it does not exist yet)."""
    path = (folder or "").strip()
    if path:
        os.makedirs(path, exist_ok=True)
    prefs.save_pref(base_dir, FOLDER_PREF, path)
    return status(base_dir)


def device_id(base_dir: str) -> str:
    """A stable id for this profile, so a payload can say which machine wrote it."""
    current = str(prefs.get_pref(base_dir, DEVICE_PREF, "") or "").strip()
    if current:
        return current
    fresh = uuid.uuid4().hex[:12]
    prefs.save_pref(base_dir, DEVICE_PREF, fresh)
    return fresh


def payload_path(base_dir: str) -> str:
    folder = get_folder(base_dir)
    return os.path.join(folder, PAYLOAD_NAME) if folder else ""


def state_path(base_dir: str) -> str:
    return os.path.join(base_dir, STATE_NAME)


def _load_state(base_dir: str) -> dict:
    raw = storage_utils.read_json(state_path(base_dir), {})
    if not isinstance(raw, dict) or str(raw.get("version", "")) != str(STATE_VERSION):
        return {"version": STATE_VERSION, "baseline": {}, "payload_id": "", "last_sync": ""}
    baseline = raw.get("baseline")
    raw["baseline"] = baseline if isinstance(baseline, dict) else {}
    return raw


def _save_state(base_dir: str, state: dict) -> None:
    storage_utils.write_json(state_path(base_dir), state)


def _hashes(rows: list[dict], ignore: frozenset) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        record_id = str(row.get("id", "") or "").strip()
        if not record_id:
            continue
        result[record_id] = _hash_record(row, ignore)
    return result


def _local_rows(base_dir: str, adapter: StoreAdapter) -> list[dict]:
    rows = adapter.load(base_dir) or []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def read_payload(base_dir: str) -> dict:
    """Read the shared payload; raises ``SyncFormatError`` when it is not ours."""
    path = payload_path(base_dir)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError, UnicodeError) as exc:
        raise SyncFormatError(f"The sync file could not be read ({exc}). Nothing was changed.") from exc
    if not isinstance(data, dict) or data.get("kind") != PAYLOAD_KIND:
        raise SyncFormatError("That file is not a Mei sync file. Nothing was changed.")
    try:
        version = int(data.get("version", 0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise SyncFormatError("Invalid sync schema version. Nothing was changed.") from exc
    if version > PAYLOAD_VERSION:
        raise SyncFormatError("That sync file was written by a newer Mei. Update before syncing.")
    if version < 1:
        raise SyncFormatError("Invalid sync schema version. Nothing was changed.")
    stores = data.get("stores")
    data["stores"] = stores if isinstance(stores, dict) else {}
    data["payload_id"] = str(data.get("payload_id") or "")
    return data


class SyncFormatError(RuntimeError):
    """The shared file is not a Mei payload we can trust."""


def _remote_store(payload: dict, adapter: StoreAdapter) -> tuple[dict[str, dict], dict[str, str]]:
    """``({id: record}, {id: hash})`` for one store out of a payload."""
    store = payload.get("stores", {}).get(adapter.key, {})
    records = store.get("records") if isinstance(store, dict) else None
    records = records if isinstance(records, dict) else {}
    clean: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    for record_id, row in records.items():
        if not isinstance(row, dict):
            continue
        clean[str(record_id)] = row
        hashes[str(record_id)] = str(row.get("_hash") or "") or _hash_record(row, adapter.ignore)
    return clean, hashes


# --------------------------------------------------------------------------- #
# The merge
# --------------------------------------------------------------------------- #
def _decide(local: str | None, remote: str | None, baseline: str | None) -> str:
    """One record's fate: ``keep`` | ``take_remote`` | ``delete_local`` |
    ``delete_remote`` | ``conflict`` | ``conflict_resurrect`` |
    ``conflict_keep_local`` | ``nothing``."""
    if local == remote:
        return "nothing"
    if local is None:
        if remote is None:
            return "nothing"
        if baseline is None:
            return "take_remote"  # added on the other machine, never seen here
        if remote == baseline:
            return "delete_remote"  # deleted here, untouched there: a tombstone
        return "conflict_resurrect"  # deleted here, edited there: the edit wins
    if remote is None:
        if baseline is None:
            return "keep"
        if local == baseline:
            return "delete_local"
        return "conflict_keep_local"
    if local == baseline:
        return "take_remote"
    if remote == baseline:
        return "keep"
    return "conflict"


def _merge_store(base_dir: str, adapter: StoreAdapter, payload: dict, baseline: dict) -> dict:
    """Classify one store and return the desired rows plus the change report."""
    local_rows = _local_rows(base_dir, adapter)
    local_by_id = {str(row["id"]): row for row in local_rows}
    remote_records, remote_hashes = _remote_store(payload, adapter)
    local_hashes = _hashes(local_rows, adapter.ignore)
    old_baseline = baseline.get(adapter.key)
    old_baseline = old_baseline if isinstance(old_baseline, dict) else {}

    desired: dict[str, dict] = dict(local_by_id)
    changes: list[dict] = []
    counts = {"added": 0, "updated": 0, "deleted": 0, "conflicts": 0, "kept": 0}

    for record_id in sorted(set(local_hashes) | set(remote_hashes) | set(old_baseline)):
        local_hash = local_hashes.get(record_id)
        remote_hash = remote_hashes.get(record_id)
        verdict = _decide(local_hash, remote_hash, old_baseline.get(record_id))

        if verdict == "nothing":
            continue
        if verdict == "keep":
            counts["kept"] += 1
            continue
        if verdict == "take_remote":
            row = dict(remote_records.get(record_id) or {})
            if not row:
                continue
            row["id"] = record_id
            action = "added" if local_hash is None else "updated"
            desired[record_id] = row
            counts[action] += 1
            changes.append(_change(adapter, record_id, action, row))
            continue
        if verdict == "delete_local":
            desired.pop(record_id, None)
            counts["deleted"] += 1
            changes.append(_change(adapter, record_id, "deleted", local_by_id.get(record_id) or {}))
            continue
        if verdict == "delete_remote":
            # Gone here, unchanged there: publish a tombstone by leaving it out of
            # the outgoing payload (the baseline still remembers it).
            counts["deleted"] += 1
            changes.append(_change(adapter, record_id, "deleted", local_by_id.get(record_id) or {}))
            continue
        if verdict == "conflict_resurrect":
            # Deleted on this machine, edited on the other: the edit comes back
            # and the user is told, instead of the delete silently winning.
            row = dict(remote_records.get(record_id) or {})
            if row:
                row["id"] = record_id
                desired[record_id] = row
            counts["conflicts"] += 1
            changes.append(
                _change(
                    adapter,
                    record_id,
                    "conflict",
                    row or local_by_id.get(record_id) or {},
                    note="deleted on one machine and edited on the other — the edit was kept",
                )
            )
            continue

        # Conflicts: nobody's edit is dropped.
        counts["conflicts"] += 1
        remote_row = dict(remote_records.get(record_id) or {})
        local_row = local_by_id.get(record_id) or {}
        if local_hash is None or remote_hash is None:
            # One side deleted the record, the other edited it: the edit wins and
            # is published again, so a delete can never eat a later edit.
            if remote_row:
                remote_row["id"] = record_id
                desired[record_id] = remote_row
            kept = remote_row or local_row
            changes.append(
                _change(
                    adapter,
                    record_id,
                    "conflict",
                    kept,
                    note="deleted on one machine and edited on the other — the edit was kept",
                )
            )
        elif adapter.keep_both_on_conflict and adapter.duplicate is not None:
            if remote_row:
                remote_row["id"] = record_id
                copy = adapter.duplicate(base_dir, remote_row)
                if copy:
                    desired[str(copy.get("id", ""))] = dict(copy)
                changes.append(
                    _change(
                        adapter,
                        record_id,
                        "conflict",
                        remote_row,
                        note="kept both: the other machine's version was added as a new record",
                    )
                )
        else:
            changes.append(
                _change(adapter, record_id, "conflict", remote_row or local_row, note="kept the copy on this machine")
            )

    rows = list(desired.values())
    return {"rows": rows, "changes": changes, "counts": counts, "adapter": adapter}


def _change(adapter: StoreAdapter, record_id: str, action: str, row: dict, note: str = "") -> dict:
    return {
        "store": adapter.key,
        "store_label": adapter.label,
        "id": record_id,
        "action": action,
        "title": _title_of(row) or record_id,
        "note": note,
    }


def _title_of(row: dict) -> str:
    for key in ("title", "front", "name", "label", "url"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return ""


def compute(base_dir: str) -> dict:
    """Work out the merge (reads everything, writes nothing)."""
    folder = get_folder(base_dir)
    if not folder:
        return {"enabled": False, "changes": [], "summary": {}, "warnings": [], "folder": ""}
    payload = read_payload(base_dir)
    state = _load_state(base_dir)
    baseline = state.get("baseline") if isinstance(state.get("baseline"), dict) else {}
    merged: dict[str, dict] = {}
    changes: list[dict] = []
    summary: dict[str, dict] = {}
    for adapter in ADAPTERS:
        result = _merge_store(base_dir, adapter, payload, baseline)
        merged[adapter.key] = result
        changes.extend(result["changes"])
        summary[adapter.key] = {
            "label": adapter.label,
            **result["counts"],
            "total": len(result["rows"]),
        }
    return {
        "enabled": True,
        "applied": False,
        "folder": folder,
        "payload": payload,
        "merged": merged,
        "changes": changes,
        "summary": summary,
        "warnings": _warnings(base_dir, folder, payload, state),
        "same_writer": bool(payload.get("device") and payload.get("device") == device_id(base_dir)),
    }


def _warnings(base_dir: str, folder: str, payload: dict, state: dict) -> list[str]:
    notes: list[str] = []
    lowered = folder.lower()
    if any(hint in lowered for hint in CLOUD_HINTS):
        notes.append(
            "That folder looks like a cloud drive that syncs whole files: Mei writes the sync file "
            "atomically, but a client may still be uploading it mid-write on the other machine."
        )
    try:
        if os.path.abspath(folder).startswith(os.path.abspath(base_dir) + os.sep):
            notes.append("The sync folder is inside this profile — pick a folder outside it, or the two copies are the same copy.")
    except OSError:
        pass
    if payload and not payload.get("stores"):
        notes.append("The sync file exists but is empty: it will be filled from this machine on the next sync.")
    generated = str(payload.get("generated_at") or "")
    last = str(state.get("last_sync") or "")
    if generated and last and generated > last:
        notes.append(f"The other machine last wrote this file at {generated}.")
    return notes


def _snapshot(base_dir: str, keys: tuple[str, ...]) -> str:
    """Copy the affected stores into ``<profile>/backups/sync-<stamp>/``."""
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    target = os.path.join(base_dir, BACKUP_DIRNAME, f"{BACKUP_PREFIX}{stamp}")
    os.makedirs(target, exist_ok=True)
    for key in keys:
        adapter = ADAPTERS_BY_KEY.get(key)
        if adapter is None:
            continue
        rows = _local_rows(base_dir, adapter)
        with open(os.path.join(target, f"{key}.json"), "w", encoding="utf-8") as handle:
            json.dump({"store": key, "records": rows}, handle, ensure_ascii=False, indent=2)
    return target


def _build_payload(base_dir: str, stores: dict[str, list[dict]]) -> dict:
    out: dict[str, Any] = {}
    for adapter in ADAPTERS:
        rows = stores.get(adapter.key, [])
        records: dict[str, dict] = {}
        for row in rows:
            record_id = str(row.get("id", "") or "").strip()
            if not record_id:
                continue
            published = _cell(row, adapter.ignore)
            published["_hash"] = _hash_record(row, adapter.ignore)
            records[record_id] = published
        out[adapter.key] = {"records": records}
    payload_id = uuid.uuid4().hex[:16]
    return {
        "kind": PAYLOAD_KIND,
        "version": PAYLOAD_VERSION,
        "product": "mei",
        "payload_id": payload_id,
        "device": device_id(base_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stores": out,
    }


def _stores_differ(left: dict, right: dict) -> bool:
    """Whether two payload ``stores`` sections really differ.

    The shared file is only replaced when there is something new to say — a sync
    that found nothing must leave the file's bytes (and its timestamp) alone, or
    two machines in a row would rewrite it forever just to say "nothing".
    """
    left_text = json.dumps(left or {}, sort_keys=True, ensure_ascii=False, default=str)
    right_text = json.dumps(right or {}, sort_keys=True, ensure_ascii=False, default=str)
    return left_text != right_text


def _write_payload(base_dir: str, payload: dict) -> bool:
    """Write the shared file atomically (temp file beside it, then replace)."""
    path = payload_path(base_dir)
    if not path:
        return False
    storage_utils.write_json(path, payload)
    return True


@profile_transaction
def sync(base_dir: str, apply: bool = True) -> dict:
    """Merge with the folder (``apply=False`` is exactly ``preview``).

    With ``apply`` the affected stores are snapshotted first, the merged rows are
    written through each store's own writer, the shared file is replaced, and the
    baseline is rebuilt from what the stores actually hold afterwards — so a note
    that had to be created under a different file name is not re-published on
    every sync.
    """
    plan = compute(base_dir)
    if not plan.get("enabled"):
        return {**plan, "applied": False, "reason": "no-folder"}
    if not apply:
        return {**plan, "applied": False}

    touched = tuple(adapter.key for adapter in ADAPTERS if plan["merged"][adapter.key]["changes"])
    # A snapshot is taken only when a store is about to be written: a sync that
    # only publishes must not litter the profile with identical backups.
    snapshot = _snapshot(base_dir, touched) if touched else ""

    written: dict[str, int] = {}
    for adapter in ADAPTERS:
        if adapter.key not in touched:
            continue
        rows = plan["merged"][adapter.key]["rows"]
        if len(rows) > MAX_RECORDS_PER_STORE:
            raise SyncFormatError(f"{adapter.label} holds more rows than folder sync will write.")
        adapter.replace(base_dir, rows)
        written[adapter.key] = len(rows)

    # The baseline is rebuilt from what the stores hold *now* — after the writes —
    # so a record whose file had to be created under another name (a note) is not
    # re-published on every sync, and the outgoing payload is the merged truth.
    actual = {adapter.key: _local_rows(base_dir, adapter) for adapter in ADAPTERS}
    outgoing = _build_payload(base_dir, actual)
    existing = plan.get("payload") or {}
    published = _stores_differ(outgoing.get("stores", {}), existing.get("stores", {}))
    stored = _write_payload(base_dir, outgoing) if published else False
    if published and not stored:
        # Never acknowledge unpublished edits as a shared baseline: doing so
        # makes the next run interpret them as deletions by the other device.
        raise OSError("Could not publish the sync file; your edits remain local and can be retried")
    did_something = bool(touched) or stored
    _save_state(
        base_dir,
        {
            "version": STATE_VERSION,
            "baseline": {adapter.key: _hashes(actual[adapter.key], adapter.ignore) for adapter in ADAPTERS},
            "payload_id": outgoing["payload_id"] if stored else str(existing.get("payload_id") or ""),
            "last_sync": outgoing["generated_at"] if stored else str(existing.get("generated_at") or ""),
        },
    )
    return {
        **plan,
        "applied": did_something,
        "reason": "" if did_something else "nothing-new",
        "snapshot": snapshot,
        "written": written,
        "payload_written": stored,
        "payload_id": outgoing["payload_id"] if stored else str(existing.get("payload_id") or ""),
    }


def status(base_dir: str) -> dict:
    """What the Settings card needs to say, without merging anything."""
    folder = get_folder(base_dir)
    state = _load_state(base_dir)
    baseline = state.get("baseline") if isinstance(state.get("baseline"), dict) else {}
    tracked = sum(len(store) for store in baseline.values() if isinstance(store, dict))
    exists = bool(folder) and os.path.isdir(folder)
    payload_exists = bool(folder) and os.path.isfile(payload_path(base_dir))
    return {
        "enabled": bool(folder),
        "folder": folder,
        "folder_exists": exists,
        "payload_exists": payload_exists,
        "last_sync": str(state.get("last_sync") or ""),
        "tracked_records": tracked,
        "device": device_id(base_dir) if folder else "",
        "stores": [{"key": adapter.key, "label": adapter.label} for adapter in ADAPTERS],
    }


def summary_line(report: dict) -> str:
    """One line for the status strip / dialog: what a sync just did."""
    if not report.get("enabled"):
        return "Folder sync is off — pick a folder in Settings to keep two machines in step."
    totals = {"added": 0, "updated": 0, "deleted": 0, "conflicts": 0}
    for counts in (report.get("summary") or {}).values():
        for key in totals:
            totals[key] += int(counts.get(key, 0) or 0)
    if not any(totals.values()):
        return "Already in step — nothing to merge." if report.get("applied") else "Nothing to merge."
    parts = [f"{value} {name}" for name, value in totals.items() if value]
    head = "Synced" if report.get("applied") else "Would sync"
    line = f"{head}: " + ", ".join(parts)
    if totals["conflicts"]:
        line += " — conflicts kept both copies"
    return line


__all__ = [
    "ADAPTERS",
    "ADAPTERS_BY_KEY",
    "PAYLOAD_NAME",
    "STATE_NAME",
    "StoreAdapter",
    "SyncFormatError",
    "VOLATILE_KEYS",
    "compute",
    "device_id",
    "get_folder",
    "payload_path",
    "read_payload",
    "set_folder",
    "state_path",
    "status",
    "summary_line",
    "sync",
]
