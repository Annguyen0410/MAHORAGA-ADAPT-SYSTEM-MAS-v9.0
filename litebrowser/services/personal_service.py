import copy
import os
import re
import time

from litebrowser.core import prefs
from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked
from litebrowser.core.storage_utils import safe_child_path, write_text_atomic
from litebrowser.services import history_service

_log = get_logger("personal_service")

NOTE_EXTENSIONS = (".md", ".txt")


class NoteConflictError(OSError):
    """A newer note exists on disk; keep the editor draft instead of overwriting."""

_cache = {"notes": None, "base_dir": "", "notes_time": 0, "notes_ttl": 2.0}


def _invalidate_cache():
    _cache["notes"] = None
    _cache["notes_time"] = 0
    # Note files are part of the AI index signature; any note mutation must
    # drop the cached signature so the next index check sees the change.
    from litebrowser.services import ai_service as _ai

    try:
        _ai.reset_index_signature_cache()
    except Exception as exc:  # noqa: BLE001  cache reset must never break a note edit
        _log.debug("index signature cache reset failed: %s", exc)


def _get_cached_notes(base_dir: str) -> list[dict[str, str]]:
    now = time.time()
    if _cache["notes"] is not None and _cache["base_dir"] == base_dir and (now - _cache["notes_time"]) < _cache["notes_ttl"]:
        return _cache["notes"]
    items = []
    with profile_locked(base_dir):
        for root, _dirs, files in os.walk(notes_dir(base_dir)):
            for fn in sorted(files):
                if not fn.lower().endswith(NOTE_EXTENSIONS):
                    continue
                path = _note_path(base_dir, os.path.relpath(os.path.join(root, fn), notes_dir(base_dir)))
                if not path:
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    record = _note_record_from_path(base_dir, path, text=text)
                    items.append(record)
                except (OSError, ValueError) as exc:
                    _log.warning("skipping unreadable note %s: %s", path, exc)
                    continue
    items.sort(key=lambda item: (-int(item["updated_at"]), item["title"].lower()))
    _cache["notes"] = items
    _cache["base_dir"] = base_dir
    _cache["notes_time"] = now
    return items
# Windows-forbidden filename characters only; keep Unicode (e.g. Vietnamese) in folder/title slugs.
_WIN_FORBIDDEN_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def notes_dir(base_dir: str) -> str:
    path = safe_child_path(base_dir, "SafeVault/notes")
    if not path:
        raise OSError("The notes folder must stay inside this profile")
    os.makedirs(path, exist_ok=True)
    return path


def _normalize_category(category: str) -> str:
    raw = (category or "").strip() or "General"
    raw = raw.replace("\\", "/").strip("/")
    parts = [_safe_name(part) for part in raw.split("/") if part.strip()]
    if not parts:
        return "General"
    return "/".join(parts[:4])


def _note_path(base_dir: str, note_id: str) -> str:
    return safe_child_path(notes_dir(base_dir), note_id)


def _note_record_from_path(base_dir: str, path: str, text: str | None = None):
    rel_id = os.path.relpath(path, notes_dir(base_dir))
    rel_id = rel_id.replace("/", os.sep)
    title = os.path.splitext(os.path.basename(rel_id))[0]
    category = os.path.dirname(rel_id).replace("\\", "/").strip("/") or "General"
    if text is None:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    return {
        "id": rel_id,
        "title": title,
        "category": category,
        "path": path,
        "snippet": text.strip().replace("\n", " ")[:200],
        "content": text,
        "updated_at": str(int(os.path.getmtime(path))),
    }


def _safe_name(title: str) -> str:
    raw = (title or "").strip() or "note"
    raw = _WIN_FORBIDDEN_NAME_RE.sub("-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip(" .") or "note"
    if len(raw) > 80:
        raw = raw[:80].rstrip(" .") or "note"
    if raw.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raw = "_" + raw
    return raw


def list_notes(base_dir: str, query: str = "") -> list[dict[str, str]]:
    q = (query or "").strip().lower()
    if q:
        items = _get_cached_notes(base_dir)
        return copy.deepcopy([it for it in items if q in f"{it['title']}\n{it['category']}\n{it['content']}".lower()])
    return copy.deepcopy(_get_cached_notes(base_dir))


def read_note(base_dir: str, note_id: str):
    with profile_locked(base_dir):
        path = _note_path(base_dir, note_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        record = _note_record_from_path(base_dir, path, text=content)
    return record


def create_note(base_dir: str, title: str, content: str = "", category: str = "General"):
    with profile_locked(base_dir):
        category_path = _normalize_category(category)
        folder = safe_child_path(notes_dir(base_dir), category_path)
        if not folder:
            raise OSError("The note category points outside this profile")
        os.makedirs(folder, exist_ok=True)
        note_id = os.path.join(*category_path.split("/"), _safe_name(title) + ".md")
        path = _note_path(base_dir, note_id)
        suffix = 2
        while os.path.exists(path):
            note_id = os.path.join(*category_path.split("/"), f"{_safe_name(title)}-{suffix}.md")
            path = _note_path(base_dir, note_id)
            suffix += 1
        write_text_atomic(path, content or "")
    _invalidate_cache()
    history_service.log_event(base_dir, "note", title, "Note created", {"note_id": note_id, "category": category_path})
    return read_note(base_dir, note_id)


def save_note(base_dir: str, note_id: str, content: str, *, expected_content: str | None = None) -> bool:
    with profile_locked(base_dir):
        path = _note_path(base_dir, note_id)
        if not path or not os.path.isfile(path):
            return False
        if expected_content is not None:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                current = handle.read()
            if current != expected_content and current != content:
                raise NoteConflictError("Another window or device updated this note. Your draft is retained; save it as a separate note.")
        write_text_atomic(path, content or "")
    _invalidate_cache()
    history_service.log_event(base_dir, "note", os.path.splitext(note_id)[0], "Note updated", {"note_id": note_id})
    return True


def update_note(base_dir: str, note_id: str, content: str, category: str | None = None):
    with profile_locked(base_dir):
        note = read_note(base_dir, note_id)
        if not note:
            return None
        target_category = _normalize_category(category or note.get("category") or "General")
        current_category = _normalize_category(note.get("category") or "General")
        original_id = note_id
        target_id = note_id
        if target_category != current_category:
            target_folder = safe_child_path(notes_dir(base_dir), target_category)
            if not target_folder:
                raise OSError("The note category points outside this profile")
            os.makedirs(target_folder, exist_ok=True)
            target_id = os.path.join(*target_category.split("/"), os.path.basename(note_id))
            target_path = _note_path(base_dir, target_id)
            if os.path.normcase(target_path) != os.path.normcase(_note_path(base_dir, note_id)):
                # A same-named note in the destination must never be clobbered
                # (v6.4 silently os.replace'd over it — data loss). Suffix like
                # create_note does.
                if os.path.exists(target_path):
                    stem = os.path.splitext(os.path.basename(note_id))[0]
                    suffix = 2
                    while True:
                        target_id = os.path.join(*target_category.split("/"), f"{stem}-{suffix}.md")
                        target_path = _note_path(base_dir, target_id)
                        if not os.path.exists(target_path):
                            break
                        suffix += 1
                from litebrowser.services import flashcard_service, link_service

                # Keep the source until its replacement and all references are
                # durable. A failed move must leave the original note usable.
                old_links = link_service.load_links(base_dir)
                old_cards = flashcard_service.load_cards(base_dir)
                old_order = prefs.get_note_order(base_dir)
                links = copy.deepcopy(old_links)
                cards = copy.deepcopy(old_cards)
                for link in links:
                    for side in ("from", "to"):
                        if link.get(f"{side}_type") == "note" and link.get(f"{side}_id") == original_id:
                            link[f"{side}_id"] = target_id
                for card in cards:
                    if card.get("source_note_id") == original_id:
                        card["source_note_id"] = target_id
                # Snapshot raw reference files so rollback preserves unknown
                # fields and timestamps, not just normalized service records.
                snapshots = {}
                for reference_name in ("entity_links.json", "flashcards.json", "prefs.json"):
                    reference_path = os.path.join(base_dir, reference_name)
                    if os.path.isfile(reference_path):
                        with open(reference_path, "r", encoding="utf-8", newline="") as handle:
                            snapshots[reference_path] = handle.read()
                    else:
                        snapshots[reference_path] = None
                write_text_atomic(target_path, content or "")
                changed_links = changed_cards = changed_order = False
                try:
                    if links != old_links:
                        link_service.save_links(base_dir, links)
                        changed_links = True
                    if cards != old_cards:
                        flashcard_service.save_cards(base_dir, cards)
                        changed_cards = True
                    if original_id in old_order:
                        prefs.set_note_order(base_dir, [target_id if value == original_id else value for value in old_order])
                        changed_order = True
                    os.remove(_note_path(base_dir, original_id))
                except (OSError, ValueError, TypeError) as exc:
                    rollback_errors = []
                    changed = (changed_links, changed_cards, changed_order)
                    for (reference_path, previous), touched in zip(snapshots.items(), changed):
                        if not touched:
                            continue
                        try:
                            if previous is None:
                                if os.path.exists(reference_path):
                                    os.remove(reference_path)
                            else:
                                write_text_atomic(reference_path, previous)
                        except OSError as rollback_exc:
                            rollback_errors.append(str(rollback_exc))
                    if rollback_errors:
                        # Keep both note files if a reference could not roll back:
                        # neither the old nor the new edge becomes a missing note.
                        _invalidate_cache()
                        raise OSError("Note move failed; both note copies were retained because reference rollback failed: " + "; ".join(rollback_errors)) from exc
                    os.remove(target_path)
                    _invalidate_cache()
                    raise
                note_id = target_id
        if note_id == original_id:
            path = _note_path(base_dir, note_id)
            if not os.path.isfile(path):
                return None
            write_text_atomic(path, content or "")
    _invalidate_cache()
    history_service.log_event(base_dir, "note", os.path.splitext(note_id)[0], "Note updated", {"note_id": note_id})
    return read_note(base_dir, note_id)


def delete_note(base_dir: str, note_id: str) -> bool:
    from litebrowser.services import link_service

    with profile_locked(base_dir):
        path = _note_path(base_dir, note_id)
        if not os.path.isfile(path):
            return False
        os.remove(path)
    # The note is gone; edges that point at it would render as dead titles.
    link_service.delete_links_for(base_dir, "note", note_id)
    _invalidate_cache()
    history_service.log_event(base_dir, "note", os.path.splitext(note_id)[0], "Note deleted", {"note_id": note_id})
    return True


def list_note_categories(base_dir: str) -> list[str]:
    categories = {"General"}
    for item in _get_cached_notes(base_dir):
        categories.add(item.get("category") or "General")
    return sorted(categories, key=lambda value: value.lower())


def list_root_entries(base_dir: str, query: str = "") -> list[dict[str, str]]:
    root = prefs.get_personal_root(base_dir) or ""
    if not root or not os.path.isdir(root):
        return []
    q = (query or "").strip().lower()
    out = []
    for name in sorted(os.listdir(root))[:1000]:
        if q and q not in name.lower():
            continue
        path = os.path.join(root, name)
        out.append({"name": name, "path": path, "kind": "dir" if os.path.isdir(path) else "file"})
    return out
