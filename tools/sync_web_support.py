"""Mirror ``web_support/`` into ``dist/web_support`` for a packaged build.

    .venv\\Scripts\\python.exe tools\\sync_web_support.py
    .venv\\Scripts\\python.exe tools\\sync_web_support.py web_support dist\\web_support

Mei.exe loads the chained sites from the ``web_support`` folder *beside* the exe,
so every build has to refresh it. That used to be ``xcopy`` plus an ``rmdir`` of
the legacy hub copy in ``build_exe.bat`` — but cmd.exe decodes batch lines in the
OEM code page while the file itself is UTF-8, so the diacritics in
``Cục Quản Lý - Bản Đầy Đủ 1`` never matched the real folder name: the dead
~600 MB duplicate was copied into ``dist`` on every build and never pruned.

Doing the mirror in Python keeps the Unicode names intact *and* skips the folder
while walking the source, so the payload is never copied at all. The skip list
comes from ``litebrowser.core.app_paths`` so the build and the running app agree
on which folder names are stale.
"""
import os
from pathlib import Path
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, REPO_ROOT)

try:  # single source of truth for the folder names that are no longer shipped
    from litebrowser.core.app_paths import LEGACY_BUNDLED_FOLDER_MARKERS as SKIP_DIRS
except Exception:  # pragma: no cover - only when the package cannot be imported
    SKIP_DIRS = (
        "Cục Quản Lý - Bản Đầy Đủ 1",
        "Cuc Quan Ly - Ban Day Du 1",
    )

# Dev leftovers that must never ship next to the exe.
SKIP_SUFFIXES = (".log",)


def is_skipped(name: str) -> bool:
    """True for names this build refuses to copy (and prunes from ``dist``)."""
    return name in SKIP_DIRS or name.lower().endswith(SKIP_SUFFIXES)


# Public static assets only. Never inspect private backend stores or keys.
PRIVATE_DIRS = frozenset({"server", "node_modules", "tests", "profiles", "runtime_data", "browserdata", "safevault", "downloads", "litebrowser-update", "extension", "bí mật - bản cũ full màu"})
PUBLIC_SUFFIXES = frozenset({".html", ".htm", ".css", ".js", ".mjs", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".wav", ".mp4", ".webm"})
PRIVATE_FILES = frozenset({"sessions.json", "config.local.json", "credentials.json", "tokens.json", "package-lock.json", "package.json", "replace_colors.js"})


def _private_directory(name: str) -> bool:
    return name.startswith(".") or name.lower() in PRIVATE_DIRS or is_skipped(name)


def _private_file(name: str) -> bool:
    return name.startswith(".") or name.lower() in PRIVATE_FILES or is_skipped(name) or Path(name).suffix.lower() not in PUBLIC_SUFFIXES


def public_files(source: str):
    """Yield safe relative paths without following links or entering private dirs."""
    root_path = Path(source).resolve()
    for root, dirs, names in os.walk(root_path, topdown=True, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not _private_directory(name) and not Path(root, name).is_symlink())
        for name in sorted(names):
            path = Path(root, name)
            if _private_file(name) or path.is_symlink():
                continue
            if path.is_file():
                yield path.relative_to(root_path)


def prune(dest: str, log=print) -> int:
    """Remove non-public entries older builds left in the generated bundle.

    Apply the same policy as copying, without following links or reading private
    file contents. A cleanup failure must fail the build, not ship stale secrets.
    """
    if not os.path.isdir(dest):
        return 0
    removed = 0
    for root, dirs, names in os.walk(dest, topdown=True):
        stale_dirs = [name for name in dirs if _private_directory(name) or os.path.islink(os.path.join(root, name))]
        stale_files = [name for name in names if _private_file(name) or os.path.islink(os.path.join(root, name))]
        dirs[:] = [name for name in dirs if name not in stale_dirs]
        for name in stale_dirs + stale_files:
            path = os.path.join(root, name)
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError as exc:
                raise OSError(f"Could not remove non-public bundle entry {path}: {exc}") from exc
            removed += 1
            log(f"  pruned {os.path.relpath(path, dest)}")
    return removed


def sync(source: str, dest: str, log=print) -> tuple[int, int]:
    """Copy ``source`` onto ``dest``, returning (files copied, bytes copied)."""
    source_path, dest_path = Path(source).resolve(), Path(dest).resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(source)
    if source_path == dest_path or source_path.is_relative_to(dest_path) or dest_path.is_relative_to(source_path):
        raise ValueError("Source and destination must be separate, non-nested folders")
    dest_path.mkdir(parents=True, exist_ok=True)
    prune(str(dest_path), log)
    files = total = 0
    for relative in public_files(str(source_path)):
        src_path, target = source_path / relative, dest_path / relative
        if not target.resolve().is_relative_to(dest_path):
            raise OSError("Destination path escapes the web bundle")
        target.parent.mkdir(parents=True, exist_ok=True)
        # A failed public-asset copy is a failed build, never a silent success.
        shutil.copy2(src_path, target)
        files += 1
        total += src_path.stat().st_size
    return files, total


def _utf8_stdout() -> None:
    """Keep the build log readable when a folder name carries diacritics.

    The console code page is cp1252/cp437, so printing ``Cục Quản Lý`` would
    raise UnicodeEncodeError and abort the build halfway through the copy.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    _utf8_stdout()
    source = os.path.abspath(args[0] if args else os.path.join(REPO_ROOT, "web_support"))
    dest = os.path.abspath(
        args[1] if len(args) > 1 else os.path.join(REPO_ROOT, "dist", "web_support")
    )
    if not os.path.isdir(source):
        print(f"Not found: {source}")
        return 1
    print(f"Syncing {source}\n      -> {dest}")
    print(f"  not shipping: {', '.join(SKIP_DIRS)}")
    try:
        files, total = sync(source, dest)
    except (OSError, ValueError) as exc:
        print(f"Sync failed: {exc}")
        return 1
    print(f"  copied {files} files, {total / (1024 * 1024):.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
