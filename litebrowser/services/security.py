# Mei - Passcode gating (per profile)
import base64
import hashlib
import hmac
import os
import weakref

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from litebrowser.core import prefs

_UNLOCKED = set()  # in-memory session unlock, per base_dir
_LOCK_LISTENERS = {}


def on_lock(base_dir: str, callback) -> None:
    """Weak subscriptions let every shell relock without retaining windows."""
    _LOCK_LISTENERS.setdefault(os.path.normcase(os.path.realpath(base_dir)), []).append(weakref.WeakMethod(callback))


def _pbkdf2_hash(passcode: str, salt: bytes, rounds: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", (passcode or "").encode("utf-8"), salt, rounds)


def _encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii")


def _decode(s: str) -> bytes:
    return base64.urlsafe_b64decode((s or "").encode("ascii"))


def has_passcode(base_dir: str) -> bool:
    salt_b64, hash_b64, rounds = prefs.get_passcode_record(base_dir)
    return bool(salt_b64 and hash_b64 and rounds)


def set_passcode(base_dir: str, new_passcode: str) -> bool:
    if not new_passcode:
        return False
    salt = os.urandom(16)
    rounds = 200_000
    digest = _pbkdf2_hash(new_passcode, salt, rounds)
    prefs.set_passcode_record(base_dir, _encode(salt), _encode(digest), rounds)
    return True


def verify_passcode(base_dir: str, passcode: str) -> bool:
    salt_b64, hash_b64, rounds = prefs.get_passcode_record(base_dir)
    if not salt_b64 or not hash_b64 or not rounds:
        return False
    try:
        salt = _decode(salt_b64)
        expected = _decode(hash_b64)
        rounds = int(rounds)
        if len(salt) != 16 or len(expected) != 32 or not 100_000 <= rounds <= 2_000_000:
            return False
        got = _pbkdf2_hash(passcode, salt, rounds)
        return hmac.compare_digest(expected, got)
    except (TypeError, ValueError):
        return False


def is_unlocked(base_dir: str) -> bool:
    key = os.path.normcase(os.path.realpath(base_dir))
    return any(os.path.normcase(os.path.realpath(path)) == key for path in _UNLOCKED)


def lock(base_dir: str) -> None:
    key = os.path.normcase(os.path.realpath(base_dir))
    _UNLOCKED.difference_update(path for path in list(_UNLOCKED) if os.path.normcase(os.path.realpath(path)) == key)
    live = []
    for reference in _LOCK_LISTENERS.get(key, []):
        callback = reference()
        if callback is not None:
            live.append(reference)
            callback()
    _LOCK_LISTENERS[key] = live


class _PasscodeDialog(QDialog):
    def __init__(self, parent, title: str, mode: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(420, 210)
        self._remember = True
        self._mode = mode  # "set" or "unlock"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self.lbl = QLabel(
            "Set a passcode to lock Personal/AI (per profile)." if mode == "set"
            else "Enter the passcode to unlock this area."
        )
        self.lbl.setWordWrap(True)
        layout.addWidget(self.lbl)

        self.ed1 = QLineEdit()
        self.ed1.setEchoMode(QLineEdit.Password)
        self.ed1.setPlaceholderText("Passcode")
        layout.addWidget(self.ed1)

        self.ed2 = None
        if mode == "set":
            self.ed2 = QLineEdit()
            self.ed2.setEchoMode(QLineEdit.Password)
            self.ed2.setPlaceholderText("Re-enter passcode")
            layout.addWidget(self.ed2)

        self.remember = QCheckBox("Remember unlock for this session (not saved to disk)")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        layout.addLayout(row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

    def values(self) -> tuple[str, str | None, bool]:
        a = self.ed1.text() or ""
        b = self.ed2.text() if self.ed2 else None
        return a, b, bool(self.remember.isChecked())


def ensure_unlocked(parent, base_dir: str, title: str = "Unlock") -> bool:
    """
    Ensure base_dir is unlocked for this session.
    If no passcode exists, prompt to set one (twice confirm).
    If exists, prompt to unlock.
    """
    if is_unlocked(base_dir):
        return True

    if not has_passcode(base_dir):
        dlg = _PasscodeDialog(parent, "Set passcode", mode="set")
        if dlg.exec_() != QDialog.Accepted:
            return False
        a, b, remember = dlg.values()
        if not a or (b is not None and a != b):
            QMessageBox.warning(parent, "Passcode", "Passcode is empty or the re-entry does not match.")
            return False
        if not set_passcode(base_dir, a):
            QMessageBox.warning(parent, "Passcode", "Could not set the passcode.")
            return False
        if remember:
            _UNLOCKED.add(os.path.normcase(os.path.realpath(base_dir)))
        QMessageBox.information(parent, "Passcode", "Passcode set for this profile.")
        return True

    dlg = _PasscodeDialog(parent, title, mode="unlock")
    if dlg.exec_() != QDialog.Accepted:
        return False
    a, _b, remember = dlg.values()
    if verify_passcode(base_dir, a):
        if remember:
            _UNLOCKED.add(os.path.normcase(os.path.realpath(base_dir)))
        return True

    QMessageBox.warning(parent, "Passcode", "Wrong passcode.")
    return False

