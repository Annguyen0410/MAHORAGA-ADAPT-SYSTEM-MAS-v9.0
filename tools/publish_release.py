"""Publish a built Mei.exe as a GitHub Release the app can actually update from.

    .venv\\Scripts\\python.exe tools\\publish_release.py --tag v0.7.0.0

Three artefacts go up together, because the app needs all three:

* ``Mei.exe``                        — the build itself;
* ``Mei-<version>-web_support.zip``  — the site folder that lives *beside* the exe
                                      (it is deliberately not bundled into it);
* ``update.json``                    — the channel manifest the app polls at
                                      ``releases/latest/download/update.json``:
                                      version, asset URL, size and **sha256**.

Until 0.7.0.0 the only update channel was a Netlify path nobody ever deployed, so
an installed Mei polled a 404 and the "release page" button pointed at nothing.
The channel is now an asset of the newest release: it resolves for as long as the
repository exists, the manifest is versioned with the build, and the hash in it is
what the updater holds the downloaded bytes to.

The upload uses the GitHub REST API with a token (there is no ``gh`` CLI on the
release machine)::

    set GITHUB_TOKEN=github_pat_…      # fine-grained, "Contents: read and write"

``--dry-run`` prints the plan and the manifest without touching the network;
``--local-only`` writes ``dist/update/update.json`` for a machine that upgrades
from a folder instead of the internet.

``--prerelease`` marks the release as a GitHub **pre-release**, which is the only
way to ship an Alpha without serving it to everyone: ``releases/latest`` — the
channel every installed copy polls — skips pre-releases and keeps pointing at the
last stable build. A tag with a suffix (``v1.0.0.0-alpha.2``) is refused unless
that flag is present, so an Alpha cannot reach the ordinary channel by accident,
and the manifest always records the plain build version the updater compares.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from litebrowser.core import product  # noqa: E402
from litebrowser.services import update_service  # noqa: E402

try:  # running as a script puts tools/ on sys.path, running from tests does not
    from tools import write_local_update
except ImportError:  # pragma: no cover - script invocation
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import write_local_update  # type: ignore[no-redef]

USAGE = (
    "usage: publish_release.py --tag v<version> [--repo owner/name] [--exe dist/Mei.exe]\n"
    "       [--web-support dist/web_support] [--notes \"text\"] [--draft] [--prerelease]\n"
    "       [--replace] [--dry-run | --local-only]"
)

API_ROOT = "https://api.github.com"
UPLOAD_ROOT = "https://uploads.github.com"
CHANGELOG = os.path.join("docs", "CHANGELOG.md")
# Written beside the manifest so a manual upload can paste the body verbatim.
BODY_FILENAME = "RELEASE_BODY.md"
DEFAULT_WEB_SUPPORT = os.path.join("dist", "web_support")
DEFAULT_EXE = os.path.join("dist", product.ASSET_NAME)

# A release body is read by people, not by the updater. The channel manifest is
# English (it is data); download instructions and release notes are English too.
DOWNLOAD_HEADER = (
    "**Download:** `{exe}` (prebuilt application) and `{web_support}` "
    "(extract beside the executable). Mei 0.7.0.0 and later update automatically "
    "from `releases/latest/download/update.json`."
)

PRERELEASE_NOTE = (
    "**Alpha (pre-release)** — this build is not offered through automatic updates: "
    "`releases/latest` still serves the latest stable build. Download this preview manually here."
)

#: ``v1.0.0.0`` or ``v1.0.0.0-alpha.2``. A tag may carry a pre-release suffix,
#: but the *build* behind it is always the plain four-part version — that is what
#: the updater compares and what the manifest records.
TAG_RE = re.compile(r"^(?P<version>\d+(?:\.\d+){3})(?:-(?P<suffix>[0-9A-Za-z.\-]+))?$")


def version_from_tag(tag: str) -> str:
    """``v0.7.0.0`` and ``0.7.0.0`` both mean the same release."""
    return str(tag or "").strip().lstrip("vV")


def assert_tag_matches_build(tag: str, version: str = "", prerelease: bool = False) -> str:
    """Refuse to publish a release whose tag and build disagree.

    The tag is what a download URL is built from and the build's own version is
    what the updater compares, so a mismatch ships an update nobody is offered.
    A suffix (``v1.0.0.0-alpha.1``) is allowed only together with ``prerelease``:
    a suffixed tag published as an ordinary release would take over
    ``releases/latest``, which is how everyone's copy decides what to install.

    Returns the build version (never the suffix) — the manifest records that.
    """
    clean = version_from_tag(tag)
    current = version or product.APP_VERSION
    match = TAG_RE.match(clean)
    if not match:
        raise ValueError(f"Tag '{tag}' is not a four-part version, optionally with a -suffix.")
    if match.group("version") != current:
        raise ValueError(
            f"Tag '{tag}' is not the build in this tree ({current}). "
            f"Bump core/product.py, rebuild, then publish v{current}."
        )
    if match.group("suffix") and not prerelease:
        raise ValueError(
            f"Tag '{tag}' carries a pre-release suffix — add --prerelease, or the "
            "ordinary update channel would be offered this build."
        )
    return current


def asset_download_url(repo: str, tag: str, name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{name}"


def release_page_url(repo: str) -> str:
    return f"https://github.com/{repo}/releases/latest"


def web_support_name(version: str) -> str:
    return f"{product.PRODUCT_NAME}-{version}-web_support.zip"


def changelog_section(text: str, version: str) -> str:
    """The changelog block for ``version`` — its heading and everything under it.

    Release notes are copied from ``docs/CHANGELOG.md`` rather than written a
    second time, so the notes a user reads on GitHub and the notes in the repo
    cannot disagree.
    """
    lines = text.splitlines()
    head = None
    for index, line in enumerate(lines):
        stripped = line.strip().lstrip("> ").strip()
        if stripped.startswith("##") and version in stripped:
            head = index
            break
    if head is None:
        raise ValueError(f"docs/CHANGELOG.md has no section for {version}")
    body = [lines[head].strip()]
    for line in lines[head + 1 :]:
        stripped = line.strip().lstrip("> ").strip()
        if stripped.startswith("##"):
            break
        body.append(line.rstrip())
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


def build_release_body(
    version: str, exe_name: str, web_support: str, changelog_text: str, prerelease: bool = False
) -> str:
    header = DOWNLOAD_HEADER.format(exe=exe_name, web_support=web_support)
    if prerelease:
        header = f"{header}\n\n{PRERELEASE_NOTE}"
    notes = changelog_section(changelog_text, version)
    return f"{header}\n\n---\n\n{notes}\n"


def build_manifest(
    *,
    version: str,
    exe_path: str,
    download_url: str,
    notes: str = "",
    published_at: str = "",
    web_support_path: str = "",
    web_support_url: str = "",
    release_url: str = "",
) -> dict:
    """The channel manifest — the single file the app polls.

    Written by ``tools/write_local_update.py`` for the folder channel too, so both
    channels verify the same facts: product id, version, asset name, size, hash.
    """
    manifest = write_local_update.manifest_for(exe_path, download_url, notes, published_at)
    manifest["version"] = version
    manifest["release_url"] = release_url
    if web_support_url:
        manifest["web_support"] = {
            "download_url": web_support_url,
            "size": os.path.getsize(web_support_path) if web_support_path else 0,
            "sha256": update_service.file_sha256(web_support_path) if web_support_path else "",
        }
    return manifest


def verify_build(exe_path: str) -> dict:
    """Refuse to publish something that is not a plausible Mei build."""
    update_service.verify_package(exe_path)
    return {"size": os.path.getsize(exe_path), "sha256": update_service.file_sha256(exe_path)}


def zip_web_support(folder: str, out_path: str) -> str:
    """Package only public web assets; preserve the previous ZIP on failure."""
    from tools.sync_web_support import public_files
    import tempfile

    if not os.path.isdir(folder):
        raise FileNotFoundError(folder)
    if os.path.commonpath([os.path.abspath(folder), os.path.abspath(out_path)]) == os.path.abspath(folder):
        raise ValueError("Write the release ZIP outside the source folder")
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mei-web-", suffix=".zip", dir=parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
            for relative in public_files(folder):
                bundle.write(os.path.join(folder, relative), relative.as_posix())
        os.replace(temporary, out_path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return out_path


def _request(method: str, url: str, token: str, *, payload=None, stream_path: str = "", content_type=""):
    """One GitHub API call. ``stream_path`` uploads a file without loading it.

    A release asset is a 170 MB executable, so the body is streamed with an
    explicit ``Content-Length`` (urllib cannot measure a file object itself, and
    without it the request would fall back to chunked encoding, which the upload
    host rejects).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{product.PRODUCT_NAME}/{product.APP_VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    reader = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif stream_path:
        length = os.path.getsize(stream_path)
        reader = _ProgressReader(stream_path, length)
        data = reader
        headers["Content-Type"] = content_type or "application/octet-stream"
        headers["Content-Length"] = str(length)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8", "replace")
    finally:
        if reader is not None:
            reader.close()
    return json.loads(body) if body.strip() else {}


class _ProgressReader:
    """A file wrapper that reports upload progress every ~16 MB."""

    def __init__(self, path: str, total: int):
        self._handle = open(path, "rb")
        self._total = total
        self._sent = 0
        self._next_report = 16 * 1024 * 1024

    def read(self, size: int = -1) -> bytes:
        chunk = self._handle.read(size)
        self._sent += len(chunk)
        if self._sent >= self._next_report or (not chunk and self._total):
            shown = 100.0 * self._sent / max(self._total, 1)
            # ASCII only: this prints in cmd.exe, which decodes in the OEM code page.
            print(f"    ... {self._sent / (1024 * 1024):.0f} MB of {self._total / (1024 * 1024):.0f} MB ({shown:.0f}%)")
            self._next_report = self._sent + 16 * 1024 * 1024
        return chunk

    def close(self):
        self._handle.close()


def _ensure_release(repo: str, tag: str, token: str, body: str, draft: bool, prerelease: bool = False) -> dict:
    payload = {
        "tag_name": tag,
        "name": f"{product.PRODUCT_NAME} {version_from_tag(tag)}",
        "body": body,
        "draft": bool(draft),
        "prerelease": bool(prerelease),
    }
    try:
        return _request("POST", f"{API_ROOT}/repos/{repo}/releases", token, payload=payload)
    except urllib.error.HTTPError as exc:
        if exc.code != 422:  # 422 = this tag already has a release
            raise
        print(f"Release {tag} already exists — adding to it.")
        existing = _request("GET", f"{API_ROOT}/repos/{repo}/releases/tags/{tag}", token)
        release_id = int(existing.get("id") or 0)
        if existing.get("draft") != bool(draft):
            print(
                f"  it is {'a draft' if existing.get('draft') else 'published'} — "
                "leaving that flag as it is"
            )
        # Re-apply the flag and the notes: a re-run must not quietly turn a
        # pre-release into an ordinary one (that would hand the Alpha to every
        # installed copy on the next update check).
        return _request(
            "PATCH",
            f"{API_ROOT}/repos/{repo}/releases/{release_id}",
            token,
            payload={"body": body, "prerelease": bool(prerelease)},
        )


def _upload_asset(repo: str, release_id: int, path: str, token: str, replace: bool) -> None:
    name = os.path.basename(path)
    size = os.path.getsize(path)
    assets = _request("GET", f"{API_ROOT}/repos/{repo}/releases/{release_id}/assets", token)
    for asset in assets if isinstance(assets, list) else []:
        if asset.get("name") != name:
            continue
        if not replace:
            print(f"  {name}: already attached (use --replace to overwrite) — skipped")
            return
        _request("DELETE", f"{API_ROOT}/repos/{repo}/releases/assets/{asset['id']}", token)
    query = urllib.parse.urlencode({"name": name})
    print(f"  {name}: uploading {size / (1024 * 1024):.1f} MB ...")
    _request(
        "POST",
        f"{UPLOAD_ROOT}/repos/{repo}/releases/{release_id}/assets?{query}",
        token,
        stream_path=path,
    )


def publish(
    *,
    tag: str,
    repo: str,
    exe: str,
    web_support: str,
    notes: str,
    token: str,
    draft: bool = False,
    prerelease: bool = False,
    replace: bool = False,
    out_dir: str = "",
    skip_upload: bool = False,
) -> dict:
    """Create the release and attach the build, the site folder and the manifest."""
    version = assert_tag_matches_build(tag, prerelease=prerelease)
    if not os.path.isfile(exe):
        raise FileNotFoundError(f"{exe} — build first: build_exe.bat")
    facts = verify_build(exe)
    print(f"{product.PRODUCT_NAME} {version}: {facts['size'] / (1024 * 1024):.1f} MB, sha256 {facts['sha256'][:16]}...")

    site_zip = os.path.join(out_dir or os.path.dirname(os.path.abspath(exe)), web_support_name(version))
    site_url = ""
    if web_support and os.path.isdir(web_support):
        zip_web_support(web_support, site_zip)
        site_url = asset_download_url(repo, tag, os.path.basename(site_zip))
        print(f"  web_support: zipped {os.path.getsize(site_zip) / (1024 * 1024):.1f} MB")
    else:
        site_zip = ""
        print("  web_support: not found — the release will ship the exe only")

    changelog_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), CHANGELOG)
    with open(changelog_path, encoding="utf-8-sig") as handle:
        changelog_text = handle.read()
    body = build_release_body(
        version,
        product.ASSET_NAME,
        os.path.basename(site_zip) or "(web_support)",
        changelog_text,
        prerelease=prerelease,
    )

    manifest = build_manifest(
        version=version,
        exe_path=exe,
        download_url=asset_download_url(repo, tag, product.ASSET_NAME),
        notes=notes or f"{version} — {product.PRODUCT_NAME} desktop build.",
        published_at=date.today().isoformat(),
        web_support_path=site_zip,
        web_support_url=site_url,
        release_url=release_page_url(repo),
    )
    out = os.path.dirname(os.path.abspath(exe))
    manifest_path = os.path.join(out, "update.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(f"  manifest: {manifest_path}")

    # The body is written out as well: uploading by hand (no token on the release
    # machine) then means pasting this file, not retyping the release notes.
    body_path = os.path.join(out, BODY_FILENAME)
    with open(body_path, "w", encoding="utf-8") as handle:
        handle.write(body)
    print(f"  release body: {body_path}")

    if skip_upload:
        print("Dry run — nothing was uploaded. The release would carry:")
        for path in filter(None, (exe, site_zip, manifest_path, body_path)):
            print(f"    {os.path.basename(path)}  ({os.path.getsize(path) / (1024 * 1024):.1f} MB)")
        return {
            "manifest": manifest,
            "manifest_path": manifest_path,
            "body": body,
            "body_path": body_path,
            "uploaded": False,
        }

    if not token:
        raise ValueError("Set GITHUB_TOKEN (fine-grained token with Contents: read and write) to publish.")

    release = _ensure_release(repo, tag, token, body, draft, prerelease)
    release_id = int(release.get("id") or 0)
    kind = "pre-release" if prerelease else "release"
    print(f"Release {tag} ready (id {release_id}, draft={bool(draft)}, {kind}).")
    for path in filter(None, (exe, site_zip, manifest_path)):
        _upload_asset(repo, release_id, path, token, replace)
    print(f"Published: {release_page_url(repo)}")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "body_path": body_path,
        "body": body,
        "release": release,
        "uploaded": True,
    }


def _arg_value(args: list, flag: str, default: str = "") -> str:
    if flag not in args:
        return default
    index = args.index(flag)
    try:
        return args[index + 1]
    except IndexError:
        return default


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    tag = _arg_value(args, "--tag")
    if not tag:
        print(USAGE)
        return 2
    repo = _arg_value(args, "--repo", product.RELEASES_REPO)
    exe = _arg_value(args, "--exe", DEFAULT_EXE)
    web_support = _arg_value(args, "--web-support", DEFAULT_WEB_SUPPORT)
    notes = _arg_value(args, "--notes")
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    prerelease = "--prerelease" in args

    if "--local-only" in args:
        try:
            assert_tag_matches_build(tag, prerelease=prerelease)
            written = write_local_update.write_local_channel(os.path.dirname(os.path.abspath(exe)), notes)
        except (ValueError, FileNotFoundError) as exc:
            print(f"error: {exc}")
            return 1
        print(f"Local channel written for {product.APP_VERSION}: {written['manifest_path']}")
        return 0

    dry_run = "--dry-run" in args
    try:
        publish(
            tag=tag,
            repo=repo,
            exe=exe,
            web_support="" if "--no-web-support" in args else web_support,
            notes=notes,
            token=token,
            draft="--draft" in args,
            prerelease=prerelease,
            replace="--replace" in args,
            skip_upload=dry_run,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}")
        if not token and not dry_run:
            print(
                "No token found. Either set GITHUB_TOKEN, or attach the three files by hand in\n"
                f"the release UI ({release_page_url(repo)} → Releases → Draft a new release)."
            )
        return 1
    except urllib.error.HTTPError as exc:
        print(f"error: GitHub refused the request: HTTP {exc.code} {exc.reason}")
        print(exc.read().decode("utf-8", "replace")[:600])
        return 1
    if not dry_run:
        print("Done. The channel is live at", product.DEFAULT_UPDATE_CHANNEL_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
