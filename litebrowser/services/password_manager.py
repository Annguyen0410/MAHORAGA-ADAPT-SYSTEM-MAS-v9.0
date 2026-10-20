# Mei - Password manager (basic): encrypted store + autofill
import base64
import hashlib
import json
import os
from urllib.parse import urlsplit

from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked, profile_transaction
from litebrowser.core.storage_utils import write_text_atomic

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

_log = get_logger("password_manager")


_VAULT_VERSION = 2
_KDF_NAME = "pbkdf2-sha256"
_KDF_ITERATIONS = 390000
_SALT_BYTES = 16


def _derive_key(master_password):
    """Legacy static derivation kept so existing password vaults can be read."""
    if not master_password:
        return None
    key = hashlib.sha256(("litebrowser_pw_salt_" + master_password).encode()).digest()
    return base64.urlsafe_b64encode(key).decode()


def _derive_pbkdf2_key(master_password, salt, iterations):
    if not master_password or not salt:
        return None
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=int(iterations or _KDF_ITERATIONS),
        backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))


def _get_cipher(master_password):
    """Legacy cipher kept for read compatibility with pre-v2 vault files."""
    if not HAS_CRYPTO or not master_password:
        return None
    try:
        key = _derive_key(master_password)
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:  # noqa: BLE001  crypto failure -> no legacy cipher (never log the password)
        _log.warning("legacy cipher derivation failed: %s", type(exc).__name__)
        return None


def _passwords_path(base_dir):
    return os.path.join(base_dir, "SafeVault", "passwords.enc")


def _get_v2_cipher(master_password, salt=None, iterations=_KDF_ITERATIONS):
    if not HAS_CRYPTO or not master_password:
        return None, None
    try:
        salt = salt or os.urandom(_SALT_BYTES)
        key = _derive_pbkdf2_key(master_password, salt, iterations)
        if not key:
            return None, None
        return Fernet(key), salt
    except Exception as exc:  # noqa: BLE001  crypto failure -> no v2 cipher (never log the password)
        _log.warning("v2 cipher derivation failed: %s", type(exc).__name__)
        return None, None


def _encrypted_entry(entry, cipher):
    item = {"url": entry.get("url", ""), "username": entry.get("username", "")}
    pw = entry.get("password") or entry.get("password_plain", "")
    if pw:
        item["password"] = cipher.encrypt(str(pw).encode("utf-8")).decode("utf-8")
    else:
        item["password"] = entry.get("password_encrypted", "")
    return item


def _decrypt_entries(data, cipher):
    out = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        pw = entry.get("password", "")
        if pw:
            try:
                token = pw.encode("utf-8") if isinstance(pw, str) else pw
                pw = cipher.decrypt(token).decode("utf-8")
            except Exception as exc:  # noqa: BLE001  bad token -> empty (never log the password)
                _log.warning("entry decrypt failed: %s", type(exc).__name__)
                # Decryption failed: surface an empty password instead of the
                # ciphertext blob (v6.4 leaked the encrypted string as if it
                # were the plaintext password into the UI and autofill).
                pw = ""
        out.append({"url": entry.get("url", ""), "username": entry.get("username", ""), "password": pw})
    return out


def _encode_v2_vault(entries, master_password):
    cipher, salt = _get_v2_cipher(master_password)
    if not cipher or not salt:
        return None
    payload = [_encrypted_entry(entry, cipher) for entry in entries]
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    envelope = {
        "version": _VAULT_VERSION,
        "kdf": {
            "name": _KDF_NAME,
            "iterations": _KDF_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
        },
        "payload": cipher.encrypt(raw).decode("utf-8"),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def _decode_v2_vault(blob, master_password):
    """Returns (handled, entries). handled=False means 'not a v2 vault';

    handled=True with entries=list (possibly empty) means decrypted OK;
    handled=True with entries=None means the vault IS v2 but could NOT be
    decrypted (wrong password / corrupt). Callers must never overwrite the
    vault in that case (v6.4 wiped the whole vault on a typo'd password)."""
    try:
        envelope = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False, []
    if not isinstance(envelope, dict):
        return False, []
    try:
        version = int(envelope.get("version", 0) or 0)
    except (TypeError, ValueError):
        return False, []
    if version != _VAULT_VERSION:
        return False, []
    try:
        kdf = envelope.get("kdf") if isinstance(envelope.get("kdf"), dict) else {}
        if kdf.get("name") != _KDF_NAME:
            return True, None
        salt = base64.b64decode(kdf.get("salt") or "")
        iterations = int(kdf.get("iterations") or _KDF_ITERATIONS)
        if not 100_000 <= iterations <= 2_000_000 or len(salt) != _SALT_BYTES:
            return True, None
        cipher, _ = _get_v2_cipher(master_password, salt=salt, iterations=iterations)
        if not cipher:
            return True, None
        raw = cipher.decrypt(str(envelope.get("payload") or "").encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        return True, _decrypt_entries(data, cipher)
    except Exception:  # noqa: BLE001  any crypto/decode failure means locked
        return True, None


class VaultUnlockError(RuntimeError):
    """Raised when a v2 vault exists but the master password is wrong."""


def save_passwords(base_dir, entries, master_password):
    """entries: list of {url_pattern, username, password_encrypted or plain}. Encrypts and writes."""
    if not HAS_CRYPTO or not master_password:
        return False
    encoded = _encode_v2_vault(entries if isinstance(entries, list) else [], master_password)
    if not encoded:
        return False
    try:
        with profile_locked(base_dir):
            write_text_atomic(_passwords_path(base_dir), encoded.decode("utf-8"))
        return True
    except (OSError, ValueError) as exc:
        _log.warning("password vault save failed: %s", type(exc).__name__)
        return False


def load_passwords(base_dir, master_password):
    """Returns list of {url, username, password} (decrypted)."""
    status, entries = load_passwords_status(base_dir, master_password)
    return entries


def load_passwords_status(base_dir, master_password):
    """Returns (status, entries); status is one of:
    - "ok":      vault read and decrypted (may be empty)
    - "missing": no vault file yet
    - "locked":  a vault exists but the master password is wrong / file corrupt
    """
    if not HAS_CRYPTO or not master_password:
        return "missing", []
    cipher = _get_cipher(master_password)
    if not cipher:
        return "missing", []
    path = _passwords_path(base_dir)
    if not os.path.isfile(path):
        return "missing", []
    try:
        with profile_locked(base_dir), open(path, "rb") as f:
            blob = f.read()
        handled, entries = _decode_v2_vault(blob, master_password)
        if handled:
            return ("locked" if entries is None else "ok"), (entries or [])
        raw = cipher.decrypt(blob).decode("utf-8")
        data = json.loads(raw)
        return "ok", _decrypt_entries(data, cipher)
    except Exception:  # noqa: BLE001  wrong password/corrupt vault must stay locked
        return "locked", []


@profile_transaction
def add_password(base_dir, url, username, password, master_password):
    status, entries = load_passwords_status(base_dir, master_password)
    if status == "locked":
        # The vault exists but this master password cannot decrypt it. Saving
        # now would replace every stored credential with just this one entry —
        # refuse instead (v6.4 silently wiped the whole vault on a typo).
        raise VaultUnlockError(
            "The saved password vault could not be unlocked with this master password. "
            "Nothing was changed. Check the password and try again."
        )
    url_norm = _normalize_origin(url)
    if not url_norm:
        return False
    for e in entries:
        if _origin_match(e["url"], url_norm) and e["username"] == username:
            e["password"] = password
            return save_passwords(base_dir, entries, master_password)
    entries.append({"url": url_norm, "username": username, "password": password})
    return save_passwords(base_dir, entries, master_password)


def get_credentials_for(base_dir, url, master_password):
    entries = load_passwords(base_dir, master_password)
    url_norm = _normalize_origin(url)
    for e in entries:
        if _origin_match(e["url"], url_norm):
            return {"username": e["username"], "password": e["password"]}
    return None


def _normalize_origin(url):
    if not url:
        return ""
    try:
        parsed = urlsplit(url.strip() if "://" in url else "https://" + url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return ""
        host = parsed.hostname.lower().rstrip(".")
        port = parsed.port
        default = 443 if parsed.scheme == "https" else 80
        authority = f"[{host}]" if ":" in host else host
        if port is not None and port != default:
            authority = f"{authority}:{port}"
        return f"{parsed.scheme.lower()}://{authority}"
    except (ValueError, TypeError, AttributeError):
        return ""


def _origin_match(stored_origin, page_origin):
    if not stored_origin or not page_origin:
        return False
    # Old vaults stored host-only entries. Interpret these as HTTPS rather
    # than releasing their secrets on an HTTP downgrade.
    so = _normalize_origin(stored_origin)
    po = _normalize_origin(page_origin)
    return bool(so and po and po == so)


AUTOFILL_SCRIPT = """
(function() {
  var form = document.querySelector('form');
  if (!form) return;
  var inputs = form.querySelectorAll('input');
  var userInput = null, passInput = null;
  for (var i = 0; i < inputs.length; i++) {
    var n = (inputs[i].name || '').toLowerCase();
    var t = (inputs[i].type || '').toLowerCase();
    if (t === 'password') passInput = inputs[i];
    else if (n.indexOf('user') >= 0 || n.indexOf('email') >= 0 || n.indexOf('login') >= 0) userInput = inputs[i];
    else if (t === 'text' && !userInput) userInput = inputs[i];
  }
  if (userInput && passInput && typeof __lite_username !== 'undefined' && typeof __lite_password !== 'undefined') {
    userInput.value = __lite_username;
    passInput.value = __lite_password;
    userInput.dispatchEvent(new Event('input', { bubbles: true }));
    passInput.dispatchEvent(new Event('input', { bubbles: true }));
  }
})();
"""


def build_autofill_script(username, password):
    """Returns JS string that sets __lite_username/__lite_password and runs AUTOFILL_SCRIPT."""
    u_esc = json.dumps(username)
    p_esc = json.dumps(password)
    return "(function(){var __lite_username = " + u_esc + "; var __lite_password = " + p_esc + "; " + AUTOFILL_SCRIPT.strip() + "})();"


# Chrome-style save-password capture: a profile-level script watches every
# login form; on submit it stashes the credentials in sessionStorage under a
# fixed key. The app reads (and clears) that key on the NEXT page load, which
# is when a real login would have succeeded — no QWebChannel needed.
CAPTURE_INSTALL_SCRIPT = """
(function() {
  if (window.__mei_capture_installed) return;
  window.__mei_capture_installed = true;
  function findCreds(root) {
    var pass = root.querySelector('input[type="password"]');
    if (!pass) return null;
    var form = pass.closest('form') || document;
    var user = null;
    var inputs = (form === document ? document.querySelectorAll('input') : form.querySelectorAll('input'));
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i] === pass) continue;
      var t = (inputs[i].type || '').toLowerCase();
      if (t === 'email' || t === 'text' || t === 'tel') { user = inputs[i]; break; }
    }
    if (!pass.value) return null;
    return { user: user ? user.value : '', pass: pass.value };
  }
  function stash(creds) {
    try {
      sessionStorage.setItem('__mei_pending_creds', JSON.stringify({
        user: creds.user, pass: creds.pass, at: Date.now()
      }));
    } catch (e) {}
  }
  document.addEventListener('submit', function(ev) {
    try {
      var creds = findCreds(ev.target);
      if (creds) stash(creds);
    } catch (e) {}
  }, true);
  // SPA-style logins (fetch/XHR without form submit): watch password fields
  // losing focus right before a same-tick navigation is too fragile, so also
  // listen for Enter inside a password field.
  document.addEventListener('keydown', function(ev) {
    if (ev.key !== 'Enter') return;
    try {
      var t = ev.target;
      if (t && (t.type || '').toLowerCase() === 'password') {
        var creds = findCreds(t.closest('form') || document);
        if (creds) stash(creds);
      }
    } catch (e) {}
  }, true);
})();
"""

READ_CAPTURED_SCRIPT = """
(function() {
  try {
    var raw = sessionStorage.getItem('__mei_pending_creds');
    if (!raw) return null;
    sessionStorage.removeItem('__mei_pending_creds');
    var d = JSON.parse(raw);
    if (!d || !d.pass || (Date.now() - (d.at || 0) > 60000)) return null;
    return { user: d.user || '', pass: d.pass };
  } catch (e) { return null; }
})();
"""
