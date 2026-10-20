"""Two-way links between entities living in different stores.

Notes already know wiki-links and a card remembers its source note, but the
graph between a note, a planner item, a card, a saved page or a board node had
nowhere to live: every store would have needed its own link list, its own
migration and its own sync merge. One small edge table fixes that once.

An edge is ``(from_type, from_id) -> (to_type, to_id)`` with an optional label.
Backlinks are the same rows read in reverse, so the two directions can never
drift apart.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from litebrowser.core.profile_lock import profile_locked
from litebrowser.core.store import StoreSpec, read_store, write_store

LINK_VERSION = 1
LINK_FILENAME = "entity_links.json"
VALID_ENTITY_TYPES = (
    "note",
    "task",
    "planner_item",
    "planner_course",
    "planner_block",
    "saved_page",
    "flashcard",
    "board_node",
)


def _default_links() -> dict:
    return {"version": LINK_VERSION, "links": []}


# Versioned like every other store: one writer, atomic, no silent downgrade.
LINK_STORE = StoreSpec(name=LINK_FILENAME, version=LINK_VERSION, default=_default_links)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_type(value: Any) -> str:
    entity_type = str(value or "").strip().lower()
    return entity_type if entity_type in VALID_ENTITY_TYPES else ""


def _normalize_link(link: Any) -> dict | None:
    if not isinstance(link, dict):
        return None
    from_type = _clean_type(link.get("from_type"))
    to_type = _clean_type(link.get("to_type"))
    from_id = str(link.get("from_id") or "").strip()[:1024]
    to_id = str(link.get("to_id") or "").strip()[:1024]
    if not (from_type and to_type and from_id and to_id):
        return None
    created = str(link.get("created_at") or "").strip() or _now_iso()
    return {
        **link,
        "id": str(link.get("id") or uuid.uuid4().hex)[:80],
        "from_type": from_type,
        "from_id": from_id,
        "to_type": to_type,
        "to_id": to_id,
        "label": str(link.get("label") or "").strip()[:120],
        "created_at": created,
        "updated_at": str(link.get("updated_at") or "").strip() or created,
    }


def load_links(base_dir: str) -> list[dict]:
    data = read_store(base_dir, LINK_STORE)
    links = data.get("links") if isinstance(data, dict) else None
    if not isinstance(links, list):
        return []
    return [normalized for normalized in (_normalize_link(link) for link in links) if normalized]


def save_links(base_dir: str, links: list) -> list[dict]:
    """Bulk write (backup/sync import): normalise first, then persist."""
    normalized = [link for link in (_normalize_link(raw) for raw in (links or [])) if link]
    with profile_locked(base_dir):
        write_store(base_dir, LINK_STORE, {"links": normalized})
    return normalized


def add_link(
    base_dir: str,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    label: str = "",
) -> dict | None:
    """Create one directed edge; a duplicate returns the existing edge."""
    link = _normalize_link(
        {
            "from_type": from_type,
            "from_id": from_id,
            "to_type": to_type,
            "to_id": to_id,
            "label": label,
        }
    )
    if link is None:
        return None
    if link["from_type"] == link["to_type"] and link["from_id"] == link["to_id"]:
        return None
    with profile_locked(base_dir):
        links = load_links(base_dir)
        for existing in links:
            if (
                existing["from_type"],
                existing["from_id"],
                existing["to_type"],
                existing["to_id"],
                existing["label"],
            ) == (
                link["from_type"],
                link["from_id"],
                link["to_type"],
                link["to_id"],
                link["label"],
            ):
                return existing
        links.append(link)
        write_store(base_dir, LINK_STORE, {"links": links})
    return link


def remove_link(base_dir: str, link_id: str) -> bool:
    with profile_locked(base_dir):
        links = load_links(base_dir)
        kept = [link for link in links if link.get("id") != link_id]
        if len(kept) == len(links):
            return False
        write_store(base_dir, LINK_STORE, {"links": kept})
        return True


def links_for(base_dir: str, entity_type: str, entity_id: str) -> dict:
    """Outgoing edges plus backlinks for one entity."""
    entity_type = _clean_type(entity_type)
    entity_id = str(entity_id or "").strip()
    outgoing: list[dict] = []
    incoming: list[dict] = []
    if entity_type and entity_id:
        for link in load_links(base_dir):
            if link["from_type"] == entity_type and link["from_id"] == entity_id:
                outgoing.append(link)
            elif link["to_type"] == entity_type and link["to_id"] == entity_id:
                incoming.append(link)
    return {"outgoing": outgoing, "incoming": incoming, "total": len(outgoing) + len(incoming)}


def delete_links_for(base_dir: str, entity_type: str, entity_id: str) -> int:
    """Cascade: drop every edge that touches an entity being deleted."""
    entity_type = _clean_type(entity_type)
    entity_id = str(entity_id or "").strip()
    if not entity_type or not entity_id:
        return 0
    with profile_locked(base_dir):
        links = load_links(base_dir)
        kept = [
            link
            for link in links
            if not (
                (link["from_type"] == entity_type and link["from_id"] == entity_id)
                or (link["to_type"] == entity_type and link["to_id"] == entity_id)
            )
        ]
        removed = len(links) - len(kept)
        if removed:
            write_store(base_dir, LINK_STORE, {"links": kept})
        return removed
