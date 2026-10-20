"""Drive the app's own engine paths and print one PASS/FAIL line per fact.

The unit suite is service-heavy and its GUI half is offscreen smoke, so a Qt or
Chromium jump can pass every test and still break the *app*: an interceptor whose
signature changed, a profile path that never gets created, a download that never
fires, force-dark that silently stops applying, a UA spoof that keeps claiming an
engine we no longer ship. This is the check that catches those.

Everything is hermetic on purpose — pages are served from a loopback HTTP server,
so the run needs no network and answers the same on a machine that has none:

    .venv/Scripts/python.exe tools/engine_smoke.py

Exit code is non-zero when any fact failed, so CI or a release script can gate on
it. See docs/reports/qt611-spike.md for what it found when the engine last moved.
"""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu --no-sandbox --disable-software-rasterizer"
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RESULTS = {}


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS[name] = {"ok": bool(ok), "detail": str(detail)[:400]}
    print(("PASS " if ok else "FAIL ") + name + ((" — " + str(detail)[:220]) if detail else ""), flush=True)


def note(text: str) -> None:
    """A fact worth printing that is not a pass/fail (e.g. what Qt itself does)."""
    print("INFO " + text[:240], flush=True)


import litebrowser  # noqa: F401,E402  importing the package activates the PyQt5 → PyQt6 shim

from PyQt5 import QtCore, QtWidgets  # noqa: E402
from PyQt5.QtWebEngineCore import (  # noqa: E402
    QWebEngineProfile,
    QWebEngineScript,
    qWebEngineChromiumVersion,
    qWebEngineVersion,
)
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView  # noqa: E402
from litebrowser.browser import adblock, browser_page  # noqa: E402

HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<h1>engine smoke</h1>
<img id="blocked" src="http://doubleclick.net/ad.gif">
<img id="control" src="http://example.com/favicon.ico">
<a id="dl" download="smoke.txt" href="smoke.txt">dl</a>
</body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request noise
        pass


class RecordingBlocker(adblock.TrackingBlocker):
    """The app's interceptor, plus a receipt of every host it was asked about."""

    def __init__(self, base_dir):
        super().__init__(None, base_dir)
        self.seen = []
        self.blocked = []

    def interceptRequest(self, info):
        host = info.requestUrl().host().lower()
        verdict = self._is_blocked_host(host)
        self.seen.append(host)
        if verdict:
            self.blocked.append(host)
        return super().interceptRequest(info)


class FakeInfo:
    """Stands in for the engine's request info so header work is checkable offline."""

    def __init__(self, url):
        self._url = QtCore.QUrl(url)
        self.headers = {}

    def requestUrl(self):
        return self._url

    def setHttpHeader(self, key, value):
        self.headers[bytes(key).decode("latin-1").lower()] = bytes(value).decode("latin-1")

    def redirect(self, url):  # noqa: A003 - matches the Qt signature
        self._redirect = QtCore.QUrl(url).toString()

    def block(self, flag):  # noqa: A003 - matches the Qt signature
        self._blocked = bool(flag)


class Harness(QtCore.QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.profile = None
        self.page = None
        self.blocker = None
        self.downloads = []
        self.loaded = False

    def pump(self, ms: int) -> None:
        deadline = time.time() + (ms / 1000.0)
        while time.time() < deadline:
            self.app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)

    def load_and_wait(self, url: str, page=None, ms: int = 20000) -> bool:
        target = page or self.page
        done = {"ok": False}

        def on_load(ok):
            done["ok"] = bool(ok)

        target.loadFinished.connect(on_load)
        target.load(QtCore.QUrl(url))
        deadline = time.time() + (ms / 1000.0)
        while not done["ok"] and time.time() < deadline:
            self.pump(50)
        target.loadFinished.disconnect(on_load)
        return done["ok"]

    def wait_js(self, script: str, page=None, ms: int = 4000):
        target = page or self.page
        box = {}

        def done(value):
            box["value"] = value

        target.runJavaScript(script, 0, done)
        deadline = time.time() + (ms / 1000.0)
        while "value" not in box and time.time() < deadline:
            self.pump(50)
        return box.get("value")


def set_scheme(app, name: str) -> bool:
    """Force prefers-color-scheme, so the run does not inherit the host desktop."""
    scheme = getattr(QtCore.Qt.ColorScheme, name, None)
    if scheme is None or not hasattr(app.styleHints(), "setColorScheme"):
        return False
    app.styleHints().setColorScheme(scheme)
    return True


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["mei-engine-smoke"])
    tmp = tempfile.mkdtemp(prefix="mei-engine-smoke-")
    base_dir = os.path.join(tmp, "profile")
    os.makedirs(os.path.join(base_dir, "BrowserData"), exist_ok=True)

    for name, body in (("smoke.html", HTML), ("other.html", HTML), ("smoke.txt", "hello-from-smoke\n")):
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as handle:
            handle.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=tmp))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"

    record(
        "the host colour scheme can be pinned for the run",
        set_scheme(app, "Light"),
        f"Light requested, Qt reports {app.styleHints().colorScheme()}",
    )
    record(
        "the PyQt5 import shim resolves WebEngine onto PyQt6",
        "PyQt6" in getattr(QWebEnginePage, "__module__", ""),
        f"QWebEnginePage -> {getattr(QWebEnginePage, '__module__', '?')}",
    )
    chrome = qWebEngineChromiumVersion()
    record("engine version", bool(chrome), f"Qt {qWebEngineVersion()} / Chromium {chrome}")
    raw_ua = QWebEngineProfile.defaultProfile().httpUserAgent() or ""
    ua_chrome = raw_ua.split("Chrome/")[-1].split(" ")[0] if "Chrome/" in raw_ua else "?"
    if chrome not in raw_ua:
        note(f"Qt's own user agent says Chrome/{ua_chrome} while the engine is {chrome} — the binding is the source of truth")

    # The adblock layer spoofs a Chrome UA / client hints so Google sign-in does
    # not reject the built-in browser. It reads the live profile UA, so it must
    # follow the engine rather than a hard-coded number — and it must use the
    # engine's real build, not the UA's truncated one.
    detected_major, detected_full = adblock._detect_chrome_versions()
    record(
        "the UA spoof follows the engine in use",
        detected_major == chrome.split(".")[0],
        f"spoof says Chrome {detected_major} ({detected_full}) vs engine {chrome}",
    )
    record(
        "the spoofed UA carries the real major version",
        f"Chrome/{chrome.split('.')[0]}" in adblock._modern_google_ua(),
        adblock._modern_google_ua(),
    )

    h = Harness(app)
    h.profile = QWebEngineProfile("mei-engine-smoke", None)
    storage = os.path.join(base_dir, "BrowserData", "storage")
    cache = os.path.join(base_dir, "BrowserData", "cache")
    h.profile.setPersistentStoragePath(storage)
    h.profile.setCachePath(cache)
    h.blocker = RecordingBlocker(base_dir)
    h.profile.setUrlRequestInterceptor(h.blocker)

    h.page = QWebEnginePage(h.profile, None)

    def on_download(item):
        try:
            h.downloads.append(item.url().toString() or item.suggestedFileName())
        except Exception as exc:  # noqa: BLE001
            h.downloads.append(f"handler raised {exc!r}")
        item.cancel()

    h.profile.downloadRequested.connect(on_download)

    # Client hints, checked against the engine's own version without a network.
    compat = FakeInfo("https://accounts.google.com/signin")
    h.blocker._apply_compat_headers(compat, "accounts.google.com")
    record(
        "the client hints carry the engine's full version",
        compat.headers.get("sec-ch-ua-full-version") == f'"{chrome}"',
        f"sec-ch-ua-full-version={compat.headers.get('sec-ch-ua-full-version')} vs engine {chrome}",
    )
    record(
        "the client hints are Chrome-shaped, not Qt-shaped",
        "Google Chrome" in compat.headers.get("sec-ch-ua", "") and "Chromium" in compat.headers.get("sec-ch-ua", ""),
        compat.headers.get("sec-ch-ua", ""),
    )

    record("a loopback page loads", h.load_and_wait(origin + "/smoke.html"), origin + "/smoke.html")

    h.pump(2500)
    record(
        "the app's interceptor is called by the engine",
        bool(h.blocker.seen),
        f"{len(h.blocker.seen)} request(s): {sorted(set(h.blocker.seen))[:6]}",
    )
    record(
        "a blocked host is recognised (ads stay blocked)",
        any("doubleclick" in host for host in h.blocker.blocked),
        f"blocked: {h.blocker.blocked[:4]}",
    )
    record(
        "the control host is not blocked",
        any("example.com" in host for host in h.blocker.seen) and not any("example.com" in host for host in h.blocker.blocked),
        f"seen: {[host for host in h.blocker.seen if 'example' in host]}",
    )
    images = h.wait_js(
        "JSON.stringify({b: document.getElementById('blocked').complete && document.getElementById('blocked').naturalWidth === 0,"
        " ua: navigator.userAgent})"
    )
    parsed = json.loads(images) if images else {}
    record("the blocked image really failed to load", parsed.get("b") is True, str(parsed.get("b")))
    record(
        "the page reports the engine in navigator.userAgent",
        chrome.split(".")[0] in str(parsed.get("ua", "")),
        str(parsed.get("ua", ""))[:120],
    )

    # force-dark injects a <style> unless the page already asks for dark. To tell
    # "stood down on purpose" apart from "profile scripts stopped running" — the
    # same empty result — a probe script of our own reports the scheme the engine
    # actually gave the page, and whether DocumentReady scripts ran at all.
    probe = QWebEngineScript()
    probe.setName("mei-engine-smoke-scheme-probe")
    probe.setSourceCode(
        "window.__meiSmokeScheme = (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches)"
        " ? 'dark' : 'light';"
    )
    probe.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    probe.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    h.profile.scripts().insert(probe)

    try:
        browser_page.ensure_forced_dark_script(h.profile, True, base_dir)
        script_count = len(h.profile.scripts())
        record("force-dark installs a profile script", script_count >= 2, f"{script_count} script(s) on the profile")
        set_scheme(app, "Light")
        h.load_and_wait(origin + "/smoke.html")
        h.pump(1500)
        readout = h.wait_js(
            "JSON.stringify({scheme: window.__meiSmokeScheme,"
            " applied: !!document.getElementById('lite-forced-dark'),"
            " bg: getComputedStyle(document.body).backgroundColor})"
        )
        info = json.loads(readout) if readout else {}
        scheme = info.get("scheme")
        record(
            "profile scripts still run at DocumentReady",
            scheme in ("light", "dark"),
            f"probe script reported scheme={scheme!r}",
        )
        already_dark = scheme == "dark"
        record(
            "force-dark matches the scheme the engine reports",
            info.get("applied") is (not already_dark),
            f"engine={scheme} style={'yes' if info.get('applied') else 'no'} body={info.get('bg')}"
            + (" — stood down because the page already asks for dark" if already_dark else ""),
        )
        set_scheme(app, "Dark")
        h.load_and_wait(origin + "/smoke.html")
        h.pump(1500)
        dark_readout = h.wait_js(
            "JSON.stringify({scheme: window.__meiSmokeScheme,"
            " applied: !!document.getElementById('lite-forced-dark')})"
        )
        dark_info = json.loads(dark_readout) if dark_readout else {}
        record(
            "force-dark stands down when the page already asks for dark",
            dark_info.get("scheme") != "dark" or dark_info.get("applied") is False,
            f"engine={dark_info.get('scheme')} style={'yes' if dark_info.get('applied') else 'no'}",
        )
        set_scheme(app, "Light")
    except Exception as exc:  # noqa: BLE001
        record("force-dark installs a profile script", False, repr(exc)[:200])

    # Split view and web panel both put a *second* live page on the same profile,
    # through the app's own page class. That is the shape worth smoking: two
    # renderers at once, both under the profile's scripts, without the compat
    # shim being installed twice.
    before_scripts = len(h.profile.scripts())
    second_view = QWebEngineView()
    second_view.setObjectName("EngineSmokeSplit")
    second_page = None
    try:
        second_page = browser_page.BrowserPage(h.profile, second_view, base_dir, host=None)
        second_view.setPage(second_page)
    except Exception as exc:  # noqa: BLE001
        record("a second page builds on the same profile", False, repr(exc)[:200])
    if second_page is not None:
        record("a second page builds on the same profile", True, "BrowserPage(profile, view)")
        record(
            "the profile's scripts were not duplicated for it",
            len(h.profile.scripts()) == before_scripts,
            f"{before_scripts} -> {len(h.profile.scripts())} script(s)",
        )
        first_ok = h.load_and_wait(origin + "/smoke.html")
        second_ok = h.load_and_wait(origin + "/other.html", page=second_page)
        record(
            "two pages load side by side (split view / web panel shape)",
            first_ok and second_ok,
            f"first={first_ok} second={second_ok}",
        )
        own_urls = h.wait_js("window.location.pathname", page=second_page)
        record(
            "the second page is its own renderer, not a mirror",
            str(own_urls).endswith("/other.html"),
            f"second view is on {own_urls}",
        )
        record(
            "the interceptor sees traffic from both renderers",
            h.blocker.seen.count("127.0.0.1") >= 3,
            f"{h.blocker.seen.count('127.0.0.1')} loopback request(s) so far",
        )
        second_view.close()
        second_page.deleteLater()
        second_view.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        h.pump(300)

    h.page.load(QtCore.QUrl(origin + "/smoke.html"))
    h.pump(1500)
    h.wait_js("document.getElementById('dl').click()")
    h.pump(3000)
    record(
        "a download still reaches the download handler",
        bool(h.downloads),
        f"downloads: {h.downloads[:2]}",
    )
    record(
        "the profile created its storage and cache paths",
        os.path.isdir(storage) or os.path.isdir(cache),
        f"storage={os.path.isdir(storage)} cache={os.path.isdir(cache)}",
    )

    # A page must be destroyed before its profile, not merely queued beside
    # it. Chromium can crash during interpreter teardown if deferred deletes
    # never ran (processEvents alone does not guarantee DeferredDelete).
    h.page.triggerAction(QWebEnginePage.WebAction.Stop)
    h.page.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    h.page = None
    h.profile.setUrlRequestInterceptor(None)
    h.profile.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    h.profile = None
    h.blocker.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    h.blocker = None
    h.pump(300)
    server.shutdown()
    server.server_close()
    shutil.rmtree(tmp, ignore_errors=True)

    failed = [name for name, item in RESULTS.items() if not item["ok"]]
    print("\nSUMMARY " + json.dumps({"failed": failed, "total": len(RESULTS)}), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
