"""Flashcards with a light SM-2 spaced-repetition scheduler.

Local-first: one JSON file per profile (flashcards.json). Cards are plain
{front, back} pairs optionally tied to a source note, so the wiki-link graph,
the AI index and the export center all see them like any other data.

Scheduling is a compact SM-2: each card carries ease (2.5 default), interval
(days), and due (unix). Grading:
- again  -> interval reset to 0 (due today, +10 min feel)
- hard   -> interval * 1.2, ease -0.15
- good   -> interval * ease
- easy   -> interval * ease * 1.3, ease +0.05
Intervals floor at 1 day after the first successful review; ease clamps to
[1.3, 3.0] so a rough streak never wedges a card.
"""

import math
import os
import time

from litebrowser.core.profile_lock import profile_locked, profile_transaction
from litebrowser.core.storage_utils import read_json, write_json
from litebrowser.services import history_service

_EASE_MIN = 1.3
_EASE_MAX = 3.0


def cards_path(base_dir: str) -> str:
    """Path of the per-profile flashcard store (shared with index invalidation)."""
    return os.path.join(base_dir, "flashcards.json")


def _number(value, default, maximum):
    try:
        result = float(value)
        return max(0, min(maximum, result)) if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def load_cards(base_dir: str) -> list[dict]:
    data = read_json(cards_path(base_dir), {"version": 1, "cards": []})
    cards = data.get("cards") if isinstance(data, dict) else None
    result = []
    for raw in cards if isinstance(cards, list) else []:
        if not isinstance(raw, dict):
            continue
        card = dict(raw)
        for key in ("front", "back", "source_note_id"):
            card[key] = str(card.get(key) or "")
        card["ease"] = max(_EASE_MIN, _number(card.get("ease"), 2.5, _EASE_MAX))
        card["interval"] = _number(card.get("interval"), 0, 36500)
        for key in ("due", "reviews", "lapses"):
            card[key] = int(_number(card.get(key), 0, 253402214400 if key == "due" else 1_000_000))
        result.append(card)
    return result


def save_cards(base_dir: str, cards: list[dict]) -> None:
    with profile_locked(base_dir):
        write_json(cards_path(base_dir), {"version": 1, "cards": cards})


def new_card(front: str, back: str, source_note_id: str = "") -> dict:
    """The card shape in one place: the Add button and the deck importer agree.

    Trimming lives here too, so an importer can compare what it is about to add
    against what is already stored without re-deriving the limits.
    """
    return {
        "id": os.urandom(8).hex(),
        "front": (front or "").strip()[:500],
        "back": (back or "").strip()[:2000],
        "source_note_id": source_note_id or "",
        "ease": 2.5,
        "interval": 0,
        "due": int(time.time()),
        "created_at": int(time.time()),
        "reviews": 0,
        "lapses": 0,
    }


@profile_transaction
def add_cards(base_dir: str, cards: list[dict]) -> list[dict]:
    """Store several prepared cards (see :func:`new_card`) in a single write.

    Like :func:`add_card`, this stores what it is handed: deciding that a card is
    too blank to keep belongs to the caller that can say so (the Add field pair,
    the deck importer's skip count), not to the store.
    """
    fresh = [card for card in cards if isinstance(card, dict)]
    if not fresh:
        return []
    stored = load_cards(base_dir)
    stored[0:0] = fresh
    save_cards(base_dir, stored)
    return fresh


def add_card(base_dir: str, front: str, back: str, source_note_id: str = "") -> dict:
    card = new_card(front, back, source_note_id)
    add_cards(base_dir, [card])
    history_service.log_event(base_dir, "flashcard", card["front"][:80], "Card created", {"card_id": card["id"]})
    return card


@profile_transaction
def delete_card(base_dir: str, card_id: str) -> bool:
    from litebrowser.services import link_service

    cards = load_cards(base_dir)
    kept = [c for c in cards if c.get("id") != card_id]
    if len(kept) == len(cards):
        return False
    save_cards(base_dir, kept)
    link_service.delete_links_for(base_dir, "flashcard", card_id)
    return True


@profile_transaction
def delete_cards_for_note(base_dir: str, note_id: str) -> int:
    """Cascade: when a source note is deleted, its generated cards go too
    (they would review as orphans with no context)."""
    from litebrowser.services import link_service

    cards = load_cards(base_dir)
    kept = [c for c in cards if c.get("source_note_id") != note_id]
    removed = len(cards) - len(kept)
    if removed:
        save_cards(base_dir, kept)
        for card in cards:
            if card.get("source_note_id") == note_id:
                link_service.delete_links_for(base_dir, "flashcard", card.get("id", ""))
    return removed


def due_cards(base_dir: str, now: int | None = None) -> list[dict]:
    now = int(now if now is not None else time.time())
    return [c for c in load_cards(base_dir) if int(c.get("due", 0) or 0) <= now]


@profile_transaction
def review_card(base_dir: str, card_id: str, grade: str) -> dict | None:
    """Apply one SM-2 review; grade in {again, hard, good, easy}."""
    grade = (grade or "").strip().lower()
    if grade not in ("again", "hard", "good", "easy"):
        return None
    cards = load_cards(base_dir)
    for card in cards:
        if card.get("id") != card_id:
            continue
        ease = float(card.get("ease", 2.5) or 2.5)
        interval = float(card.get("interval", 0) or 0)
        now = int(time.time())
        if grade == "again":
            ease = max(_EASE_MIN, ease - 0.20)
            interval = 0
            card["lapses"] = int(card.get("lapses", 0) or 0) + 1
            due = now + 10 * 60  # 10 minutes: a same-session retry feel
        else:
            factor = {"hard": 1.2, "good": ease, "easy": ease * 1.3}[grade]
            if grade == "hard":
                ease = max(_EASE_MIN, ease - 0.15)
            elif grade == "easy":
                ease = min(_EASE_MAX, ease + 0.05)
            interval = 1 if interval < 1 else interval * factor
            due = now + int(interval * 86400)
        card.update({"ease": round(ease, 3), "interval": round(interval, 2), "due": due})
        card["reviews"] = int(card.get("reviews", 0) or 0) + 1
        save_cards(base_dir, cards)
        history_service.log_event(
            base_dir, "flashcard-review", card.get("front", "")[:80], grade,
            {"card_id": card_id, "interval": card["interval"]},
        )
        return card
    return None


def stats(base_dir: str) -> dict:
    cards = load_cards(base_dir)
    now = int(time.time())
    due = sum(1 for c in cards if c["due"] <= now)
    return {"total": len(cards), "due": due, "matured": sum(1 for c in cards if float(c.get("interval", 0) or 0) >= 21)}
