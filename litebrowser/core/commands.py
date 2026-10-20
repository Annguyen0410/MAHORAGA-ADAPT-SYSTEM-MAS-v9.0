"""Slash-command registry: the single source of truth for every surface that
lists commands — the omnibar autocomplete, the omnibar hint line, the command
palette / quick switcher and ``docs/COMMAND_REFERENCE.md``.

Each entry declares:

``name``        the literal the user types, e.g. ``/template``
``takes_arg``   True when text after the command is expected; surfaces then
                offer it with a trailing space so the box stays typeable
``description`` one line, shown in hints and the palette
``kind``        ``"action"`` (does something) or ``"nav"`` (goes somewhere)
``example``     optional concrete usage shown after the description

Adding a command is two edits: one entry here, one dispatch branch in
``AppShell._handle_omnibar_text``.  ``tests/test_command_registry.py`` enforces
the pair, keeps the autocomplete generated (a hand-written list drifted by six
commands) and keeps the docs complete.
"""
from typing import NamedTuple


class Command(NamedTuple):
    name: str
    takes_arg: bool
    description: str
    kind: str = "action"
    example: str = ""

    def completion(self) -> str:
        """What the autocomplete should insert for this command."""
        return self.name + (" " if self.takes_arg else "")

    def hint(self) -> str:
        """One-line hint shown under the omnibar."""
        return f"{self.description} · {self.example}" if self.example else self.description


# Navigation first (they are what people reach for most), then actions.
COMMANDS: tuple[Command, ...] = (
    Command("/home", False, "Home dashboard", "nav"),
    Command("/browser", False, "Browser workspace", "nav"),
    Command("/history", False, "History workspace", "nav"),
    Command("/ai", False, "AI workspace (passcode-gated)", "nav"),
    Command("/personal", False, "Personal Hub (passcode-gated)", "nav"),
    Command("/library", False, "Library workspace", "nav"),
    Command("/settings", False, "Settings workspace", "nav"),
    Command("/guide", False, "Browser control center", "nav"),
    Command("/help", False, "Browser control center", "nav"),
    Command("/read", False, "Reading list", "nav"),
    Command("/reading-list", False, "Reading list", "nav"),
    Command("/hub", False, "Open the Project Hub app chain", "nav"),
    Command("/cql", False, "Open Management Hub", "nav"),
    Command("/linklumina", False, "Open LinkLumina", "nav"),
    Command("/mas", False, "Open MAS — Mahoraga Adapt System", "nav"),
    Command("/leaderboard", False, "Open World Leaderboard", "nav"),
    Command("/bimat", False, "Open PersonalFrequency", "nav"),
    Command("/boitoan", False, "Open Fortune & Reflection", "nav"),
    Command("/task", True, "Create a task and jump to Personal", "action", "/task Prepare report"),
    Command("/note", True, "Create a note", "action", "/note Work/Brief | body"),
    Command("/capture", False, "Quick capture a note, task, link, or flashcard"),
    Command("/board", True, "Create an idea board", "action", "/board Sprint map"),
    Command("/ask", True, "Ask with current workspace context", "action", "/ask …"),
    Command("/save-page", False, "Save the active browser page to Library"),
    Command("/focus", True, "Start a café pour (minutes)", "action", "/focus 25 (minutes)"),
    Command("/status", False, "Show current focus timer state"),
    Command("/cafe", False, "Open café Focus journal / controls"),
    Command("/freeze", False, "Suspend all background tabs to free memory"),
    Command("/save-tabs", True, "Save current tabs as a named set", "action", "/save-tabs Research"),
    Command("/summarize", True, "Summarize the active browser page with AI"),
    Command("/brief", False, "Show your local Morning Brief"),
    Command("/flow", False, "Study loop: capture → plan → study → review → reflect"),
    Command("/agent", True, "Agent actions (summary / tasks / review)", "action", "/agent summary"),
    Command("/group-tabs", False, "Label tabs by domain so you can filter them"),
    Command("/sync", False, "Push + pull a self-hosted snapshot"),
    Command("/review", False, "Flashcard review queue"),
    Command("/routines", False, "Schedule daily automations"),
    Command("/export", False, "Export notes as MD zip or HTML site"),
    Command("/template", True, "Daily plan or weekly review note", "action", "/template daily"),
    Command("/theme", True, "Switch theme instantly", "action", "/theme matcha-day"),
    Command("/accent", True, "Switch accent color", "action", "/accent matcha"),
)


def command_names() -> tuple[str, ...]:
    return tuple(cmd.name for cmd in COMMANDS)


def by_name(name: str) -> Command | None:
    for cmd in COMMANDS:
        if cmd.name == name:
            return cmd
    return None


def completions() -> list[str]:
    """Autocomplete entries — generated, never hand-maintained."""
    return [cmd.completion() for cmd in COMMANDS]


def hints() -> dict[str, str]:
    """Omnibar hint text per command."""
    return {cmd.name: cmd.hint() for cmd in COMMANDS}


def action_names() -> tuple[str, ...]:
    return tuple(cmd.name for cmd in COMMANDS if cmd.kind == "action")


def nav_names() -> tuple[str, ...]:
    return tuple(cmd.name for cmd in COMMANDS if cmd.kind == "nav")
