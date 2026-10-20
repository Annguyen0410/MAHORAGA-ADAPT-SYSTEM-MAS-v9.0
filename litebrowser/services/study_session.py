"""Study sessions: one planner item, one focus pour, credited minutes.

The loop the weekly planner was missing. A session starts *from* an item or a
time block, runs through Café Focus (so the pour journal and streaks keep
working), and when it finishes the elapsed minutes are written back to the
item — exactly once, tracked by ``credited`` on the session record.

The review queue stays the global deck; pinning individual cards to a course is
the job of the entity-link table, not of this module.
"""
from __future__ import annotations

from datetime import datetime

from litebrowser.core.profile_lock import profile_transaction

from litebrowser.services import (
    flashcard_service,
    focus_service,
    history_service,
    personal_plan,
)

MIN_SESSION_MINUTES = 5
MAX_SESSION_MINUTES = 180


def _find_item(base_dir: str, item_id: str) -> dict | None:
    return next(
        (item for item in personal_plan.load_plan(base_dir)["items"] if item.get("id") == item_id),
        None,
    )


def _find_block(base_dir: str, block_id: str) -> dict | None:
    return next(
        (
            block
            for block in personal_plan.load_plan(base_dir)["time_blocks"]
            if block.get("id") == block_id
        ),
        None,
    )


def _planned_minutes(value, default: int) -> int:
    try:
        planned = int(value or default)
    except (TypeError, ValueError, OverflowError):
        planned = default
    return max(MIN_SESSION_MINUTES, min(MAX_SESSION_MINUTES, planned))


def start_for_item(base_dir: str, item_id: str, minutes: int | None = None) -> dict | None:
    """Pour a study session tied to a planner item (default: the item's duration)."""
    item = _find_item(base_dir, item_id)
    if item is None:
        return None
    planned = _planned_minutes(minutes, int(item.get("duration_minutes") or personal_plan.DEFAULT_DURATION_MINUTES))
    session = focus_service.start_focus(
        base_dir, minutes=planned, label=item.get("title", ""), item_id=item_id
    )
    history_service.log_event(
        base_dir,
        "study",
        item.get("title", ""),
        f"Study session started ({planned} min)",
        {"item_id": item_id, "minutes": planned},
    )
    return session


def start_for_block(base_dir: str, block_id: str, minutes: int | None = None) -> dict | None:
    """Pour a session for a focus block; a linked planner item receives credit."""
    block = _find_block(base_dir, block_id)
    if block is None:
        return None
    planned = _planned_minutes(
        minutes, int(block.get("duration_minutes") or personal_plan.DEFAULT_DURATION_MINUTES)
    )
    session = focus_service.start_focus(
        base_dir,
        minutes=planned,
        label=block.get("title", ""),
        item_id=block.get("item_id", "") or "",
    )
    history_service.log_event(
        base_dir,
        "study",
        block.get("title", ""),
        f"Study block started ({planned} min)",
        {"block_id": block_id, "item_id": session.get("item_id", ""), "minutes": planned},
    )
    return session


def active_session(base_dir: str) -> dict:
    """Running session (if any), the item behind it, and the due-card count."""
    status = focus_service.focus_status(base_dir)
    payload = {
        "running": bool(status.get("running")),
        "session": status.get("session"),
        "remaining": int(status.get("remaining", 0) or 0),
        "item": None,
        "cards_due": flashcard_service.stats(base_dir)["due"],
    }
    active = status.get("session")
    if isinstance(active, dict) and active.get("item_id"):
        payload["item"] = _find_item(base_dir, active["item_id"])
    return payload


@profile_transaction
def finish(base_dir: str, complete: bool = True) -> dict:
    """Stop the running pour, then credit whatever it earned."""
    focus_service.stop_focus(base_dir, complete=complete)
    summary = credit_pending(base_dir)
    return summary


@profile_transaction
def credit_pending(base_dir: str) -> dict:
    """Credit every finished, uncredited item session in the journal.

    Rounding rule: elapsed whole minutes, capped by the planned duration — the
    same honesty rule the focus heatmap uses. A session that ran for less than
    a minute still gets marked credited so it is never re-counted.
    """
    # Close an expired pour first. Without this the minutes earned while the app
    # sat on another workspace stayed inside "active" and were only credited the
    # next time something happened to read the status — so the planner label
    # showed nothing right after a session ended.
    focus_service.focus_status(base_dir)
    summary = {"credited": 0, "minutes": 0, "items": [], "cards_due": 0}
    for session in reversed(focus_service.focus_journal(base_dir, limit=200)):
        item_id = session.get("item_id")
        if not item_id or session.get("credited") or session.get("status") != "completed":
            continue
        planned = int(session.get("minutes", 0) or 0)
        started = int(session.get("started_at", 0) or 0)
        ended = int(session.get("ended_at", 0) or started)
        spent = max(0, min(ended - started, planned * 60)) // 60 if planned else 0
        item = _find_item(base_dir, item_id)
        if item is None or spent <= 0:
            # Nothing honest to credit (deleted item / immediate stop): flag the
            # session so the next refresh does not re-examine it.
            focus_service.mark_credited(base_dir, session.get("id", ""))
            continue
        session_id = session.get("id", "")
        credited_ids = item.get("credited_session_ids", [])
        if session_id in credited_ids:
            # Recover a crash after the planner write but before the journal
            # acknowledgement without adding those minutes a second time.
            focus_service.mark_credited(base_dir, session_id)
            continue
        updated = personal_plan.update_item(
            base_dir,
            item_id,
            studied_minutes=int(item.get("studied_minutes", 0) or 0) + spent,
            last_studied_at=datetime.now().isoformat(timespec="seconds"),
            credited_session_ids=[*credited_ids, session_id][-256:],
        )
        focus_service.mark_credited(base_dir, session.get("id", ""))
        history_service.log_event(
            base_dir,
            "study",
            item.get("title", ""),
            f"Studied {spent} min",
            {
                "item_id": item_id,
                "minutes": spent,
                "total_minutes": int((updated or {}).get("studied_minutes", 0) or 0),
            },
        )
        summary["credited"] += 1
        summary["minutes"] += spent
        summary["items"].append(item_id)
    summary["cards_due"] = flashcard_service.stats(base_dir)["due"]
    return summary
