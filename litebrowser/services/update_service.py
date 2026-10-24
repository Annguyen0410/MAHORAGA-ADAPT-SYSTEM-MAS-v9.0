"""Self-update: check a product-owned channel, verify the package, install it safely.

The channel can be remote *or* a build dropped next to the exe: put
``update\\update.json`` + ``Mei.exe`` in the folder beside the running build and the
app offers it on the next launch, replaces itself, keeps one ``.bak`` for rollback
and deletes the old build to free the space back.

Three guarantees this module now enforces (each one was violated before):

1. **Channel ownership** — the metadata must declare ``"product": "mei"``.  The
   desktop app previously polled the LinkLumina web app's channel, read version
   ``6.2.4``, considered it newer than Mei ``0.6.9.0`` and offered to install a
   completely different product over ``Mei.exe``.
2. **Package identity** — the download URL must point at ``Mei.exe``, the
   downloaded file must be a plausible Windows executable (size + MZ header), and
   when the channel declares a ``sha256`` the bytes must match it, so neither an
   HTML error page nor a corrupted/tampered download can be written over the
   running app.
3. **Reversibility** — installing keeps a ``.bak`` next to the executable and a
   watchdog script restores it when the new build fails to come up.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass

from litebrowser.core import app_version, product
from litebrowser.core.log import get_logger

_log = get_logger("update")

# Metadata key that ties a release channel to a product.
PRODUCT_FIELD = "product"

# A hand-dropped build lives here, next to the exe.  Publishing an update for a
# machine without a release server is then just "copy two files into update\\".
LOCAL_CHANNEL_DIRNAME = "update"
LOCAL_CHANNEL_FILENAME = "update.json"

# Leftovers a previous build/update leaves beside the exe.  ``.bak`` is what the
# rollback keeps; the rest are from interrupted swaps and hand-made copies.
STALE_SUFFIXES = (".bak", ".old", ".new")
STALE_PREFIXES = ("~",)

# Never delete something younger than this: an update that is happening right
# now would otherwise lose its own package mid-flight.
CLEANUP_MIN_AGE_SECONDS = 600

#: A release version is exactly four numeric parts. Tags may carry a pre-release
#: suffix, but a suffix is never allowed into ``update.json``: the stable channel
#: compares build versions, and turning ``-alpha`` into a zero is how a preview
#: would quietly replace a stable install.
RELEASE_VERSION_RE = re.compile(r"^(\d{1,9})\.(\d{1,9})\.(\d{1,9})\.(\d{1,9})$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

#: A 512 MB ceiling is generous for a PyInstaller build and still stops a
#: malicious/broken channel from filling the disk before verification.
MAX_PACKAGE_BYTES = 512 * 1024 * 1024

_SENSITIVE_QUERY_PARTS = ("token", "secret", "signature", "sig", "key", "password", "auth")


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    download_url: str
    notes: str
    published_at: str
    has_update: bool
    product: str = ""
    # Integrity facts from the channel manifest. ``sha256`` is empty for an older
    # manifest that predates hashing; ``size`` is what the publisher measured.
    sha256: str = ""
    size: int = 0
    # A human-facing release page, when the channel carries one.
    release_url: str = ""
    # A local ``update\\update.json`` may omit the hash for a hand-built package;
    # that exception is narrow, visible, and never applies to a remote channel.
    manual_channel: bool = False


def file_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Hash a (possibly 170 MB) file without holding it in memory.

    Publishers stamp this into ``update.json``; the updater recomputes it after
    the download, and the two must agree before the executable is replaced.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_sha256(metadata: dict) -> str:
    """The declared hash, lowercased; accepts ``sha256`` or the shorter ``hash``."""
    declared = str(metadata.get("sha256") or metadata.get("hash") or "").strip()
    if declared.lower().startswith("sha256:"):
        declared = declared.split(":", 1)[1].strip()
    return declared.lower()


def parse_version(version: str) -> tuple[int, int, int, int]:
    """Parse the one release-version shape Mei publishes and accepts.

    Four numeric parts, nothing else. Prereleases are GitHub pre-releases and
    are deliberately absent from the stable channel's ``update.json``; a suffix
    here is an error, not a zero. This removes the old behaviour where
    ``1.0.0.1-alpha`` compared as ``1.0.0.1`` and could replace a stable user.
    """
    text = str(version or "").strip()
    match = RELEASE_VERSION_RE.match(text)
    if not match:
        raise ValueError(
            f"Version '{text or '(missing)'}' is not a four-part numeric release "
            "version such as 1.2.3.4. Pre-release suffixes belong on a GitHub "
            "pre-release tag, never in the stable update manifest."
        )
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _normalize_version(version: str):
    """Backwards-compatible name for :func:`parse_version`."""
    return parse_version(version)


def _version_is_newer(latest: str, current: str) -> bool:
    """Compare two valid four-part versions; malformed values are refused."""
    return parse_version(latest) > parse_version(current)


def redact_url(url: str) -> str:
    """Hide credentials and token-shaped query values before showing a URL."""
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return "<redacted url>"
    hostname = parts.hostname or ""
    netloc = hostname
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"
    try:
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
    except ValueError:
        pass
    query = urllib.parse.urlencode(
        [
            (
                key,
                "REDACTED"
                if any(part in key.lower() for part in _SENSITIVE_QUERY_PARTS)
                else value,
            )
            for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def asset_name(url: str) -> str:
    return os.path.basename(urllib.parse.urlparse(str(url or "")).path)


def app_directory(app_dir: str = "") -> str:
    """Folder the running build lives in (``dist\\`` for a built .exe).

    Empty for a from-source run, so a stray ``update\\`` folder next to
    ``python.exe`` can never hijack a developer's update check.
    """
    if app_dir:
        return os.path.abspath(app_dir)
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return ""


def local_channel_path(app_dir: str = "") -> str:
    """``update\\update.json`` beside the exe, when someone dropped one there."""
    directory = app_directory(app_dir)
    if not directory:
        return ""
    path = os.path.join(directory, LOCAL_CHANNEL_DIRNAME, LOCAL_CHANNEL_FILENAME)
    return path if os.path.isfile(path) else ""


def local_channel_packages(app_dir: str = "") -> list[str]:
    """Builds sitting in ``update\\`` — deleted after they are installed."""
    directory = app_directory(app_dir)
    if not directory:
        return []
    folder = os.path.join(directory, LOCAL_CHANNEL_DIRNAME)
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        if name.lower().endswith(".exe") and os.path.isfile(os.path.join(folder, name))
    ]


def local_channel_url(app_dir: str = "") -> str:
    path = local_channel_path(app_dir)
    return f"file:{urllib.request.pathname2url(path)}" if path else ""


def local_source(url: str) -> str:
    """Filesystem path when ``url`` points at a local file, else ``""``.

    Accepts ``file:///D:/...`` *and* a bare Windows path, because a hand-made
    channel JSON is easier to write with ``"D:\\\\builds\\\\Mei.exe"`` in it.
    """
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme == "file":
        return urllib.request.url2pathname(parsed.path)
    if parsed.scheme in ("http", "https", "ftp"):
        return ""
    # ``D:\x\Mei.exe`` parses as scheme "d"; anything with no scheme at all (or a
    # single letter) is still a path on this machine.
    return text if len(parsed.scheme) <= 1 else ""


def asset_is_ours(download_url: str) -> bool:
    """True when the download URL points at this product's release asset."""
    name = asset_name(download_url)
    return bool(name) and name.lower() == product.ASSET_NAME.lower()


def _read_remote_json(url: str, timeout: int = 8):
    local = local_source(url)
    if local:
        with open(local, "rb") as handle:
            return json.loads(handle.read().decode("utf-8-sig", errors="replace"))
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"{app_version.APP_NAME}/{app_version.APP_VERSION}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read().decode(charset, errors="replace")
    return json.loads(payload)


def _wrong_channel_error(declared: str) -> ValueError:
    served = declared or "an unidentified product"
    return ValueError(
        f"This update channel serves {served}, not {product.PRODUCT_NAME}. "
        f"Point {product.PRODUCT_ID} at its own release channel "
        f"(see core/product.py → DEFAULT_UPDATE_CHANNEL_URL) and try again."
    )


def check_for_updates(metadata_url: str | None = None, app_dir: str = "") -> UpdateInfo:
    """Check for updates. Raises a clear error if no update server is configured.

    ``metadata_url`` lets tests point at a fixture server without touching the
    global default; when empty we fall back to the product's configured channel.
    ``app_dir`` overrides ``update\\`` discovery (tests, tooling).
    """
    # A build dropped into ``update\`` beside the exe is a deliberate, local
    # instruction — honour it before the configured remote channel.
    url = metadata_url or local_channel_url(app_dir) or app_version.UPDATE_METADATA_URL
    if not url:
        raise ValueError(
            "Update server is not configured in this build. "
            "Set LITEBROWSER_UPDATE_METADATA_URL when publishing."
        )
    metadata = _read_remote_json(url)
    if not isinstance(metadata, dict):
        raise ValueError("Update metadata is not a JSON object")

    # Ownership gate: a release channel that does not name this product is not
    # ours, no matter how its version number compares.
    declared = str(metadata.get(PRODUCT_FIELD) or "").strip()
    if declared != product.PRODUCT_ID:
        raise _wrong_channel_error(declared)

    latest_version = str(metadata.get("version") or "").strip()
    if not latest_version:
        raise ValueError("Missing version in update metadata")
    # Parse here, before comparing: a malformed or pre-release version in the
    # channel is refused with a message naming the rule, not coerced to zero.
    parse_version(latest_version)

    # Only asset-shaped keys become a download URL. ``release_url`` is a page, so
    # it is kept aside — inventing a download from it would offer the releases
    # page as if it were Mei.exe (and the asset check would then refuse it).
    download_url = str(metadata.get("download_url") or metadata.get("installer_url") or "").strip()
    release_url = str(metadata.get("release_url") or "").strip()
    notes = str(metadata.get("notes") or metadata.get("changelog") or "").strip()
    published_at = str(metadata.get("published_at") or metadata.get("date") or "").strip()
    sha256 = _manifest_sha256(metadata)
    if sha256 and not SHA256_RE.match(sha256):
        raise ValueError("The update manifest declares a malformed SHA-256 hash. Refusing it.")
    try:
        size = int(metadata.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size < 0:
        size = 0
    if size > MAX_PACKAGE_BYTES:
        raise ValueError("The update manifest advertises an implausibly large package. Refusing it.")
    current_version = app_version.APP_VERSION
    has_update = _version_is_newer(latest_version, current_version)
    manual = bool(local_source(download_url) or local_channel_path(app_dir))

    if has_update and download_url and not asset_is_ours(download_url):
        raise ValueError(
            f"The channel offers '{asset_name(download_url)}' for {latest_version}, "
            f"but {product.PRODUCT_NAME} updates ship as {product.ASSET_NAME}. "
            "Refusing an update that is not this product's build."
        )
    if has_update and download_url and not sha256 and not manual:
        raise ValueError(
            "The update manifest does not declare a SHA-256 for the package. "
            "A remote update must be identity-checked before it can replace "
            "Mei, so this release is refused. Publish it with tools/publish_release.py."
        )

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        notes=notes,
        published_at=published_at,
        has_update=has_update,
        product=declared,
        sha256=sha256,
        size=size,
        release_url=release_url,
        manual_channel=manual,
    )


def download_update_package(
    download_url: str,
    version: str,
    expected_sha256: str = "",
    expected_size: int = 0,
    timeout: int = 30,
    progress_callback=None,
) -> str:
    """Download and verify a package, reporting bounded progress.

    ``progress_callback(received, total)`` runs on the caller's worker thread, so
    a GUI passes a signal emitter rather than touching widgets. It is called at
    most ~20 times for a full package, not once per network chunk.
    """
    def report(received: int, total: int) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(int(received), int(total))
        except Exception:  # noqa: BLE001  progress must never fail a download
            pass

    if not download_url:
        raise ValueError("Missing download URL")
    if not asset_is_ours(download_url):
        raise ValueError(
            f"Refusing to download '{asset_name(download_url)}' — "
            f"{product.PRODUCT_NAME} updates ship as {product.ASSET_NAME}."
        )
    # The version is part of a file name; only the strict release shape may be
    # used so a manifest cannot steer the write outside the update folder.
    parse_version(version)
    target_dir = os.path.join(tempfile.gettempdir(), app_version.APP_NAME, "updates")
    os.makedirs(target_dir, exist_ok=True)
    file_name = f"{app_version.APP_NAME}-{version}.exe"
    target_path = os.path.join(target_dir, file_name)
    local = local_source(download_url)
    try:
        if local:
            # Already on this machine: copy, never move — the user's build stays
            # put, and the swap script is the only thing allowed to delete it.
            total = os.path.getsize(local)
            report(0, total)
            shutil.copyfile(local, target_path)
            report(total, total)
            return _accept_download(target_path, expected_sha256, expected_size)
        request = urllib.request.Request(
            download_url,
            headers={"User-Agent": f"{app_version.APP_NAME}/{app_version.APP_VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            try:
                declared = int(response.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                declared = 0
            if declared > MAX_PACKAGE_BYTES:
                raise ValueError("The update download is larger than Mei will accept.")
            if expected_size and declared and declared != expected_size:
                raise ValueError(
                    "The update server advertises a different size than the release manifest. "
                    "Refusing this download."
                )
            total = expected_size or declared or 0
            step = max(1024 * 1024, (total or MAX_PACKAGE_BYTES) // 20)
            next_report = step
            report(0, total)
            received = 0
            with open(target_path, "wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_PACKAGE_BYTES:
                        raise ValueError("The update download is larger than Mei will accept.")
                    output.write(chunk)
                    if received >= next_report:
                        report(received, total or received)
                        next_report = received + step
            report(received, total or received)
        return _accept_download(target_path, expected_sha256, expected_size)
    except Exception:
        # A partial file must never linger as if it were a usable update.
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise


def _accept_download(path: str, expected_sha256: str = "", expected_size: int = 0) -> str:
    """Verify a finished download and drop it when it cannot be a build.

    Failing here (instead of at install time) keeps a corrupt download from
    sitting in ``%TEMP%`` as if it were a usable update, and reports the reason
    while the user still has the download in front of them.
    """
    try:
        verify_package(path, expected_sha256, expected_size)
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path


def verify_package(package_path: str, expected_sha256: str = "", expected_size: int = 0) -> None:
    """Reject anything that cannot be a real build before it touches the exe.

    A truncated download, an HTML error page saved as ``.exe`` or a random file
    would otherwise be copied over the running application.  When the channel
    declared a hash, the bytes must match it too — that is what turns "probably
    the right file" into the exact file the publisher measured. The advertised
    size and the absolute ceiling are checked before hashing.
    """
    if not os.path.isfile(package_path):
        raise FileNotFoundError(package_path)
    size = os.path.getsize(package_path)
    if size < product.MIN_PACKAGE_BYTES:
        raise ValueError(
            f"Downloaded update is only {size} bytes — far too small to be "
            f"{product.PRODUCT_NAME}. The download likely failed."
        )
    if size > MAX_PACKAGE_BYTES:
        raise ValueError("Downloaded update is larger than Mei will accept.")
    try:
        declared_size = int(expected_size or 0)
    except (TypeError, ValueError):
        declared_size = 0
    if declared_size and size != declared_size:
        raise ValueError(
            f"Downloaded update is {size} bytes but its release manifest advertised "
            f"{declared_size}. The download is incomplete or was tampered with."
        )
    with open(package_path, "rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError(
                "Downloaded update is not a Windows executable (missing MZ header). "
                "Refusing to install it."
            )
    digest = (expected_sha256 or "").strip().lower()
    if digest:
        if not SHA256_RE.match(digest):
            raise ValueError("The expected SHA-256 is malformed; refusing to verify against it.")
        actual = file_sha256(package_path)
        if actual != digest:
            raise ValueError(
                "The downloaded update does not match its release manifest "
                f"(sha256 {actual[:12]}... but the channel declared {digest[:12]}...). "
                "The download is corrupted or was tampered with — refusing to install it."
            )


def _stale_beside_exe(directory: str) -> list[str]:
    """Leftover swaps next to the exe (and inside ``update\\``), never the live one."""
    live = os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else ""
    found: list[str] = []
    for folder in (directory, os.path.join(directory, LOCAL_CHANNEL_DIRNAME)):
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not os.path.isfile(path) or os.path.abspath(path) == live:
                continue
            lower = name.lower()
            if lower.endswith(STALE_SUFFIXES) or (lower.endswith(".exe") and lower.startswith(STALE_PREFIXES)):
                found.append(path)
    return found


def _downloaded_packages() -> list[str]:
    """Update packages this app downloaded into ``%TEMP%\\Mei\\updates``."""
    folder = os.path.join(tempfile.gettempdir(), app_version.APP_NAME, "updates")
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        if os.path.isfile(os.path.join(folder, name))
    ]


def cleanup_old_artifacts(
    app_dir: str = "",
    *,
    min_age_seconds: int = CLEANUP_MIN_AGE_SECONDS,
    downloaded: bool = True,
) -> dict:
    """Delete what previous builds and updates left behind; report the space freed.

    A self-update is supposed to be space-neutral: the swap keeps one ``.bak`` for
    the rollback window and downloads a ~170 MB copy of the installer.  The swap
    script deletes both on success, but a rollback or a crash leaves them behind,
    so this sweeps them on the next launch.  Anything younger than
    ``min_age_seconds`` is skipped — that is this machine's *current* update.
    """
    directory = app_directory(app_dir)
    candidates = _stale_beside_exe(directory) if directory else []
    if downloaded:
        candidates.extend(_downloaded_packages())

    removed: list[str] = []
    errors: list[str] = []
    freed = 0
    now = time.time()
    for path in candidates:
        try:
            if min_age_seconds and now - os.path.getmtime(path) < min_age_seconds:
                continue
            size = os.path.getsize(path)
            os.remove(path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            continue
        removed.append(path)
        freed += size

    if removed:
        _log.info(
            "cleaned %s stale build file(s), freeing %.0f MB",
            len(removed),
            freed / (1024 * 1024),
        )
    for problem in errors:
        _log.debug("could not clean %s", problem)
    return {"removed": removed, "freed_bytes": freed, "errors": errors}


def _ps_quote(value: str) -> str:
    """One PowerShell single-quoted literal; ``%``, ``&`` and ``!`` stay inert."""
    return "'" + str(value or "").replace("'", "''") + "'"


def _update_script_text(
    current_exe: str,
    package_path: str,
    pid: int,
    stale_paths=(),
    health_file: str = "",
    health_token: str = "",
) -> str:
    """A PowerShell swap script with no shell interpolation of paths at all.

    The old ``.cmd`` builder pasted paths into a batch file, where ``%``, ``&``
    and ``!`` are syntax. Here every path is a single-quoted PowerShell literal
    and the whole script is run as ``-EncodedCommand``, so cmd.exe never parses
    the path at all. Success is a *startup health marker* written by the new
    build, not merely “a process with this name exists” (a second instance made
    the old check pass for the wrong build).
    """
    cleanup = "".join(
        f"Remove-Item -LiteralPath {_ps_quote(path)} -Force -ErrorAction SilentlyContinue\n"
        for path in stale_paths
    )
    health_dir = os.path.dirname(health_file) if health_file else ""
    return f"""$ErrorActionPreference = 'Stop'
$target = {_ps_quote(current_exe)}
$source = {_ps_quote(package_path)}
$backup = $target + '.bak'
$processId = {int(pid)}
$healthFile = {_ps_quote(health_file)}
$healthToken = {_ps_quote(health_token)}
$workingDirectory = Split-Path -Parent $target

while (Get-Process -Id $processId -ErrorAction SilentlyContinue) {{
    Start-Sleep -Milliseconds 500
}}

Copy-Item -LiteralPath $target -Destination $backup -Force
try {{
    Copy-Item -LiteralPath $source -Destination $target -Force
}} catch {{
    Copy-Item -LiteralPath $backup -Destination $target -Force
    Start-Process -FilePath $target -WorkingDirectory $workingDirectory
    exit 1
}}

Remove-Item -LiteralPath $healthFile -Force -ErrorAction SilentlyContinue
$env:MEI_UPDATE_HEALTH_FILE = $healthFile
$env:MEI_UPDATE_HEALTH_TOKEN = $healthToken
$started = Start-Process -FilePath $target -WorkingDirectory $workingDirectory -PassThru
$healthy = $false
if ($healthToken) {{
    for ($i = 0; $i -lt 60; $i++) {{
        Start-Sleep -Seconds 1
        if (Test-Path -LiteralPath $healthFile) {{
            try {{
                $value = (Get-Content -LiteralPath $healthFile -Raw).Trim()
                if ($value -eq $healthToken) {{ $healthy = $true; break }}
            }} catch {{ }}
        }}
        if ($started.HasExited) {{ break }}
    }}
}} else {{
    Start-Sleep -Seconds 15
    $healthy = -not $started.HasExited
}}

if (-not $healthy) {{
    # Keep the backup: a failed health check is exactly when a user may need it.
    Copy-Item -LiteralPath $backup -Destination $target -Force
    Start-Process -FilePath $target -WorkingDirectory $workingDirectory
    exit 2
}}

Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
{cleanup}if ({_ps_quote(health_dir)}) {{ Remove-Item -LiteralPath {_ps_quote(health_dir)} -Recurse -Force -ErrorAction SilentlyContinue }}
exit 0
"""


def install_downloaded_update(
    package_path: str,
    stale_paths=(),
    expected_sha256: str = "",
    expected_size: int = 0,
) -> None:
    verify_package(package_path, expected_sha256, expected_size)
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-replace only supports a built .exe.")

    current_exe = os.path.abspath(sys.executable)
    support_dir = tempfile.mkdtemp(prefix="mei-updater-")
    health_file = os.path.join(support_dir, "startup.ok")
    health_token = uuid.uuid4().hex
    script = _update_script_text(
        current_exe,
        package_path,
        os.getpid(),
        stale_paths,
        health_file=health_file,
        health_token=health_token,
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    subprocess.Popen(command, close_fds=True, creationflags=creationflags)


def format_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"Server returned HTTP error {exc.code}."
    if isinstance(exc, urllib.error.URLError):
        return "Could not connect to the update server."
    if isinstance(exc, TimeoutError):
        return "Update check timed out."
    if isinstance(exc, ValueError):
        return str(exc)
    return f"Update error: {exc}"
