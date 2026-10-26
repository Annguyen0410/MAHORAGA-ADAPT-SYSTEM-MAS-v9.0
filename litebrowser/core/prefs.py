import copy
import json
import os
import re
import secrets
import shutil
import time

from litebrowser.core import app_paths
from litebrowser.core import secret_store
from litebrowser.core import theme_data as _theme_mod
from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked, profile_transaction
from litebrowser.core.storage_utils import read_json, write_json, write_text_atomic

_log = get_logger("prefs")


def _prefs_path(base_dir):
    return os.path.join(base_dir, "prefs.json")


def session_path(base_dir):
    return os.path.join(base_dir, "session.json")


def history_path(base_dir):
    return os.path.join(base_dir, "history.txt")


def bookmarks_path(base_dir):
    return os.path.join(base_dir, "bookmarks.json")


def vault_path(base_dir):
    return os.path.join(base_dir, "SafeVault")


def ext_path(base_dir):
    return os.path.join(base_dir, "Extensions")


def proxy_config_path(base_dir):
    return os.path.join(base_dir, "proxy_config.json")


def _strip_plaintext_proxy_password(base_dir):
    data = read_json(proxy_config_path(base_dir), {})
    if isinstance(data, dict) and "password" in data:
        data.pop("password", None)
        write_json(proxy_config_path(base_dir), data)


def get_proxy_config(base_dir) -> dict:
    data = read_json(proxy_config_path(base_dir), {"enabled": False})
    if not isinstance(data, dict):
        return {"enabled": False}
    legacy = data.pop("password", None) if "password" in data else None
    if isinstance(legacy, str) and legacy:
        secret_store.adopt(
            base_dir,
            "proxy_password",
            legacy,
            lambda: _strip_plaintext_proxy_password(base_dir),
        )
    secured = secret_store.get_secret(base_dir, "proxy_password")
    if secured is not None:
        data["password"] = secured
    elif isinstance(legacy, str) and legacy:
        data["password"] = legacy
    return data


@profile_transaction
def set_proxy_config(base_dir, cfg: dict):
    payload = dict(cfg) if isinstance(cfg, dict) else {"enabled": False}
    password = payload.pop("password", None)
    if password is not None:
        if str(password):
            secret_store.set_secret(base_dir, "proxy_password", str(password))
        else:
            secret_store.delete_secret(base_dir, "proxy_password")
    write_json(proxy_config_path(base_dir), payload)


def get_auto_connect_vpn(base_dir) -> bool:
    return bool(load_prefs(base_dir).get("vpn_auto_connect", False))


@profile_transaction
def set_auto_connect_vpn(base_dir, value):
    data = load_prefs(base_dir)
    data["vpn_auto_connect"] = bool(value)
    save_prefs(base_dir, data)


def get_last_vpn_proxy(base_dir) -> dict:
    """The last proxy the user connected with (kept even after disconnect so
    auto-connect can re-enable it on the next launch)."""
    data = load_prefs(base_dir).get("vpn_last_proxy", {})
    if not isinstance(data, dict):
        return {}
    data = dict(data)
    legacy = data.pop("password", None) if "password" in data else None
    if isinstance(legacy, str) and legacy:
        secret_store.adopt(
            base_dir,
            "proxy_password",
            legacy,
            lambda: _strip_plaintext_last_vpn_password(base_dir),
        )
    secured = secret_store.get_secret(base_dir, "proxy_password")
    if secured is not None:
        data["password"] = secured
    elif isinstance(legacy, str) and legacy:
        data["password"] = legacy
    return data


def _strip_plaintext_last_vpn_password(base_dir):
    data = load_prefs(base_dir)
    last = data.get("vpn_last_proxy")
    if isinstance(last, dict) and "password" in last:
        last.pop("password", None)
        save_prefs(base_dir, data)


@profile_transaction
def set_last_vpn_proxy(base_dir, cfg: dict):
    data = load_prefs(base_dir)
    payload = dict(cfg) if isinstance(cfg, dict) else {}
    password = payload.pop("password", None)
    if password is not None:
        if str(password):
            secret_store.set_secret(base_dir, "proxy_password", str(password))
        else:
            secret_store.delete_secret(base_dir, "proxy_password")
    data["vpn_last_proxy"] = payload
    save_prefs(base_dir, data)


def permissions_path(base_dir):
    return os.path.join(base_dir, "permissions.json")


def downloads_list_path(base_dir):
    return os.path.join(base_dir, "downloads_list.json")


def workspaces_path(base_dir):
    return os.path.join(base_dir, "workspaces.json")


def profile_meta_path(base_dir):
    return os.path.join(base_dir, "profile_meta.json")


def ai_index_path(base_dir):
    return os.path.join(base_dir, "ai_index.json")


def ai_settings_path(base_dir):
    return os.path.join(base_dir, "ai_settings.json")


def favicon_cache_dir(base_dir):
    if not base_dir:
        return os.path.join(os.path.expanduser("~"), ".cache", "litebrowser", "favicons")
    path = os.path.join(base_dir, "favicons")
    os.makedirs(path, exist_ok=True)
    return path


_ensure_layout_done: set[str] = set()


def ensure_profile_layout(base_dir):
    # Fast path: a profile already laid out in this process skips the 5
    # makedirs syscalls + profile-meta parse that every save_prefs used to
    # repeat (v6.5 audit: save_prefs → ensure_profile_layout on every toggle).
    if base_dir in _ensure_layout_done:
        return base_dir
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(vault_path(base_dir), exist_ok=True)
    os.makedirs(ext_path(base_dir), exist_ok=True)
    os.makedirs(favicon_cache_dir(base_dir), exist_ok=True)
    os.makedirs(app_paths.browser_data_path(base_dir), exist_ok=True)
    os.makedirs(app_paths.downloads_dir(base_dir), exist_ok=True)
    with profile_locked(base_dir):
        meta = load_profile_meta(base_dir)
        if int(meta.get("schema_version", 0) or 0) < app_paths.APP_SCHEMA_VERSION:
            meta["schema_version"] = app_paths.APP_SCHEMA_VERSION
            write_json(profile_meta_path(base_dir), meta)
        prefs_data = load_prefs(base_dir)
        if int(prefs_data.get("schema_version", 0) or 0) < app_paths.APP_SCHEMA_VERSION:
            prefs_data["schema_version"] = app_paths.APP_SCHEMA_VERSION
            write_json(_prefs_path(base_dir), prefs_data)
    _ensure_layout_done.add(base_dir)
    return base_dir


def load_profile_meta(base_dir):
    data = read_json(profile_meta_path(base_dir), {"schema_version": app_paths.APP_SCHEMA_VERSION})
    if not isinstance(data, dict):
        return {"schema_version": app_paths.APP_SCHEMA_VERSION}
    data.setdefault("schema_version", app_paths.APP_SCHEMA_VERSION)
    return data


# Every get_*/set_* pref helper funnels through load_prefs, which previously
# re-opened and re-parsed prefs.json from disk on every call (theme, accent,
# bridge settings, tab prefs, ...). Cache the parsed dict keyed by the file's
# mtime+size so repeated reads are in-memory; callers get a deep copy so nobody
# can accidentally mutate the cached value.
_prefs_cache: dict[str, tuple[int, int, dict]] = {}
# The deep copy is itself expensive for the many small scalar getters (every
# tab hover palette lookup deep-copied the whole prefs tree). Keep one copy
# per signature: it is regenerated only when the file changes, and every
# getter still receives its own mutable copy.
_prefs_copy_cache: dict[str, tuple[int, int, dict]] = {}


def _deep_copy_prefs(base_dir, signature, data):
    cached = _prefs_copy_cache.get(base_dir)
    if cached is not None and cached[0] == signature[0] and cached[1] == signature[1]:
        return copy.deepcopy(cached[2])
    copy_result = copy.deepcopy(data)
    _prefs_copy_cache[base_dir] = (signature[0], signature[1], copy_result)
    return copy.deepcopy(copy_result)


def load_prefs(base_dir):
    path = _prefs_path(base_dir)
    try:
        st = os.stat(path)
        signature = (st.st_mtime_ns, st.st_size)
    except OSError:
        _prefs_cache.pop(base_dir, None)
        _prefs_copy_cache.pop(base_dir, None)
        return {}
    cached = _prefs_cache.get(base_dir)
    if cached is not None and cached[0] == signature[0] and cached[1] == signature[1]:
        return _deep_copy_prefs(base_dir, signature, cached[2])
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", app_paths.APP_SCHEMA_VERSION)
    _prefs_cache[base_dir] = (signature[0], signature[1], data)
    return _deep_copy_prefs(base_dir, signature, data)


@profile_transaction
def save_prefs(base_dir, data):
    _prefs_cache.pop(base_dir, None)
    _prefs_copy_cache.pop(base_dir, None)
    with profile_locked(base_dir):
        ensure_profile_layout(base_dir)
        payload = dict(data or {})
        payload["schema_version"] = int(payload.get("schema_version", app_paths.APP_SCHEMA_VERSION) or app_paths.APP_SCHEMA_VERSION)
        write_json(_prefs_path(base_dir), payload)
    _prefs_cache.pop(base_dir, None)
    _prefs_copy_cache.pop(base_dir, None)


def get_https_only(base_dir):
    # Default ON: HTTPS-only is the modern safe baseline. localhost and explicit
    # http:// URLs the user types are still allowed via the interceptor; this
    # only blocks accidental cleartext loads (mixed-content sub-resources, etc.).
    return bool(load_prefs(base_dir).get("https_only", True))


@profile_transaction
def set_https_only(base_dir, value):
    data = load_prefs(base_dir)
    data["https_only"] = bool(value)
    save_prefs(base_dir, data)


# Single registry for every search engine: the one source of truth shared by
# the address bar, the new-tab page, and prefs validation. Add a new engine
# here and it appears everywhere automatically.
SEARCH_ENGINES = {
    "Google": {"home": "https://www.google.com/", "search": "https://www.google.com/search?q={q}"},
    "Startpage": {"home": "https://www.startpage.com/", "search": "https://www.startpage.com/search?q={q}"},
    "DuckDuckGo": {"home": "https://duckduckgo.com/", "search": "https://duckduckgo.com/?q={q}"},
    "Bing": {"home": "https://www.bing.com/", "search": "https://www.bing.com/search?q={q}"},
    "Brave Search": {"home": "https://search.brave.com/", "search": "https://search.brave.com/search?q={q}"},
    "Ecosia": {"home": "https://www.ecosia.org/", "search": "https://www.ecosia.org/search?q={q}"},
}
SEARCH_ENGINE_NAMES = tuple(SEARCH_ENGINES.keys())
DEFAULT_SEARCH_ENGINE = "Google"


def search_engine_search_template(name):
    """Raw query URL template (``...?q={q}``) for the named engine."""
    engine = SEARCH_ENGINES.get(name, SEARCH_ENGINES[DEFAULT_SEARCH_ENGINE])
    return engine["search"]


def search_engine_home_url(name):
    engine = SEARCH_ENGINES.get(name, SEARCH_ENGINES[DEFAULT_SEARCH_ENGINE])
    return engine["home"]


def search_engine_query_url(name, query):
    """Fully-encoded search URL for the named engine and query."""
    from urllib.parse import quote_plus
    return search_engine_search_template(name).replace("{q}", quote_plus(str(query or "")))


def get_search_engine(base_dir):
    name = load_prefs(base_dir).get("search_engine", DEFAULT_SEARCH_ENGINE)
    return name if name in SEARCH_ENGINES else DEFAULT_SEARCH_ENGINE


@profile_transaction
def set_search_engine(base_dir, name):
    data = load_prefs(base_dir)
    data["search_engine"] = name if name in SEARCH_ENGINES else DEFAULT_SEARCH_ENGINE
    save_prefs(base_dir, data)


def get_accent(base_dir):
    # The fallback is the product's default accent, not a literal: a profile
    # that never chose one follows the design system (see theme_data).
    default = _theme_mod.DEFAULT_ACCENT
    name = load_prefs(base_dir).get("accent", default)
    return name if _theme_mod.valid_accent(name) else default


@profile_transaction
def set_accent(base_dir, name):
    data = load_prefs(base_dir)
    default = _theme_mod.DEFAULT_ACCENT
    data["accent"] = name if _theme_mod.valid_accent(name) else default
    save_prefs(base_dir, data)


def get_shell_theme(base_dir):
    name = load_prefs(base_dir).get("shell_theme", _theme_mod.DEFAULT_THEME)
    return name if name in _theme_mod.PALETTES else _theme_mod.DEFAULT_THEME


def get_pref(base_dir, key, default=None):
    """Generic single pref read for one-off flags (onboarding, experiments)."""
    return load_prefs(base_dir).get(key, default)


@profile_transaction
def save_pref(base_dir, key, value):
    data = load_prefs(base_dir)
    data[key] = value
    save_prefs(base_dir, data)


def get_auto_theme(base_dir) -> bool:
    """When on, the café flips between day and night palettes with the clock."""
    return bool(load_prefs(base_dir).get("auto_theme", False))


@profile_transaction
def set_auto_theme(base_dir, value):
    data = load_prefs(base_dir)
    data["auto_theme"] = bool(value)
    save_prefs(base_dir, data)


def resolved_auto_theme(base_dir):
    """Effective theme id honoring auto day/night: day palettes 6-18h, night
    otherwise. Pairs each user theme with its sibling (minimal <-> minimal-night
    etc.); unknown pairs resolve to the plain default."""
    theme_id = get_shell_theme(base_dir)
    appearance = get_pref(base_dir, "appearance_mode", "palette")
    if appearance in ("light", "dark", "system"):
        dark = appearance == "dark"
        if appearance == "system":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                    dark = not bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
            except (ImportError, OSError):
                dark = False
        return _theme_mod.theme_variant(theme_id, dark)
    if not get_auto_theme(base_dir):
        return theme_id


    hour = time.localtime().tm_hour
    day_mode = 6 <= hour < 18
    pairs = {
        "minimal": ("minimal", "minimal-night"),
        "latte": ("latte", "minimal-night"),
        "rose-day": ("rose-day", "midnight-ember"),
        "dawn": ("dawn", "cafe-night"),
        "matcha-day": ("matcha-day", "forest-night"),
        "sand-day": ("sand-day", "ocean-night"),
        "lavender-day": ("lavender-day", "lavender-night"),
        "cocoa-day": ("cocoa-day", "mocha-mint"),
        # 2026 pass: weather + time-of-day themes. The night half of each pair is
        # listed as its own key too, so picking "Rainy Night" and leaving auto on
        # cannot silently slide back to a different night theme.
        "rain-day": ("rain-day", "rain-night"),
        "rain-night": ("rain-day", "rain-night"),
        "sunrise-day": ("sunrise-day", "midnight-ember"),
        "autumn-day": ("autumn-day", "cafe-night"),
    }
    day, night = pairs.get(theme_id, (_theme_mod.theme_variant(theme_id, False), _theme_mod.theme_variant(theme_id, True)))
    return day if day_mode else night


def _system_reduced_motion() -> bool:
    """Read Windows' client-area animation preference when it is available.

    Other platforms keep motion enabled unless the user chooses Reduce. The
    explicit setting remains available everywhere, including systems whose
    accessibility API is not exposed by the current Qt binding.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes

        enabled = ctypes.c_int()
        # SPI_GETCLIENTAREAANIMATION; false means Windows asks apps to reduce
        # or disable client-area movement and fade effects.
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x1042, 0, ctypes.byref(enabled), 0
        )
        return bool(ok) and not bool(enabled.value)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def reduced_motion_enabled(base_dir) -> bool:
    """Whether nonessential Mei animations should be removed for this profile."""
    if not base_dir:
        return _system_reduced_motion()
    mode = get_pref(base_dir, "reduced_motion", "system")
    if mode == "reduce":
        return True
    if mode == "allow":
        return False
    return _system_reduced_motion()


_MOTION_DURATIONS_MS = {
    "micro": 100,
    "standard": 160,
    "workspace": 240,
    "dialog": 180,
}


def motion_duration_ms(base_dir, transition: str = "standard") -> int:
    """Return a shared transition duration, or zero under reduced motion."""
    duration = _MOTION_DURATIONS_MS.get(transition, _MOTION_DURATIONS_MS["standard"])
    return 0 if reduced_motion_enabled(base_dir) else duration


DEFAULT_BASE_DIR = ""


@profile_transaction
def set_default_base_dir(base_dir: str):
    """Remember the primary profile dir for theme lookups without a profile."""
    global DEFAULT_BASE_DIR
    DEFAULT_BASE_DIR = base_dir or ""


@profile_transaction
def set_shell_theme(base_dir, name):
    data = load_prefs(base_dir)
    fallback = _theme_mod.DEFAULT_THEME
    data["shell_theme"] = name if name in _theme_mod.PALETTES else fallback
    save_prefs(base_dir, data)


# Per-host zoom factors, e.g. {"mp3.com": 1.2, "exmaple.org": 0.9}. Applied when a
# page for that host loads; the browser keeps the "default" magnification otherwise.
def get_site_zoom_map(base_dir):
    raw = load_prefs(base_dir).get("site_zoom", {})
    return raw if isinstance(raw, dict) else {}


@profile_transaction
def set_site_zoom(base_dir, host, factor):
    data = load_prefs(base_dir)
    zooms = data.get("site_zoom", {})
    if not isinstance(zooms, dict):
        zooms = {}
    host_key = (host or "").strip().lower()
    if not host_key:
        return
    if factor is None or factor <= 0:
        zooms.pop(host_key, None)
    else:
        zooms[host_key] = round(float(factor), 2)
    data["site_zoom"] = zooms
    save_prefs(base_dir, data)


def get_site_zoom(base_dir, host):
    if not host:
        return None
    zooms = get_site_zoom_map(base_dir)
    return zooms.get(host.lower())


def get_password_manager_enabled(base_dir):
    return bool(load_prefs(base_dir).get("password_manager_enabled", False))


@profile_transaction
def set_password_manager_enabled(base_dir, value):
    data = load_prefs(base_dir)
    data["password_manager_enabled"] = bool(value)
    save_prefs(base_dir, data)


def get_autofill_passwords(base_dir):
    return bool(load_prefs(base_dir).get("autofill_passwords", False))


@profile_transaction
def set_autofill_passwords(base_dir, value):
    data = load_prefs(base_dir)
    data["autofill_passwords"] = bool(value)
    save_prefs(base_dir, data)


def effective_force_dark_web(base_dir) -> bool:
    """Whether web pages should be darkened right now.

    An explicit choice (the user has flipped the menu item at least once) always
    wins. Until then pages follow the shell: a night palette — a night theme, or
    auto day/night after 18:00 — darkens pages too, so a dark window no longer
    frames a blinding white page.
    """
    raw = load_prefs(base_dir).get("force_dark_web")
    if raw is not None:
        return bool(raw)
    return _theme_mod.is_night_theme(resolved_auto_theme(base_dir))


@profile_transaction
def set_force_dark_web(base_dir, value):
    data = load_prefs(base_dir)
    data["force_dark_web"] = bool(value)
    save_prefs(base_dir, data)


def get_text_highlight_enabled(base_dir):
    """Highlight-selected-text + copy bubble helper (on by default)."""
    return bool(load_prefs(base_dir).get("text_highlight_enabled", True))


@profile_transaction
def set_text_highlight_enabled(base_dir, value):
    data = load_prefs(base_dir)
    data["text_highlight_enabled"] = bool(value)
    save_prefs(base_dir, data)


def get_ui_dynamic_background(base_dir):
    return bool(load_prefs(base_dir).get("ui_dynamic_background", False))


@profile_transaction
def set_ui_dynamic_background(base_dir, value):
    data = load_prefs(base_dir)
    data["ui_dynamic_background"] = bool(value)
    save_prefs(base_dir, data)


def get_last_web_panel(base_dir):
    """(title, url) of the most recently used web panel, or ("", "")."""
    data = load_prefs(base_dir).get("web_panel", {})
    if isinstance(data, dict):
        return str(data.get("title") or ""), str(data.get("url") or "")
    return "", ""


@profile_transaction
def set_last_web_panel(base_dir, title, url):
    data = load_prefs(base_dir)
    data["web_panel"] = {"title": str(title or ""), "url": str(url or ""), "visible": True}
    save_prefs(base_dir, data)


def get_web_panel_visible(base_dir):
    data = load_prefs(base_dir).get("web_panel", {})
    return bool(data.get("visible")) if isinstance(data, dict) else False


@profile_transaction
def set_web_panel_visible(base_dir, value):
    data = load_prefs(base_dir)
    panel = data.get("web_panel") if isinstance(data.get("web_panel"), dict) else {}
    panel["visible"] = bool(value)
    data["web_panel"] = panel
    save_prefs(base_dir, data)


def get_adblock_filter_file(base_dir):
    return load_prefs(base_dir).get("adblock_filter_file", "")


@profile_transaction
def set_adblock_filter_file(base_dir, path):
    data = load_prefs(base_dir)
    data["adblock_filter_file"] = path or ""
    save_prefs(base_dir, data)


def get_passcode_record(base_dir):
    d = load_prefs(base_dir)
    return d.get("passcode_salt", ""), d.get("passcode_hash", ""), int(d.get("passcode_rounds", 0) or 0)


@profile_transaction
def set_passcode_record(base_dir, salt_b64, hash_b64, rounds):
    data = load_prefs(base_dir)
    data["passcode_salt"] = salt_b64 or ""
    data["passcode_hash"] = hash_b64 or ""
    data["passcode_rounds"] = int(rounds or 0)
    save_prefs(base_dir, data)


def get_personal_root(base_dir):
    return load_prefs(base_dir).get("personal_root", "")


@profile_transaction
def set_personal_root(base_dir, path):
    data = load_prefs(base_dir)
    data["personal_root"] = path or ""
    save_prefs(base_dir, data)


def get_personal_sites(base_dir):
    sites = load_prefs(base_dir).get("personal_sites", [])
    return sites if isinstance(sites, list) else []


@profile_transaction
def save_personal_sites(base_dir, sites):
    data = load_prefs(base_dir)
    data["personal_sites"] = sites if isinstance(sites, list) else []
    save_prefs(base_dir, data)


@profile_transaction
def add_personal_site(base_dir, url, title=""):
    url = (url or "").strip()
    if not url:
        return False
    sites = get_personal_sites(base_dir)
    for item in sites:
        if (item.get("url") or "").strip() == url:
            if title:
                item["title"] = title
                save_personal_sites(base_dir, sites)
            return True
    sites.append({"url": url, "title": title or ""})
    save_personal_sites(base_dir, sites)
    return True


@profile_transaction
def remove_personal_site(base_dir, url):
    url = (url or "").strip()
    if not url:
        return False
    save_personal_sites(base_dir, [item for item in get_personal_sites(base_dir) if (item.get("url") or "").strip() != url])
    return True


def get_show_bundled_sites(base_dir) -> bool:
    """Whether Personal → Sites should also list the bundled/remote project
    sites. Fresh profiles (only auto-seeded links, nothing the user added)
    default to off so first entry shows an empty "Add site" state instead of
    a forced shelf; profiles the user already curates keep them visible."""
    data = load_prefs(base_dir)
    if "show_bundled_sites" in data:
        return bool(data["show_bundled_sites"])
    from litebrowser.core import app_paths as _paths

    bundled_urls = {
        (site.get("url") or "").strip()
        for site in _paths.bundled_sites() + _paths.chain_remote_sites()
        if site.get("url")
    }
    user_sites = [s for s in get_personal_sites(base_dir) if (s.get("url") or "").strip() not in bundled_urls]
    return bool(user_sites)


@profile_transaction
def set_show_bundled_sites(base_dir, value):
    data = load_prefs(base_dir)
    data["show_bundled_sites"] = bool(value)
    save_prefs(base_dir, data)


def load_permissions(base_dir):
    data = read_json(permissions_path(base_dir), {})
    return data if isinstance(data, dict) else {}


@profile_transaction
def save_permissions(base_dir, perms):
    with profile_locked(base_dir):
        write_json(permissions_path(base_dir), perms)


def get_permission(base_dir, origin, feature):
    return load_permissions(base_dir).get(origin, {}).get(feature)


@profile_transaction
def set_permission(base_dir, origin, feature, policy):
    perms = load_permissions(base_dir)
    perms.setdefault(origin, {})
    perms[origin][feature] = policy
    save_permissions(base_dir, perms)


def get_startup_prefs(base_dir):
    d = load_prefs(base_dir)
    return d.get("startup_mode", "restore"), d.get("home_url", "https://google.com") or "https://google.com"


def get_hibernate_seconds(base_dir):
    return int(load_prefs(base_dir).get("hibernate_seconds", 300))


@profile_transaction
def save_hibernate_seconds(base_dir, seconds):
    data = load_prefs(base_dir)
    data["hibernate_seconds"] = int(seconds or 0)
    save_prefs(base_dir, data)


def get_defer_background_tabs(base_dir):
    """Load background tabs lazily (dormant placeholder, no renderer/network)

    until the user actually selects them. On = the active tab keeps full network
    and CPU priority; off = background tabs warm up a renderer immediately.
    """
    return bool(load_prefs(base_dir).get("defer_background_tabs", True))


@profile_transaction
def set_defer_background_tabs(base_dir, value):
    data = load_prefs(base_dir)
    data["defer_background_tabs"] = bool(value)
    save_prefs(base_dir, data)


def get_max_live_tabs(base_dir):
    """How many live (non-hibernated) renderers to keep before suspending tabs.

    Lower = lighter on RAM/CPU when hundreds of tabs are open; higher = more
    tabs stay instantly ready in the background.
    """
    try:
        value = int(load_prefs(base_dir).get("max_live_tabs", 6))
    except (TypeError, ValueError):
        value = 6
    return max(1, min(32, value))


@profile_transaction
def set_max_live_tabs(base_dir, value):
    data = load_prefs(base_dir)
    try:
        data["max_live_tabs"] = max(1, min(32, int(value)))
    except (TypeError, ValueError):
        data["max_live_tabs"] = 6
    save_prefs(base_dir, data)


def get_new_tab_steam(base_dir):
    """Show the animated steam on the new-tab café cup."""
    return bool(load_prefs(base_dir).get("new_tab_steam", True))


@profile_transaction
def set_new_tab_steam(base_dir, value):
    data = load_prefs(base_dir)
    data["new_tab_steam"] = bool(value)
    save_prefs(base_dir, data)


def get_new_tab_greeting(base_dir):
    """Show the time-of-day café greeting on the new-tab hero."""
    return bool(load_prefs(base_dir).get("new_tab_greeting", True))


@profile_transaction
def set_new_tab_greeting(base_dir, value):
    data = load_prefs(base_dir)
    data["new_tab_greeting"] = bool(value)
    save_prefs(base_dir, data)


def get_show_morning_brief(base_dir):
    """Show the Morning Brief card on the Home dashboard."""
    return bool(load_prefs(base_dir).get("show_morning_brief", True))


@profile_transaction
def set_show_morning_brief(base_dir, value):
    data = load_prefs(base_dir)
    data["show_morning_brief"] = bool(value)
    save_prefs(base_dir, data)


def get_study_reminder_minutes(base_dir):
    """How often Mei may start a study nudge. 0 disables the proactivity.

    Default 120: often enough that a student notices the app is watching the
    day for them, rare enough that it never feels like a nag. The loop itself
    applies the quiet hours and never talks over a running pour.
    """
    try:
        value = int(load_prefs(base_dir).get("study_reminder_minutes", 120))
    except (TypeError, ValueError):
        value = 120
    return max(0, min(480, value))


@profile_transaction
def set_study_reminder_minutes(base_dir, value):
    data = load_prefs(base_dir)
    try:
        data["study_reminder_minutes"] = max(0, min(480, int(value)))
    except (TypeError, ValueError):
        data["study_reminder_minutes"] = 120
    save_prefs(base_dir, data)


def get_sync_endpoint(base_dir):
    return str(load_prefs(base_dir).get("sync_endpoint", "") or "").strip()


@profile_transaction
def set_sync_endpoint(base_dir, value):
    data = load_prefs(base_dir)
    data["sync_endpoint"] = str(value or "").strip()
    save_prefs(base_dir, data)


@profile_transaction
def _drop_plaintext_pref(base_dir, key):
    data = load_prefs(base_dir)
    if key in data:
        data.pop(key, None)
        save_prefs(base_dir, data)


def get_sync_token(base_dir):
    secured = secret_store.get_secret(base_dir, "sync_token")
    if secured is not None:
        return secured.strip()
    legacy = str(load_prefs(base_dir).get("sync_token", "") or "").strip()
    if legacy:
        return secret_store.adopt(
            base_dir,
            "sync_token",
            legacy,
            lambda: _drop_plaintext_pref(base_dir, "sync_token"),
        ).strip()
    return ""


@profile_transaction
def set_sync_token(base_dir, value):
    secret_store.set_secret(base_dir, "sync_token", str(value or "").strip())
    # Only after the protected write succeeded: remove the old plaintext copy. If
    # set_secret raised, the legacy value (if any) is still where it was.
    data = load_prefs(base_dir)
    if "sync_token" in data:
        data.pop("sync_token", None)
        save_prefs(base_dir, data)


def get_sync_enabled(base_dir):
    return bool(load_prefs(base_dir).get("sync_enabled", False))


@profile_transaction
def set_sync_enabled(base_dir, value):
    data = load_prefs(base_dir)
    data["sync_enabled"] = bool(value)
    save_prefs(base_dir, data)


def get_browser_data_saver(base_dir):
    """Whether new page loads should avoid heavyweight image transfers."""
    return bool(load_prefs(base_dir).get("browser_data_saver", False))


@profile_transaction
def set_browser_data_saver(base_dir, enabled):
    data = load_prefs(base_dir)
    data["browser_data_saver"] = bool(enabled)
    save_prefs(base_dir, data)


def get_disable_webgl(base_dir):
    """Lite rendering: turn off WebGL so heavy shader/3D sites stop dragging
    software/weak GPUs. Most sites (incl. LinkLumina) fall back gracefully."""
    return bool(load_prefs(base_dir).get("disable_webgl", False))


@profile_transaction
def set_disable_webgl(base_dir, enabled):
    data = load_prefs(base_dir)
    data["disable_webgl"] = bool(enabled)
    save_prefs(base_dir, data)


def get_block_third_party_cookies(base_dir):
    # Default ON: matches what major browsers (Brave/Firefox/Safari) ship today.
    # Compatibility hosts (Google sign-in, Microsoft, etc.) are still allowed
    # via the interceptor's allowlist so OAuth and embedded login flows work.
    return bool(load_prefs(base_dir).get("block_third_party_cookies", True))


@profile_transaction
def set_block_third_party_cookies(base_dir, value):
    data = load_prefs(base_dir)
    data["block_third_party_cookies"] = bool(value)
    save_prefs(base_dir, data)


def get_strict_referrer(base_dir):
    """Send only the origin (no path) on cross-site requests."""
    return bool(load_prefs(base_dir).get("strict_referrer", True))


@profile_transaction
def set_strict_referrer(base_dir, value):
    data = load_prefs(base_dir)
    data["strict_referrer"] = bool(value)
    save_prefs(base_dir, data)


def get_strip_client_hints(base_dir):
    """Strip Sec-CH-UA-Platform-Version and other low-entropy extras outside
    the compatibility allowlist. Reduces fingerprint entropy for tracking sites
    while keeping enough hints for Google/Microsoft sign-in to succeed."""
    return bool(load_prefs(base_dir).get("strip_client_hints", True))


@profile_transaction
def set_strip_client_hints(base_dir, value):
    data = load_prefs(base_dir)
    data["strip_client_hints"] = bool(value)
    save_prefs(base_dir, data)


def get_chrome_compat_shim(base_dir):
    return bool(load_prefs(base_dir).get("chrome_compat_shim", True))


@profile_transaction
def set_chrome_compat_shim(base_dir, value):
    data = load_prefs(base_dir)
    data["chrome_compat_shim"] = bool(value)
    save_prefs(base_dir, data)


def get_adblock_subscriptions(base_dir):
    data = load_prefs(base_dir).get("adblock_subscriptions", [])
    return data if isinstance(data, list) else []


@profile_transaction
def set_adblock_subscriptions(base_dir, value):
    data = load_prefs(base_dir)
    data["adblock_subscriptions"] = value if isinstance(value, list) else []
    save_prefs(base_dir, data)


def session_load(base_dir):
    data = read_json(session_path(base_dir), [])
    if isinstance(data, dict):
        tabs = data.get("tabs", [])
        return tabs if isinstance(tabs, list) else []
    return data if isinstance(data, list) else []


def session_save(base_dir, urls):
    with profile_locked(base_dir):
        write_json(session_path(base_dir), urls if isinstance(urls, list) else [])


def session_state_load(base_dir):
    data = read_json(session_path(base_dir), {"version": 2, "tabs": [], "recently_closed": []})
    if isinstance(data, list):
        return {
            "version": 2,
            "tabs": [{"url": url, "title": "", "icon": "", "hibernated": True, "active": False} for url in data if isinstance(url, str)],
            "recently_closed": [],
        }
    if not isinstance(data, dict):
        return {"version": 2, "tabs": [], "recently_closed": []}
    data.setdefault("version", 2)
    data.setdefault("tabs", [])
    data.setdefault("recently_closed", [])
    if not isinstance(data["tabs"], list):
        data["tabs"] = []
    if not isinstance(data["recently_closed"], list):
        data["recently_closed"] = []
    return data


def session_state_save(base_dir, state, *, window_slot=None):
    # The read-modify-write must sit inside the lock: v6.4 read the file
    # BEFORE acquiring it, so two windows (or the bridge thread) saving
    # concurrently could silently drop each other's recently_closed/tabs.
    with profile_locked(base_dir):
        payload = session_state_load(base_dir)
        if isinstance(state, dict):
            incoming = dict(state)
            if window_slot and "tabs" in incoming:
                legacy_workspace = "ws2" if window_slot == "secondary" else "ws1"
                kept = [tab for tab in payload.get("tabs", []) if isinstance(tab, dict) and (
                    tab.get("window_slot") != window_slot if tab.get("window_slot") else
                    tab.get("workspace_id", "ws1") != legacy_workspace
                )]
                incoming["tabs"] = kept + [{**tab, "window_slot": window_slot} for tab in incoming["tabs"] if isinstance(tab, dict)]
            payload.update(incoming)
        payload["version"] = 2
        payload["tabs"] = payload.get("tabs", []) if isinstance(payload.get("tabs", []), list) else []
        payload["recently_closed"] = payload.get("recently_closed", []) if isinstance(payload.get("recently_closed", []), list) else []
        write_json(session_path(base_dir), payload)


def load_history_entries(base_dir):
    entries = []
    if os.path.exists(history_path(base_dir)):
        try:
            with open(history_path(base_dir), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if "\t" in line:
                        ts_str, url = line.split("\t", 1)
                        try:
                            ts = int(ts_str)
                        except ValueError:
                            ts = int(time.time())
                    else:
                        ts, url = 0, line
                    entries.append((ts, url))
        except (OSError, ValueError) as exc:
            _log.warning("could not read history for %s: %s", base_dir, exc)
    return entries


@profile_transaction
def save_history_entries(base_dir, entries):
    ensure_profile_layout(base_dir)
    lines = "".join(f"{int(ts or 0)}\t{url}\n" for ts, url in entries)
    with profile_locked(base_dir):
        write_text_atomic(history_path(base_dir), lines)


def append_history_entry(base_dir, url):
    ensure_profile_layout(base_dir)
    with profile_locked(base_dir):
        with open(history_path(base_dir), "a", encoding="utf-8") as f:
            f.write(f"{int(time.time())}\t{url}\n")


def load_bookmarks(base_dir):
    data = read_json(bookmarks_path(base_dir), [])
    return data if isinstance(data, list) else []


@profile_transaction
def save_bookmarks(base_dir, bookmarks):
    with profile_locked(base_dir):
        write_json(bookmarks_path(base_dir), bookmarks if isinstance(bookmarks, list) else [])


def bookmark_folders_path(base_dir):
    return os.path.join(base_dir, "bookmark_folders.json")


def load_bookmark_folders(base_dir):
    data = read_json(bookmark_folders_path(base_dir), [])
    return data if isinstance(data, list) else []


@profile_transaction
def save_bookmark_folders(base_dir, folders):
    with profile_locked(base_dir):
        write_json(bookmark_folders_path(base_dir), folders if isinstance(folders, list) else [])


def _default_workspaces_payload():
    return {
        "workspaces": [
            {"id": "ws1", "name": "Workspace 1"},
            {"id": "ws2", "name": "Workspace 2"},
        ],
        "current_id": "ws1",
    }


def load_workspaces(base_dir):
    data = read_json(workspaces_path(base_dir), _default_workspaces_payload())
    if not isinstance(data, dict):
        return _default_workspaces_payload()
    d = _default_workspaces_payload()
    data.setdefault("workspaces", d["workspaces"])
    data.setdefault("current_id", d["current_id"])
    return data


@profile_transaction
def save_workspaces(base_dir, data):
    with profile_locked(base_dir):
        write_json(workspaces_path(base_dir), data)


def profiles_dir(app_dir):
    return app_paths.profiles_root(app_dir)


def _strip_plaintext_ai_key(base_dir):
    data = read_json(ai_settings_path(base_dir), {})
    if isinstance(data, dict) and "openrouter_api_key" in data:
        data.pop("openrouter_api_key", None)
        write_json(ai_settings_path(base_dir), data)


def load_ai_settings(base_dir):
    data = read_json(
        ai_settings_path(base_dir),
        {
            "provider": "rag",
            "openrouter_api_key": "",
            "openrouter_model": "openai/gpt-4o-mini",
            "openrouter_base_url": "https://openrouter.ai/api/v1/chat/completions",
            "openrouter_app_name": "Mei Cafe",
            "openrouter_site_url": "",
            "ollama_model": "",
            "llama_cpp_url": "http://127.0.0.1:8080/completion",
            "show_sources": True,
        },
    )
    if not isinstance(data, dict):
        data = {}
    legacy = data.pop("openrouter_api_key", "") if "openrouter_api_key" in data else ""
    if isinstance(legacy, str) and legacy:
        secret_store.adopt(
            base_dir,
            "openrouter_api_key",
            legacy,
            lambda: _strip_plaintext_ai_key(base_dir),
        )
    secured = secret_store.get_secret(base_dir, "openrouter_api_key")
    if secured is not None:
        data["openrouter_api_key"] = secured
    elif isinstance(legacy, str) and legacy:
        data["openrouter_api_key"] = legacy
    else:
        data.setdefault("openrouter_api_key", "")
    return data


@profile_transaction
def save_ai_settings(base_dir, settings):
    """Write ordinary AI settings; the provider key lives in the secret store.

    A failure to protect the key raises before the settings file is written, so
    the previous configuration stays intact. A legacy plaintext key is preserved
    in place when protection is unavailable rather than being silently dropped.
    """
    incoming = dict(settings or {})
    provided_key = incoming.pop("openrouter_api_key", None)
    if provided_key is not None:
        secret_store.set_secret(base_dir, "openrouter_api_key", str(provided_key or "").strip())
    secured = secret_store.get_secret(base_dir, "openrouter_api_key")
    with profile_locked(base_dir):
        current = read_json(ai_settings_path(base_dir), {})
        current = current if isinstance(current, dict) else {}
        legacy = current.pop("openrouter_api_key", "") if "openrouter_api_key" in current else ""
        current.update(incoming)
        if provided_key is None and secured is None and isinstance(legacy, str) and legacy:
            # Protection failed earlier; keeping the old value is safer than
            # writing a settings file that has lost the only copy of the key.
            current["openrouter_api_key"] = legacy
        else:
            current.pop("openrouter_api_key", None)
        write_json(ai_settings_path(base_dir), current)


def _last_profile_path(app_dir):
    return app_paths.last_profile_path(app_dir)


def get_last_profile(app_dir):
    path = _last_profile_path(app_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                name = f.read().strip()
            if name and os.path.isdir(os.path.join(profiles_dir(app_dir), name)):
                return name
        except OSError as exc:
            _log.warning("could not read last-profile marker: %s", exc)
    return None


@profile_transaction
def set_last_profile(app_dir, name):
    # Atomic write: a crash mid-write left an empty file (fell back to None).
    write_text_atomic(_last_profile_path(app_dir), (name or "").strip() + "\n")


def list_profiles(app_dir):
    pd = profiles_dir(app_dir)
    if not os.path.isdir(pd):
        return []
    return sorted([name for name in os.listdir(pd) if os.path.isdir(os.path.join(pd, name)) and not name.startswith(".")])


_PROFILE_NAME_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _safe_profile_name(name: str) -> str:
    """Strip path separators and Windows-forbidden characters: a crafted name
    like '..\\..\\x' must not escape the profiles dir (v6.4 only guarded
    ''/'.'/'..' on delete)."""
    return _PROFILE_NAME_SAFE_RE.sub("-", (name or "").strip())


def create_profile(app_dir, name):
    name = _safe_profile_name(name)
    if not name or name in (".", ".."):
        return False
    path = os.path.join(profiles_dir(app_dir), name)
    if os.path.exists(path):
        return False
    ensure_profile_layout(path)
    return True


def delete_profile(app_dir, name):
    name = _safe_profile_name(name)
    if not name or name in (".", ".."):
        return False
    path = os.path.join(profiles_dir(app_dir), name)
    root = os.path.abspath(profiles_dir(app_dir)) + os.sep
    if not os.path.abspath(path).startswith(root):
        return False
    if not os.path.isdir(path):
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


MOBILE_BRIDGE_DEFAULT_PORT = 18444
MOBILE_BRIDGE_DEFAULT_HOST = "127.0.0.1"
MOBILE_BRIDGE_LAN_HOST = "0.0.0.0"


def get_mobile_bridge_enabled(base_dir):
    return bool(load_prefs(base_dir).get("mobile_bridge_enabled", False))


@profile_transaction
def set_mobile_bridge_enabled(base_dir, value):
    data = load_prefs(base_dir)
    data["mobile_bridge_enabled"] = bool(value)
    save_prefs(base_dir, data)


def get_mobile_bridge_host(base_dir):
    h = (load_prefs(base_dir).get("mobile_bridge_host") or MOBILE_BRIDGE_DEFAULT_HOST).strip()
    return h if h else MOBILE_BRIDGE_DEFAULT_HOST


@profile_transaction
def set_mobile_bridge_host(base_dir, host):
    data = load_prefs(base_dir)
    data["mobile_bridge_host"] = (host or MOBILE_BRIDGE_DEFAULT_HOST).strip() or MOBILE_BRIDGE_DEFAULT_HOST
    save_prefs(base_dir, data)


def get_mobile_bridge_port(base_dir):
    try:
        p = int(load_prefs(base_dir).get("mobile_bridge_port", MOBILE_BRIDGE_DEFAULT_PORT))
    except (TypeError, ValueError):
        p = MOBILE_BRIDGE_DEFAULT_PORT
    return max(1, min(65535, p))


@profile_transaction
def set_mobile_bridge_port(base_dir, port):
    data = load_prefs(base_dir)
    try:
        p = int(port)
    except (TypeError, ValueError):
        p = MOBILE_BRIDGE_DEFAULT_PORT
    data["mobile_bridge_port"] = max(1, min(65535, p))
    save_prefs(base_dir, data)


def get_mobile_bridge_token(base_dir):
    secured = secret_store.get_secret(base_dir, "mobile_bridge_token")
    if secured is not None:
        return secured.strip()
    legacy = (load_prefs(base_dir).get("mobile_bridge_token") or "").strip()
    if legacy:
        return secret_store.adopt(
            base_dir,
            "mobile_bridge_token",
            legacy,
            lambda: _drop_plaintext_pref(base_dir, "mobile_bridge_token"),
        ).strip()
    return ""


def generate_mobile_bridge_token():
    return secrets.token_urlsafe(32)


@profile_transaction
def set_mobile_bridge_token(base_dir, token):
    value = (token or "").strip()
    secret_store.set_secret(base_dir, "mobile_bridge_token", value)
    data = load_prefs(base_dir)
    if "mobile_bridge_token" in data:
        data.pop("mobile_bridge_token", None)
        save_prefs(base_dir, data)


@profile_transaction
def ensure_mobile_bridge_token(base_dir):
    token = get_mobile_bridge_token(base_dir)
    if token:
        return token
    token = generate_mobile_bridge_token()
    set_mobile_bridge_token(base_dir, token)
    return token


def get_mobile_bridge_lan(base_dir):
    return get_mobile_bridge_host(base_dir) == MOBILE_BRIDGE_LAN_HOST


@profile_transaction
def set_mobile_bridge_lan(base_dir, lan_enabled):
    set_mobile_bridge_host(base_dir, MOBILE_BRIDGE_LAN_HOST if lan_enabled else MOBILE_BRIDGE_DEFAULT_HOST)


def get_show_neural_notes_graph(base_dir):
    return bool(load_prefs(base_dir).get("show_neural_notes_graph", False))


@profile_transaction
def set_show_neural_notes_graph(base_dir, value):
    data = load_prefs(base_dir)
    data["show_neural_notes_graph"] = bool(value)
    save_prefs(base_dir, data)


def get_note_order(base_dir):
    """Manual ordering of note ids (the user's drag-and-drop arrangement)."""
    order = load_prefs(base_dir).get("note_order", [])
    return [str(x) for x in order] if isinstance(order, list) else []


@profile_transaction
def set_note_order(base_dir, order):
    data = load_prefs(base_dir)
    data["note_order"] = [str(x) for x in order] if isinstance(order, list) else []
    save_prefs(base_dir, data)


def get_google_oauth_client_id(base_dir):
    return (load_prefs(base_dir).get("google_oauth_client_id") or "").strip()


@profile_transaction
def set_google_oauth_client_id(base_dir, client_id):
    data = load_prefs(base_dir)
    data["google_oauth_client_id"] = (client_id or "").strip()
    save_prefs(base_dir, data)


def get_google_account(base_dir):
    value = load_prefs(base_dir).get("google_account")
    return value if isinstance(value, dict) else {}


@profile_transaction
def set_google_account(base_dir, account):
    data = load_prefs(base_dir)
    data["google_account"] = account if isinstance(account, dict) else {}
    save_prefs(base_dir, data)


@profile_transaction
def clear_google_account(base_dir):
    secret_store.delete_secret(base_dir, "google_token_cache")
    data = load_prefs(base_dir)
    data.pop("google_account", None)
    data.pop("google_token_cache", None)
    save_prefs(base_dir, data)


def get_google_token_cache(base_dir):
    secured = secret_store.get_secret(base_dir, "google_token_cache")
    if secured:
        try:
            parsed = json.loads(secured)
        except (ValueError, TypeError):
            parsed = None
        return parsed if isinstance(parsed, dict) else {}
    legacy = load_prefs(base_dir).get("google_token_cache")
    if isinstance(legacy, dict) and legacy:
        protected = secret_store.adopt(
            base_dir,
            "google_token_cache",
            json.dumps(legacy, ensure_ascii=False),
            lambda: _drop_plaintext_pref(base_dir, "google_token_cache"),
        )
        try:
            parsed = json.loads(protected)
        except (ValueError, TypeError):
            parsed = None
        return parsed if isinstance(parsed, dict) else {}
    return {}


@profile_transaction
def set_google_token_cache(base_dir, token_cache):
    payload = token_cache if isinstance(token_cache, dict) else {}
    if payload:
        secret_store.set_secret(
            base_dir, "google_token_cache", json.dumps(payload, ensure_ascii=False)
        )
    else:
        secret_store.delete_secret(base_dir, "google_token_cache")
    data = load_prefs(base_dir)
    if "google_token_cache" in data:
        data.pop("google_token_cache", None)
        save_prefs(base_dir, data)
