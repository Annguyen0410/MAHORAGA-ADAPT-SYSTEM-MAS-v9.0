"""Application entry: profile selection, WebEngine flags, QApplication, AppShell windows."""
import os
import shutil
import sys
import time
from urllib.parse import unquote


def _force_software_rendering() -> bool:
    """Opt-in only: set LITEBROWSER_SOFTWARE_RENDERING=1 if GPU drivers crash the app."""
    return os.environ.get("LITEBROWSER_SOFTWARE_RENDERING", "").strip().lower() in ("1", "true", "yes")


if _force_software_rendering():
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_ANGLE_PLATFORM", "software")
    # Software fallback (opt-in only) also forces the Qt Quick scene-graph to
    # rasterize on the CPU. Keep the GPU path enabled by default so web content
    # is composited by the GPU like Chrome/Opera instead of the CPU.
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PyQt5.QtCore import QCoreApplication, QTimer, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication, QWidget

from litebrowser.core import app_paths, app_version, log, prefs
from litebrowser.services import android_bridge_service, workspace_manager
from litebrowser.ui.app_shell import AppShell
from litebrowser.ui.dialogs import show_profiles_dialog


def _saved_proxy_chromium_flag(app_dir: str) -> str:
    """Build the --proxy-server flag for QtWebEngine from the active profile's saved VPN.

    QtWebEngine uses Chromium's networking stack; QNetworkProxy.setApplicationProxy()
    only affects QNetworkAccessManager, NOT page loads. To actually route the WebEngine
    through a proxy we have to pass --proxy-server on launch. Returns "" when no proxy
    is enabled so we don't accidentally break browsing.
    """
    try:
        last = prefs.get_last_profile(app_dir)
        if not last:
            return ""
        profile_dir = os.path.join(prefs.profiles_dir(app_dir), last)
        cfg_path = prefs.proxy_config_path(profile_dir)
        if not os.path.isfile(cfg_path):
            return ""
        import json as _json
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = _json.load(fh)
        if not cfg.get("enabled"):
            return ""
        pac_url = str(cfg.get("pac_url") or "").strip()
        if pac_url:
            from urllib.parse import urlsplit
            parsed = urlsplit(pac_url)
            if parsed.scheme in ("http", "https", "file") and not any(c.isspace() for c in pac_url):
                return f"--proxy-pac-url={pac_url}"
            return ""
        host = (cfg.get("host") or "").strip()
        port = int(cfg.get("port") or 0)
        if not host or port <= 0 or port > 65535:
            return ""
        scheme = "socks5" if (cfg.get("type") or "http").lower().startswith("socks") else "http"
        # HTTP proxies: Chromium rejects inline user:pass in the flag, but the
        # proxyAuthenticationRequired handler (browser_page.py) answers the
        # auth challenge with the saved credentials at runtime. SOCKS5 with
        # auth is genuinely unsupported by Chromium flags — warn loudly.
        user = (cfg.get("user") or "").strip()
        if user and scheme == "socks5":
            os.environ["MEI_PROXY_AUTH_WARNING"] = (
                "SOCKS5 with username/password is not supported by Chromium; connect an HTTP proxy for authenticated use."
            )
        return "--proxy-server=%s://%s:%d" % (scheme, host, port)
    except Exception:
        return ""


def _get_profile_dir(app_dir):
    last = prefs.get_last_profile(app_dir)
    profiles_d = prefs.profiles_dir(app_dir)
    if last and os.path.isdir(os.path.join(profiles_d, last)):
        return prefs.ensure_profile_layout(os.path.join(profiles_d, last))
    names = prefs.list_profiles(app_dir)
    if not names:
        prefs.create_profile(app_dir, "Default")
        prefs.set_last_profile(app_dir, "Default")
        return prefs.ensure_profile_layout(os.path.join(profiles_d, "Default"))
    root = QWidget()
    root.setWindowTitle(app_version.APP_NAME)
    root.resize(1, 1)
    root.show()
    show_profiles_dialog(root, app_dir)
    root.close()
    last = prefs.get_last_profile(app_dir)
    if not last and names:
        prefs.set_last_profile(app_dir, names[0])
        last = names[0]
    if not last:
        prefs.create_profile(app_dir, "Default")
        prefs.set_last_profile(app_dir, "Default")
        last = "Default"
    return prefs.ensure_profile_layout(os.path.join(profiles_d, last))


def _cleanup_webengine_cache(profile_dir, force=False):
    """Trim stale/oversized WebEngine GPU caches.

    ``old_GPUCache_*`` are rotated-out snapshots and are always safe to drop.
    The live ``GPUCache`` is only rebuilt when it has grown abnormally large
    (corrupt/oversized caches make startup and first paint stutter); deleting
    it on every launch would just force a slow shader recompile each time.
    """
    data_dir = app_paths.browser_data_path(profile_dir)
    for name in ("old_GPUCache_000", "old_GPUCache_001", "old_GPUCache_002"):
        path = os.path.join(data_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    gpu = os.path.join(data_dir, "GPUCache")
    if not os.path.isdir(gpu):
        return
    if force:
        shutil.rmtree(gpu, ignore_errors=True)
        return
    try:
        total = 0
        for root, _dirs, files in os.walk(gpu):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
    except OSError:
        total = 0
    if total > 300 * 1024 * 1024:
        shutil.rmtree(gpu, ignore_errors=True)


def _write_update_health_marker():
    """Tell the updater this build reached a real GUI startup.

    The previous rollback check looked for *any* process with the executable's
    name, so a second instance (or a stale process) could make a broken build
    look healthy. The swap script sets a one-time token; writing it here — after
    the profile is claimed and both shells exist — is the health condition.
    """
    path = os.environ.pop("MEI_UPDATE_HEALTH_FILE", "").strip()
    token = os.environ.pop("MEI_UPDATE_HEALTH_TOKEN", "").strip()
    if not path or not token:
        return
    try:
        from litebrowser.core.storage_utils import write_text_atomic

        write_text_atomic(path, token)
    except OSError:
        # A health marker is useful, never required for the app to run. The
        # updater's timeout will roll back if it cannot read one.
        pass


def _register_bundled_personal_sites(profile_dir, app_dir):
    """Seed Personal Hub → Sites with the six public project links.

    The local copies remain available through the dedicated bundled-site
    commands, while Personal → Sites points at the deployed versions users can
    open directly and keep updated independently of the browser build.
    """
    remote_sites = [site for site in app_paths.chain_remote_sites(app_dir) if site.get("url")]
    remote_urls = {site["url"].strip() for site in remote_sites}
    bundled_urls = {
        site.get("url", "").strip()
        for site in app_paths.bundled_sites(app_dir)
        if site.get("url")
    }
    legacy_markers = tuple(app_paths.LEGACY_BUNDLED_FOLDER_MARKERS or ())
    for site in list(prefs.get_personal_sites(profile_dir)):
        url = (site.get("url") or "").strip()
        if not url:
            continue
        # Migrate entries created by older builds to the six public defaults,
        # without touching unrelated sites the user added themselves.
        if url in remote_urls:
            # Keep user titles and ordering for already-migrated defaults.
            continue
        if url in bundled_urls:
            prefs.remove_personal_site(profile_dir, url)
            continue
        unquoted_url = unquote(url)
        if any(marker in unquoted_url for marker in legacy_markers):
            prefs.remove_personal_site(profile_dir, url)
    for site in remote_sites:
        prefs.add_personal_site(profile_dir, site["url"], site["display"])


def main(app_dir=None):
    """Run the app. Pass ``app_dir`` when started from repo-root ``browser.py`` shim; else repo root is inferred."""
    _t0 = time.time()
    if app_dir is None:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    smoke_test = "--smoke-test" in sys.argv
    qt_argv = [arg for arg in sys.argv if arg != "--smoke-test"]

    chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    if _force_software_rendering():
        extra_flags = (
            "--disable-gpu "
            "--disable-software-rasterizer "
            "--disable-gpu-shader-disk-cache "
            "--disable-gpu-program-cache "
            "--enable-features=WebRTCPipeWireCapturer "
            "--disable-blink-features=AutomationControlled"
        )
        if extra_flags not in chromium_flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (chromium_flags + " " + extra_flags).strip()
        QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)
    else:
        # AutomationControlled can make some sites treat QtWebEngine as a bot; disabling reduces false blocks.
        extra_flags = "--enable-features=WebRTCPipeWireCapturer --disable-blink-features=AutomationControlled"
        if extra_flags not in chromium_flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (chromium_flags + " " + extra_flags).strip()

    proxy_flag = _saved_proxy_chromium_flag(app_dir)
    if proxy_flag:
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        if proxy_flag not in existing:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (existing + " " + proxy_flag).strip()
    # QtWebEngine requires shared OpenGL contexts, set BEFORE QApplication is
    # constructed (v6.4 skipped this, risking GPU-compositor crashes).
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(qt_argv)
    app.setApplicationName(app_version.APP_NAME)
    app.setApplicationVersion(app_version.APP_VERSION)
    app.setOrganizationName(app_version.APP_NAME)
    font = app.font()
    font.setStyleStrategy(QFont.PreferAntialias)
    # Multi-family fallback: unicode glyph icons (☕ ⚙ ◈ ≣ …) fall back to
    # Segoe UI Symbol / Emoji per character instead of rendering as boxes.
    font.setFamilies(["Segoe UI", "Segoe UI Symbol", "Segoe UI Emoji", "Helvetica Neue", "Arial"])
    app.setFont(font)

    app_paths.data_root(app_dir)
    log.configure(app_dir)
    app_paths.ensure_frozen_web_support_mirrored(app_dir)
    app_paths.ensure_linklumina_user_layout(app_dir)
    app.setWindowIcon(QIcon(os.path.join(app_dir, "icon.png")))
    profile_dir = _get_profile_dir(app_dir)
    prefs.set_default_base_dir(profile_dir)
    # Cross-process profile claim: a second Mei on the SAME profile would
    # silently race every JSON store (pre-0.6.8 bug class). Claim before any
    # data work; a friendly error beats silent corruption.
    from litebrowser.core import profile_lock

    acquired, lock_msg = profile_lock.try_acquire_process_lock(profile_dir)
    if not acquired and os.environ.get("MEI_SMART_RESTART") == "1":
        deadline = time.monotonic() + 45
        while not acquired and time.monotonic() < deadline:
            time.sleep(0.1)
            acquired, lock_msg = profile_lock.try_acquire_process_lock(profile_dir)
    if not acquired:
        from PyQt5.QtWidgets import QMessageBox as _QMB

        _QMB.warning(None, "Mei — profile in use", lock_msg)
        sys.exit(2)
    # VPN auto-connect: re-enable the last proxy before Chromium flags are
    # finalized, so an auto-connected session protects every tab from launch.
    smart_restart = os.environ.pop("MEI_SMART_RESTART", "").strip() == "1"
    restart_reason = os.environ.pop("MEI_RESTART_REASON", "")
    if prefs.get_auto_connect_vpn(profile_dir) and not bool(prefs.get_proxy_config(profile_dir).get("enabled")):
        last = prefs.get_last_vpn_proxy(profile_dir)
        if last.get("host") and int(last.get("port") or 0) > 0:
            prefs.set_proxy_config(profile_dir, last)
    proxy_flag = _saved_proxy_chromium_flag(app_dir)
    if proxy_flag:
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        if proxy_flag not in existing:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (existing + " " + proxy_flag).strip()
    workspace_manager.ensure_dual_workspaces(profile_dir)
    _register_bundled_personal_sites(profile_dir, app_dir)
    _cleanup_webengine_cache(
        profile_dir,
        force=os.environ.get("LITEBROWSER_CLEAN_GPU_CACHE_ON_START", "").strip().lower() in ("1", "true", "yes"),
    )
    windows = [
        AppShell(
            profile_dir,
            app_dir=app_dir,
            window_slot="primary",
            browser_workspace_id=workspace_manager.PRIMARY_WORKSPACE_ID,
        ),
        AppShell(
            profile_dir,
            app_dir=app_dir,
            window_slot="secondary",
            browser_workspace_id=workspace_manager.SECONDARY_WORKSPACE_ID,
        ),
    ]
    for window in windows:
        window.show()
    _write_update_health_marker()
    if smoke_test:
        # Release CI runs the frozen build with a throwaway data root and watches
        # for this marker: it proves the window, profile layout and WebEngine all
        # came up, not merely that the executable started.
        from litebrowser.core.storage_utils import write_text_atomic

        marker = os.environ.get("MEI_SMOKE_MARKER", "").strip()
        if marker:
            write_text_atomic(marker, f"ok {app_version.APP_VERSION}\n")
        QTimer.singleShot(400, app.quit)
    # Cold-start metric (pre-1.0 quality tracking): startup duration to the
    # console so regressions surface immediately during development.
    print(f"Mei {app_version.APP_VERSION} ready in {time.time() - _t0:.2f}s", flush=True)
    if smart_restart:
        # Session restored from the previous instance; surface why we bounced.
        note = restart_reason or "Mei restarted to apply new settings"
        windows[0].browser_page._flash_status(f"⟳ {note}")
    proxy_warning = os.environ.pop("MEI_PROXY_AUTH_WARNING", "")
    if proxy_warning:
        from PyQt5.QtWidgets import QMessageBox as _QMB

        _QMB.warning(windows[0], "VPN", proxy_warning)
    android_bridge_service.start_from_prefs(profile_dir)
    def finish_application():
        android_bridge_service.stop()
        for window in windows:
            if not window._closing:
                window.persist_state()
                window.shutdown()
        # Keep the claim until process exit: running executor jobs can still
        # finish after the GUI quits, and Chromium releases its files at exit.

    app.aboutToQuit.connect(finish_application)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
