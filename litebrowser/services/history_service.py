import base64
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile

from litebrowser.core import app_paths, prefs
from litebrowser.core.profile_lock import profile_locked, profile_transaction
from litebrowser.core.storage_utils import _atomic_replace, read_json, safe_child_path, write_json, write_text_atomic
from litebrowser.core.log import get_logger

_log = get_logger("history_service")
from litebrowser.services import tab_sets, workspace_manager


def activity_path(base_dir: str) -> str:
    return os.path.join(base_dir, "activity_history.json")


def load_activity(base_dir: str):
    data = read_json(activity_path(base_dir), {"version": 1, "events": []})
    if not isinstance(data, dict):
        return {"version": 1, "events": []}
    data.setdefault("version", 1)
    events = data.get("events")
    data["events"] = [event for event in events if isinstance(event, dict)] if isinstance(events, list) else []
    return data


def save_activity(base_dir: str, data):
    payload = dict(data or {})
    payload.setdefault("version", 1)
    payload.setdefault("events", [])
    with profile_locked(base_dir):
        write_json(activity_path(base_dir), payload)


@profile_transaction
def clear_activity(base_dir: str) -> int:
    """Delete every activity record; returns how many events were removed."""
    removed = len(load_activity(base_dir).get("events", []))
    save_activity(base_dir, {"version": 1, "events": []})
    return removed


def log_event(base_dir: str, kind: str, title: str, detail: str = "", meta: dict | None = None):
    with profile_locked(base_dir):
        data = load_activity(base_dir)
        events = data.get("events", [])
        now = int(time.time())
        event = {
            "id": uuid.uuid4().hex,
            "ts": now,
            "kind": (kind or "").strip() or "activity",
            "title": (title or "").strip(),
            "detail": (detail or "").strip(),
            "meta": meta if isinstance(meta, dict) else {},
        }
        # Consecutive-duplicate suppression: urlChanged fires for every
        # redirect, so identical browser-visit events within a 2 s window used
        # to each cost a full 3000-event rewrite (v6.5 audit).
        if events:
            first = events[0]
            if (
                first.get("kind") == event["kind"]
                and first.get("title") == event["title"]
                and first.get("detail") == event["detail"]
                and isinstance(first.get("ts"), (int, float))
                and 0 <= now - first["ts"] <= 2
            ):
                return first
        events.insert(0, event)
        data["events"] = events[:3000]
        payload = dict(data)
        payload.setdefault("version", 1)
        payload.setdefault("events", [])
        write_json(activity_path(base_dir), payload)
        return event


def list_activity(base_dir: str, query: str = "", kind: str = ""):
    query = (query or "").strip().lower()
    kind = (kind or "").strip().lower()
    events = load_activity(base_dir).get("events", [])
    out = []
    for item in events:
        if kind and (item.get("kind", "").lower() != kind):
            continue
        hay = "\n".join(
            [
                item.get("kind", ""),
                item.get("title", ""),
                item.get("detail", ""),
                " ".join(f"{k}:{v}" for k, v in (item.get("meta") or {}).items()),
            ]
        ).lower()
        if query and query not in hay:
            continue
        out.append(item)
    return out


PROFILE_ZIP_JSON_MEMBER = "profile.json"
PROFILE_ZIP_VAULT_PREFIX = "vault/"
PROFILE_ZIP_BROWSER_PREFIX = "BrowserData/"


def _export_vault_files_excluding_notes(base_dir: str) -> list:
    """All SafeVault files except under notes/ (notes are in the notes[] export key)."""
    vault = prefs.vault_path(base_dir)
    out = []
    if not os.path.isdir(vault):
        return out
    notes_prefix = "notes/"
    for root, _, files in os.walk(vault):
        for fn in files:
            abspath = os.path.join(root, fn)
            rel = os.path.relpath(abspath, vault).replace("\\", "/")
            if rel == "notes" or rel.startswith(notes_prefix):
                continue
            try:
                size = os.path.getsize(abspath)
            except OSError:
                continue
            try:
                with open(abspath, "rb") as f:
                    raw = f.read()
            except OSError:
                continue
            entry: dict = {"path": rel, "size": size}
            try:
                entry["encoding"] = "utf-8"
                entry["text"] = raw.decode("utf-8")
            except UnicodeDecodeError:
                entry["encoding"] = "base64"
                entry["data"] = base64.standard_b64encode(raw).decode("ascii")
            out.append(entry)
    return out


def _import_vault_files(base_dir: str, entries) -> None:
    if not isinstance(entries, list):
        return
    vault = prefs.vault_path(base_dir)
    os.makedirs(vault, exist_ok=True)
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        rel = (ent.get("path") or "").replace("\\", "/").strip().lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        if rel == "notes" or rel.startswith("notes/"):
            continue
        if ent.get("skipped_large"):
            continue
        dest = safe_child_path(vault, rel)
        if not dest:
            raise ValueError("Unsafe vault path in backup")
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if ent.get("encoding") == "base64" and isinstance(ent.get("data"), str):
            try:
                raw = base64.b64decode(ent["data"].encode("ascii"), validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid vault data in backup") from exc
            try:
                with open(dest, "wb") as f:
                    f.write(raw)
            except OSError:
                raise
        elif ent.get("encoding") == "utf-8" and "text" in ent:
            try:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(str(ent.get("text") or ""))
            except OSError:
                raise


def _add_vault_tree_to_zip(zf: zipfile.ZipFile, base_dir: str) -> None:
    """Append SafeVault files (except notes/) into zip under vault/."""
    vault = prefs.vault_path(base_dir)
    notes_prefix = "notes/"
    if not os.path.isdir(vault):
        return
    for root, _, files in os.walk(vault):
        for fn in files:
            abspath = os.path.join(root, fn)
            rel = os.path.relpath(abspath, vault).replace("\\", "/")
            if rel == "notes" or rel.startswith(notes_prefix):
                continue
            arcname = PROFILE_ZIP_VAULT_PREFIX + rel
            try:
                zf.write(abspath, arcname)
            except OSError:
                continue


def _import_vault_from_zip(base_dir: str, zf: zipfile.ZipFile) -> None:
    """Extract vault/* from bundle into SafeVault (skips notes/)."""
    vault = prefs.vault_path(base_dir)
    vault_abs = os.path.abspath(vault)
    os.makedirs(vault_abs, exist_ok=True)
    prefix = PROFILE_ZIP_VAULT_PREFIX
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix) :].lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        if rel == "notes" or rel.startswith("notes/"):
            continue
        dest = safe_child_path(vault_abs, rel)
        if not dest:
            raise ValueError("Unsafe vault path in backup")
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            with zf.open(info, "r") as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        except OSError:
            raise


def _add_browser_data_to_zip(zf: zipfile.ZipFile, base_dir: str) -> None:
    """Append WebEngine profile dir as BrowserData/... (can be very large)."""
    bd = app_paths.browser_data_path(base_dir)
    if not os.path.isdir(bd):
        return
    prefix = PROFILE_ZIP_BROWSER_PREFIX
    for root, _, files in os.walk(bd):
        for fn in files:
            abspath = os.path.join(root, fn)
            rel = os.path.relpath(abspath, bd).replace("\\", "/")
            if not rel or ".." in rel.split("/"):
                continue
            arcname = prefix + rel
            try:
                zf.write(abspath, arcname)
            except OSError:
                continue


def _zip_contains_browser_data(zf: zipfile.ZipFile) -> bool:
    pfx = PROFILE_ZIP_BROWSER_PREFIX
    for n in zf.namelist():
        n = n.replace("\\", "/")
        if n.endswith("/"):
            continue
        if n.startswith(pfx) and n != pfx:
            return True
    return False


def _import_browser_data_from_zip(base_dir: str, zf: zipfile.ZipFile) -> bool:
    """Restore BrowserData from a ZIP without risking the live profile.

    Extraction is staged beside the target.  The prior tree is retained until
    the staged tree has been moved into place, then restored if that move
    fails.  This matters on Windows where a WebEngine process or antivirus
    scanner can briefly reject a directory rename.
    """
    if not _zip_contains_browser_data(zf):
        return False
    bd = app_paths.browser_data_path(base_dir)
    bd_abs = os.path.abspath(bd)
    parent = os.path.dirname(bd_abs)

    # A unique staging directory avoids deleting a previous recovery artifact
    # if an earlier import was interrupted midway through its rollback.
    staging = tempfile.mkdtemp(prefix=f".{os.path.basename(bd_abs)}.import-", dir=parent)
    staging_abs = os.path.abspath(staging)
    prefix = PROFILE_ZIP_BROWSER_PREFIX
    wrote = False
    try:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix) :].lstrip("/")
            if not rel or ".." in rel.split("/"):
                continue
            dest = os.path.normpath(os.path.join(staging, *rel.split("/")))
            dest_abs = os.path.abspath(dest)
            if dest_abs != staging_abs and not dest_abs.startswith(staging_abs + os.sep):
                continue
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            try:
                with zf.open(info, "r") as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                wrote = True
            except OSError:
                return False
        if not wrote:
            return False

        # Extraction succeeded: move the old profile aside, then swap in the
        # staging tree.  Never discard the old data until the new tree exists
        # at its final path.
        if os.path.isdir(bd_abs):
            retired = f"{bd_abs}.import-old-{uuid.uuid4().hex}"
            try:
                os.replace(bd_abs, retired)
            except OSError:
                return False
            try:
                os.replace(staging, bd_abs)
            except OSError:
                # Roll back before returning: a failed import must leave the
                # original browser profile (cookies, sessions, extensions)
                # usable rather than stranded in a hidden recovery directory.
                try:
                    os.replace(retired, bd_abs)
                except OSError:
                    # Preserve the retired tree for manual recovery if the
                    # rollback itself is blocked by another process.
                    pass
                return False
            shutil.rmtree(retired, ignore_errors=True)
        else:
            try:
                os.replace(staging, bd_abs)
            except OSError:
                return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return wrote


def export_profile_to_zip(base_dir: str, zip_path: str, *, include_browser_data: bool = False) -> bool:
    """
    Write profile backup as ZIP: profile.json (structured data, no inlined vault blobs)
    + vault/ tree (all SafeVault files except notes/).
    Optionally + BrowserData/ (WebEngine: cache, localStorage, extension state, etc.).
    """
    temp_path = ""
    try:
        parent = os.path.dirname(os.path.abspath(zip_path))
        handle, temp_path = tempfile.mkstemp(prefix=".mei-backup-", suffix=".zip", dir=parent)
        os.close(handle)
        payload = export_profile_payload(base_dir, inline_vault_files=False)
        payload["backup_format_version"] = 4
        payload["backup_bundle"] = "zip"
        payload["backup_includes_browser_data"] = bool(include_browser_data)
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                PROFILE_ZIP_JSON_MEMBER,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            _add_vault_tree_to_zip(zf, base_dir)
            if include_browser_data:
                _add_browser_data_to_zip(zf, base_dir)
        _atomic_replace(temp_path, zip_path)
        return True
    except (OSError, ValueError):
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def import_profile_from_path(base_dir: str, file_path: str) -> bool:
    """Import from .zip (profile.json + vault/) or legacy .json file."""
    if not file_path or not os.path.isfile(file_path):
        return False
    lower = file_path.lower()
    if lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                infos = zf.infolist()
                if len(infos) > 20_000 or sum(info.file_size for info in infos) > 2 * 1024 ** 3:
                    return False
                for info in infos:
                    if info.file_size > 512 * 1024 ** 2 or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        return False
                    if not info.is_dir() and not safe_child_path(base_dir, info.filename):
                        return False
                if zf.getinfo(PROFILE_ZIP_JSON_MEMBER).file_size > 64 * 1024 ** 2:
                    return False
                try:
                    raw = zf.read(PROFILE_ZIP_JSON_MEMBER)
                except KeyError:
                    return False
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    return False
                return import_profile_payload(base_dir, payload, vault_zip=zf, import_browser_data=True)
        except (ValueError, UnicodeError, OSError, KeyError, zipfile.BadZipFile):
            return False
    payload = read_json(file_path, None)
    return import_profile_payload(base_dir, payload)


def _clear_notes_directory(notes_dir: str) -> None:
    if not os.path.isdir(notes_dir):
        return
    for name in os.listdir(notes_dir):
        path = os.path.join(notes_dir, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


@profile_transaction
def export_profile_payload(base_dir: str, *, inline_vault_files: bool = True):
    from litebrowser.services import (
        download_mgr,
        extension_bridge,
        flashcard_service,
        life_service,
        link_service,
        personal_plan,
        personal_service,
    )

    notes = []
    for note in personal_service.list_notes(base_dir):
        notes.append({"id": note["id"], "title": note["title"], "content": note.get("content", "")})
    payload = {
        "version": 1,
        "backup_format_version": 3,
        "exported_at": int(time.time()),
        "profile_meta": prefs.load_profile_meta(base_dir),
        "prefs": prefs.load_prefs(base_dir),
        "history_entries": prefs.load_history_entries(base_dir),
        "bookmarks": prefs.load_bookmarks(base_dir),
        "session": prefs.session_load(base_dir),
        "session_state": prefs.session_state_load(base_dir),
        "workspaces": workspace_manager.load(base_dir),
        "permissions": prefs.load_permissions(base_dir),
        "downloads": download_mgr.load_list(base_dir),
        "tab_sets": tab_sets.load_tab_sets(base_dir),
        "tasks": life_service.load_tasks(base_dir),
        "calendar": life_service.load_events(base_dir),
        "boards": life_service.load_boards(base_dir),
        "saved_pages": life_service.load_saved_pages(base_dir),
        "sync_state": life_service.load_sync_state(base_dir),
        "sync_account": life_service.load_sync_account(base_dir),
        "ai_settings": prefs.load_ai_settings(base_dir),
        "ai_index": read_json(prefs.ai_index_path(base_dir), {"version": 1, "built_at": 0, "docs": []}),
        "activity_history": load_activity(base_dir),
        "notes": notes,
        "personal_plan": personal_plan.load_plan(base_dir),
        "flashcards": flashcard_service.load_cards(base_dir),
        "focus_sessions": read_json(os.path.join(base_dir, "focus_sessions.json"), {"active": None, "sessions": []}),
        "bookmark_folders": prefs.load_bookmark_folders(base_dir),
        "entity_links": link_service.load_links(base_dir),
        "extension_imports": read_json(
            extension_bridge.storage_path(base_dir),
            {"version": 1, "batches": []},
        ),
        "vault_files": _export_vault_files_excluding_notes(base_dir) if inline_vault_files else [],
    }
    return payload


def import_profile_payload(
    base_dir: str,
    payload: dict,
    vault_zip: zipfile.ZipFile | None = None,
    *,
    import_browser_data: bool = False,
):
    """Restore only supplied collections, staging files before any live write.

    Older/sparse backups cannot erase absent stores. Failed writes roll back
    the stores and vault; a failed rollback retains its recovery directory.
    """
    from litebrowser.services import (
        download_mgr, extension_bridge, flashcard_service, life_service,
        link_service, personal_plan, personal_service,
    )

    writers = {
        "prefs": (dict, prefs._prefs_path(base_dir), prefs.save_prefs),
        "profile_meta": (dict, prefs.profile_meta_path(base_dir), lambda b, v: write_json(prefs.profile_meta_path(b), v)),
        "history_entries": (list, prefs.history_path(base_dir), prefs.save_history_entries),
        "bookmarks": (list, prefs.bookmarks_path(base_dir), prefs.save_bookmarks),
        "bookmark_folders": (list, prefs.bookmark_folders_path(base_dir), prefs.save_bookmark_folders),
        "session": (list, prefs.session_path(base_dir), prefs.session_save),
        "session_state": (dict, prefs.session_path(base_dir), prefs.session_state_save),
        "workspaces": (dict, prefs.workspaces_path(base_dir), prefs.save_workspaces),
        "permissions": (dict, prefs.permissions_path(base_dir), prefs.save_permissions),
        "downloads": (list, prefs.downloads_list_path(base_dir), download_mgr.save_list),
        "tab_sets": (dict, os.path.join(base_dir, tab_sets.TAB_SETS_FILENAME), tab_sets.save_tab_sets),
        "tasks": (list, life_service.tasks_path(base_dir), life_service.save_tasks),
        "calendar": (list, life_service.calendar_path(base_dir), life_service.save_events),
        "boards": (list, life_service.boards_path(base_dir), life_service.save_boards),
        "saved_pages": (list, life_service.saved_pages_path(base_dir), life_service.save_saved_pages),
        "sync_state": (dict, life_service.sync_state_path(base_dir), life_service.save_sync_state),
        "sync_account": (dict, life_service.sync_account_path(base_dir), lambda b, v: write_json(life_service.sync_account_path(b), v)),
        "ai_settings": (dict, prefs.ai_settings_path(base_dir), prefs.save_ai_settings),
        "ai_index": (dict, prefs.ai_index_path(base_dir), lambda b, v: write_json(prefs.ai_index_path(b), v)),
        "activity_history": (dict, activity_path(base_dir), save_activity),
        "personal_plan": (dict, personal_plan.plan_path(base_dir), personal_plan.save_plan),
        "flashcards": (list, flashcard_service.cards_path(base_dir), flashcard_service.save_cards),
        "entity_links": (list, os.path.join(base_dir, link_service.LINK_FILENAME), link_service.save_links),
        "focus_sessions": (dict, os.path.join(base_dir, "focus_sessions.json"), lambda b, v: write_json(os.path.join(b, "focus_sessions.json"), v)),
    }
    if not isinstance(payload, dict) or not any(key in payload for key in (*writers, "notes", "vault_files", "extension_imports")):
        return False
    for key, (expected, _path, _writer) in writers.items():
        if key in payload and not isinstance(payload[key], expected):
            return False
    for key in ("notes", "vault_files"):
        if key in payload and not isinstance(payload[key], list):
            return False
    valid_notes = []
    for note in payload.get("notes", []):
        if not isinstance(note, dict) or not isinstance(note.get("content", ""), str):
            return False
        note_id = note.get("id")
        if isinstance(note_id, str) and safe_child_path(os.path.join(base_dir, "SafeVault", "notes"), note_id):
            valid_notes.append((note_id, note.get("content", "")))
    if payload.get("notes") and not valid_notes:
        return False
    ext = payload.get("extension_imports")
    if ext is not None and not isinstance(ext, (dict, list)):
        return False

    with profile_locked(base_dir):
        recovery = ""
        vault = prefs.vault_path(base_dir)
        retired = ""
        swapped = False
        originals = {}
        rollback_ok = True
        try:
            prefs.ensure_profile_layout(base_dir)
            recovery = tempfile.mkdtemp(prefix=".mei-restore-", dir=base_dir)
            incoming = os.path.join(recovery, "incoming")
            incoming_vault = os.path.join(incoming, "SafeVault")
            vault_changed = "notes" in payload or bool(payload.get("vault_files")) or (vault_zip is not None and any(n.startswith(PROFILE_ZIP_VAULT_PREFIX) for n in vault_zip.namelist()))
            if vault_changed:
                if os.path.islink(vault) or not safe_child_path(base_dir, "SafeVault"):
                    raise OSError("Cannot restore through a linked vault")
                shutil.copytree(vault, incoming_vault, symlinks=True)
                if "notes" in payload:
                    staged_notes = os.path.join(incoming_vault, "notes")
                    if os.path.islink(staged_notes):
                        os.unlink(staged_notes)
                    elif os.path.isdir(staged_notes):
                        shutil.rmtree(staged_notes)
                    os.makedirs(staged_notes, exist_ok=True)
                    for note_id, content in valid_notes:
                        path = safe_child_path(staged_notes, note_id)
                        if not path:
                            raise ValueError("Unsafe note path")
                        write_text_atomic(path, content)
                if vault_zip is not None:
                    _import_vault_from_zip(incoming, vault_zip)
                else:
                    _import_vault_files(incoming, payload.get("vault_files", []))

            paths = {path for key, (_expected, path, _writer) in writers.items() if key in payload}
            if ext is not None:
                paths.add(extension_bridge.storage_path(base_dir))
            for path in paths:
                if os.path.isfile(path):
                    with open(path, "rb") as handle:
                        originals[path] = handle.read()
                else:
                    originals[path] = None
            # Keep recovery bytes on disk as well, in case rollback itself is
            # blocked by the filesystem. Never claim success on partial writes.
            for index, raw in enumerate(originals.values()):
                if raw is not None:
                    with open(os.path.join(recovery, f"store-{index}.bak"), "wb") as handle:
                        handle.write(raw)
            write_json(os.path.join(recovery, "recovery-map.json"), list(originals))
            for key, (_expected, _path, writer) in writers.items():
                if key in payload:
                    writer(base_dir, payload[key])
            if "workspaces" in payload:
                workspace_manager.ensure_dual_workspaces(base_dir)
            if ext is not None:
                batches = ext.get("batches", []) if isinstance(ext, dict) else ext
                if not isinstance(batches, list):
                    raise ValueError("Invalid extension import history")
                extension_bridge.save_batches(base_dir, batches)
            if vault_changed:
                retired = os.path.join(recovery, "original-vault")
                os.replace(vault, retired)
                os.replace(incoming_vault, vault)
                swapped = True
            if import_browser_data and vault_zip is not None and _zip_contains_browser_data(vault_zip):
                if not _import_browser_data_from_zip(base_dir, vault_zip):
                    raise OSError("Browser data is in use; close it before restoring")
            return True
        except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
            _log.warning("Profile restore failed (%s); rolling back", type(exc).__name__)
            try:
                if retired and os.path.isdir(retired):
                    if swapped:
                        shutil.rmtree(vault)
                    os.replace(retired, vault)
                for path, raw in originals.items():
                    if raw is None:
                        if os.path.isfile(path):
                            os.remove(path)
                    else:
                        # Existing JSON/text bytes were validated by the old
                        # app, not by this import; restore them verbatim.
                        write_text_atomic(path, raw.decode("utf-8"))
            except (OSError, UnicodeError):
                rollback_ok = False
                _log.error("Restore recovery retained at %s", recovery)
            return False
        finally:
            prefs._prefs_cache.pop(base_dir, None)
            prefs._prefs_copy_cache.pop(base_dir, None)
            personal_service._invalidate_cache()
            if recovery and rollback_ok:
                shutil.rmtree(recovery, ignore_errors=True)
