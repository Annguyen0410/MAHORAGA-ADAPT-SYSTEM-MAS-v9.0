"""Application logging: one rotating file under the data root.

The app previously swallowed errors silently (`except Exception: pass` with no
trace). Logging goes to ``runtime_data/logs/mei.log`` (rotated, capped) so
nothing is lost on the console of a frozen exe, while development stays quiet.
Every call here is safe: if the log file cannot be created, the app still runs.
"""
import logging
import logging.handlers
import os
import re

_HANDLER = None
_LOG_DIR = None

# Credentials reach log lines through provider errors, redirect URLs and stack
# traces. A diagnostics bundle is meant to be handed to a stranger, so the file
# handler masks anything shaped like one before it is written. This is a
# defence-in-depth layer, not a reason to log tokens in the first place.
_REDACTION_PATTERNS = (
    (re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9\-._~+/]+=*)"), r"\1[redacted]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret)(\s*[=:]\s*)([^\s,;\"']+)"), r"\1\2[redacted]"),
    (re.compile(r"(?i)\b(https?://)([^/\s:@]+):([^/\s@]+)@"), r"\1[redacted]@"),
    (re.compile(r"\b(?:sk|ghp|gho|ghu|ghs|ghr|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b"), "[redacted]"),
    (re.compile(r"\bya29\.[A-Za-z0-9_.-]{10,}\b"), "[redacted]"),
)


def redact(text: str) -> str:
    """Mask configured secret values and recognisable credential shapes."""
    cleaned = str(text or "")
    try:
        from litebrowser.core import secret_store

        for value in secret_store.known_secret_values():
            if value:
                cleaned = cleaned.replace(value, "[redacted]")
    except Exception:  # noqa: BLE001  logging must never fail on its own defence
        pass
    for pattern, replacement in _REDACTION_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            cleaned = redact(message)
            if cleaned != message:
                record.msg = cleaned
                record.args = ()
        except Exception:  # noqa: BLE001  never suppress a log record over redaction
            pass
        return True


def _open_handler(logs_dir: str) -> logging.handlers.RotatingFileHandler:
    os.makedirs(logs_dir, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(logs_dir, "mei.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(_RedactionFilter())
    handler.setLevel(logging.DEBUG)
    return handler


def configure(app_dir=None) -> None:
    """Point the file handler at ``app_dir``'s data root. Idempotent, never raises.

    Call again when the real profile/app dir becomes known; the handler is
    re-pointed instead of keeping the development default.
    """
    global _HANDLER, _LOG_DIR
    if _HANDLER is not None and app_dir in (None, _LOG_DIR):
        return
    try:
        from litebrowser.core import app_paths

        logs_dir = os.path.join(app_paths.data_root(app_dir), "logs")
        if _LOG_DIR == logs_dir:
            return
        if _HANDLER is not None:
            root = logging.getLogger("litebrowser")
            root.removeHandler(_HANDLER)
            try:
                _HANDLER.close()
            except Exception:  # noqa: BLE001  fail-safe: never raise from logging
                pass
        _HANDLER = _open_handler(logs_dir)
        _LOG_DIR = logs_dir
        root = logging.getLogger("litebrowser")
        root.setLevel(logging.DEBUG)
        root.addHandler(_HANDLER)
        root.propagate = False
    except Exception as exc:  # noqa: BLE001  logging must never take the app down
        logging.getLogger("litebrowser.log").debug("could not open log file: %s", exc)
        if _HANDLER is not None:
            try:
                _HANDLER.close()
            except Exception:  # noqa: BLE001  fail-safe: never raise from logging
                pass
            _HANDLER = None


def get_logger(name: str) -> logging.Logger:
    """Logger namespaced under ``litebrowser`` so all output lands in one file."""
    configure(None)
    if not name or name == "litebrowser":
        return logging.getLogger("litebrowser")
    return logging.getLogger(f"litebrowser.{name}")
