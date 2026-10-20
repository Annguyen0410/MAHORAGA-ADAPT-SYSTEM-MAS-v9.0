"""The study ritual — sit down properly before the timer starts.

A "pour" is this app's word for a focus session. Starting one used to be a single
typed line (``/focus 25``): fast, but it skips the part that actually makes a
session happen — deciding *what* you are going to finish and *how long* you are
willing to sit. This module turns that decision into a menu: every drink is a
pace, so choosing a cup is choosing a length, and the choice is remembered for
next time.

It writes only what the app already writes for a pour — one focus session
(:mod:`focus_service`), one history line, one preference — so Home's "Study
session" button and a typed ``/focus 25`` land in the same journal, and the
weekly review counts them the same way.
"""
from __future__ import annotations

from litebrowser.core import prefs
from litebrowser.services import focus_service, history_service

#: (id, menu line, minutes). The minutes are the point: a cup *is* a pace.
POURS: tuple[tuple[str, str, int], ...] = (
    ("ca-phe-den", "Black coffee · a short focus session", 25),
    ("tra-sen", "Lotus tea · light and quiet", 25),
    ("ca-phe-sua", "Milk coffee · the classic long session", 45),
    ("tra-dao", "Peach tea · iced peach, warm afternoon", 45),
    ("bac-xiu", "Light milk coffee · a slow double", 50),
    ("nuoc-cam", "Orange juice · a quick sip before class", 15),
)

#: The pour a first-time user gets, and the fallback when a saved one is gone.
DEFAULT_POUR = "ca-phe-sua"

POUR_PREF_KEY = "ritual_pour"


def pour_ids() -> tuple[str, ...]:
    """Every pour id, in menu order."""
    return tuple(pour for pour, _line, _minutes in POURS)


def pour_display(pour_id: str) -> str:
    """The menu line for ``pour_id`` (falls back to the default pour)."""
    for pour, line, _minutes in POURS:
        if pour == pour_id:
            return line
    return POURS[0][1]


def pour_minutes(pour_id: str) -> int:
    """The sitting length ``pour_id`` stands for."""
    for pour, _line, minutes in POURS:
        if pour == pour_id:
            return minutes
    return POURS[0][2]


def last_pour(base_dir: str) -> str:
    """The pour this profile poured last (default when nothing is saved)."""
    saved = str(prefs.get_pref(base_dir, POUR_PREF_KEY, "") or "").strip()
    return saved if saved in pour_ids() else DEFAULT_POUR


def start_ritual(base_dir: str, pour: str = "", minutes: int = 0, note: str = "", item_id: str = "") -> dict:
    """Start one ritual pour and remember the cup.

    ``minutes`` of 0 (or less) means "use the pace the cup stands for"; ``note``
    is the one line the user typed about what they will finish, and it rides in
    the session label so the journal entry explains itself later.
    """
    pour_id = (pour or "").strip()
    if pour_id not in pour_ids():
        pour_id = last_pour(base_dir)
    length = int(minutes or 0)
    if length <= 0:
        length = pour_minutes(pour_id)
    label = pour_display(pour_id)
    spoken = (note or "").strip()
    if spoken:
        label = f"{label} — {spoken}"
    session = focus_service.start_focus(
        base_dir, minutes=length, label=f"☕ {label}", item_id=item_id or ""
    )
    prefs.save_pref(base_dir, POUR_PREF_KEY, pour_id)
    history_service.log_event(
        base_dir,
        "study-ritual",
        pour_id,
        "Study session started from the desk",
        {"minutes": length, "note": spoken},
    )
    return session


def ritual_line(session: dict) -> str:
    """The one line the desk and the status strip show for a running pour."""
    session = session if isinstance(session, dict) else {}
    label = str(session.get("label") or "").strip() or pour_display(DEFAULT_POUR)
    minutes = int(session.get("minutes", 0) or 0)
    return f"{label} · {minutes} minutes" if minutes else label
