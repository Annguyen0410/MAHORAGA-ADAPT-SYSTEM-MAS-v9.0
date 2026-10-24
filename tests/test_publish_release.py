"""Publishing: the release a user downloads must match the app's own identity.

The channel manifest, the release notes and the tag are all derived from
``core/product.py`` and ``docs/CHANGELOG.md``; a mismatch ships an update nobody
is ever offered (the updater compares the build's version, the tag names the
asset URL) or notes that describe a different release. These tests cover the
derivations and every refusal path — nothing here touches the network, and the
CLI is exercised with ``--dry-run``.
"""
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import litebrowser  # noqa: F401  activates the Qt compatibility shim
from litebrowser.core import product
from litebrowser.services import update_service

from tools import publish_release, write_local_update

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fake_build(path: str) -> str:
    """A file that passes ``verify_package``: MZ header and a plausible size."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(b"MZ" + b"\0" * product.MIN_PACKAGE_BYTES)
    return path


class TestTagAndAssetNames(unittest.TestCase):
    def test_tag_accepts_both_spellings(self):
        # Built from the app's own version: a literal here would fail on the next
        # bump for a reason that has nothing to do with tag parsing.
        self.assertEqual(publish_release.version_from_tag(f"v{product.APP_VERSION}"), product.APP_VERSION)
        self.assertEqual(publish_release.version_from_tag(f" {product.APP_VERSION} "), product.APP_VERSION)

    def test_tag_must_be_the_build_in_this_tree(self):
        publish_release.assert_tag_matches_build(f"v{product.APP_VERSION}")
        with self.assertRaises(ValueError) as ctx:
            publish_release.assert_tag_matches_build("v0.6.9.0")
        self.assertIn("core/product.py", str(ctx.exception))

    def test_a_suffixed_tag_is_an_alpha_and_needs_the_flag(self):
        alpha = f"v{product.APP_VERSION}-alpha.2"
        self.assertEqual(
            publish_release.assert_tag_matches_build(alpha, prerelease=True),
            product.APP_VERSION,
            "the manifest records the build version, never the tag's suffix",
        )
        with self.assertRaises(ValueError) as ctx:
            publish_release.assert_tag_matches_build(alpha)
        self.assertIn("--prerelease", str(ctx.exception))

    def test_a_tag_that_is_not_a_version_is_refused(self):
        for tag in ("v1.0", "v1.0.0", "latest", "v1.0.0.0_alpha", ""):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    publish_release.assert_tag_matches_build(tag)

    def test_download_url_is_the_release_asset(self):
        tag = f"v{product.APP_VERSION}"
        url = publish_release.asset_download_url(product.RELEASES_REPO, tag, product.ASSET_NAME)
        self.assertEqual(
            url,
            f"https://github.com/{product.RELEASES_REPO}/releases/download/{tag}/{product.ASSET_NAME}",
        )
        self.assertTrue(update_service.asset_is_ours(url))

    def test_web_support_zip_name_carries_the_version(self):
        self.assertEqual(
            publish_release.web_support_name(product.APP_VERSION),
            f"Mei-{product.APP_VERSION}-web_support.zip",
        )


class TestReleaseNotes(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "docs", "CHANGELOG.md"), encoding="utf-8-sig") as handle:
            self.changelog = handle.read()

    def test_the_section_is_this_version_only(self):
        section = publish_release.changelog_section(self.changelog, product.APP_VERSION)
        self.assertIn(product.APP_VERSION, section)
        # The block ends where the next milestone heading starts.
        body_lines = [line for line in section.splitlines() if line.strip().startswith("> ##")]
        self.assertEqual(len(body_lines), 1, section[:200])

    def test_an_undocumented_version_is_refused(self):
        with self.assertRaises(ValueError):
            publish_release.changelog_section(self.changelog, "9.9.9.9")

    def test_the_prerelease_body_says_ordinary_users_are_not_offered_it(self):
        site = f"Mei-{product.APP_VERSION}-web_support.zip"
        body = publish_release.build_release_body(
            product.APP_VERSION, product.ASSET_NAME, site, self.changelog, prerelease=True
        )
        self.assertIn("pre-release", body)
        self.assertIn("releases/latest", body)
        self.assertIn(product.APP_VERSION, body)
        self.assertIn("Folder sync", body, "the notes still quote the changelog section")

    def test_the_body_opens_in_english_and_quotes_the_changelog(self):
        site = f"Mei-{product.APP_VERSION}-web_support.zip"
        body = publish_release.build_release_body(product.APP_VERSION, product.ASSET_NAME, site, self.changelog)
        self.assertTrue(body.startswith("**Download:**"))
        self.assertIn(product.ASSET_NAME, body)
        self.assertIn(site, body)
        self.assertIn(product.APP_VERSION, body)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exe = _fake_build(os.path.join(self._tmp.name, product.ASSET_NAME))

    def test_manifest_carries_identity_size_and_hash(self):
        manifest = publish_release.build_manifest(
            version=product.APP_VERSION,
            exe_path=self.exe,
            download_url="https://h/x/Mei.exe",
            notes="hello",
            published_at="2026-09-26",
        )
        self.assertEqual(manifest["product"], product.PRODUCT_ID)
        self.assertEqual(manifest["version"], product.APP_VERSION)
        self.assertEqual(manifest["size"], os.path.getsize(self.exe))
        self.assertEqual(manifest["sha256"], update_service.file_sha256(self.exe))
        self.assertEqual(manifest["published_at"], "2026-09-26")
        self.assertNotIn("web_support", manifest)

    def test_manifest_records_the_site_zip_when_one_is_shipped(self):
        site = os.path.join(self._tmp.name, publish_release.web_support_name(product.APP_VERSION))
        with open(site, "wb") as handle:
            handle.write(b"PK\3\4payload")
        manifest = publish_release.build_manifest(
            version=product.APP_VERSION,
            exe_path=self.exe,
            download_url="https://h/x/Mei.exe",
            web_support_path=site,
            web_support_url=f"https://h/x/{publish_release.web_support_name(product.APP_VERSION)}",
        )
        self.assertEqual(manifest["web_support"]["size"], os.path.getsize(site))
        self.assertEqual(manifest["web_support"]["sha256"], update_service.file_sha256(site))

    def test_the_local_channel_and_the_release_agree_on_the_shape(self):
        manifest = write_local_update.manifest_for(self.exe, self.exe, "notes")
        self.assertEqual(manifest["sha256"], update_service.file_sha256(self.exe))
        self.assertEqual(manifest["size"], os.path.getsize(self.exe))
        self.assertEqual(manifest["product"], product.PRODUCT_ID)

    def test_a_non_build_is_refused_before_it_is_published(self):
        junk = os.path.join(self._tmp.name, "junk.exe")
        with open(junk, "wb") as handle:
            handle.write(b"<html>404</html>")
        with self.assertRaises(ValueError):
            publish_release.verify_build(junk)


class TestWebSupportZip(unittest.TestCase):
    def test_logs_are_left_out_and_nested_files_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "web_support")
            os.makedirs(os.path.join(src, "boitoan"))
            os.makedirs(os.path.join(src, "hub"))
            for rel in ("index.html", "hub/index.html", "boitoan/app.js", "run.log"):
                with open(os.path.join(src, rel), "w", encoding="utf-8") as handle:
                    handle.write("x")
            out = os.path.join(tmp, "site.zip")
            publish_release.zip_web_support(src, out)
            import zipfile

            with zipfile.ZipFile(out) as bundle:
                names = bundle.namelist()
        self.assertIn("index.html", names)
        self.assertIn("hub/index.html", names, "every release carries the Hub entry point")
        self.assertIn("boitoan/app.js", names, "zip member names are always forward-slashed")
        self.assertNotIn("run.log", names)


    def test_private_web_data_is_excluded_from_release_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "web")
            for relative in ("hub/index.html", "app/server/.env", "app/server/sessions.json", "app/.env", "app/sessions.json", "app/node_modules/x.js"):
                target = os.path.join(src, relative)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write("fixture")
            out = os.path.join(tmp, "site.zip")
            publish_release.zip_web_support(src, out)
            import zipfile
            with zipfile.ZipFile(out) as bundle:
                self.assertEqual(bundle.namelist(), ["hub/index.html"])

    def test_failed_zip_preserves_previous_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "web")
            os.makedirs(src)
            with open(os.path.join(src, "index.html"), "w", encoding="utf-8") as handle:
                handle.write("public")
            out = os.path.join(tmp, "site.zip")
            with open(out, "wb") as handle:
                handle.write(b"previous")
            with mock.patch.object(publish_release.zipfile.ZipFile, "write", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    publish_release.zip_web_support(src, out)
            with open(out, "rb") as handle:
                self.assertEqual(handle.read(), b"previous")


class TestReleaseFlags(unittest.TestCase):
    """The flag that decides whether *everyone* is offered this build.

    ``releases/latest`` skips pre-releases, so this boolean is the difference
    between "the Alpha is download-from-the-releases-page" and "every installed
    copy is told to install the Alpha tonight".
    """

    def _calls(self, prerelease: bool) -> list:
        seen = []

        def fake_request(method, url, token, **kwargs):
            seen.append((method, url, kwargs.get("payload")))
            if method == "GET":
                return {"id": 7, "draft": False}
            if method == "POST":  # 422 = this tag already has a release
                raise urllib.error.HTTPError(url, 422, "already exists", {}, None)
            return {"id": 7}

        with mock.patch.object(publish_release, "_request", side_effect=fake_request):
            publish_release._ensure_release(
                product.RELEASES_REPO, f"v{product.APP_VERSION}-alpha.1", "tok", "body", False, prerelease
            )
        return seen

    def test_a_new_release_carries_the_prerelease_flag(self):
        payload = self._calls(True)[0][2]
        self.assertTrue(payload["prerelease"])
        self.assertFalse(payload["draft"])
        self.assertEqual(payload["tag_name"], f"v{product.APP_VERSION}-alpha.1")
        self.assertIn("alpha.1", payload["name"], "the release title is the tag people search for")

    def test_an_ordinary_release_is_not_marked_as_a_prerelease(self):
        self.assertFalse(self._calls(False)[0][2]["prerelease"])

    def test_a_re_run_re_applies_the_flag_to_the_existing_release(self):
        seen = self._calls(True)
        patch = [payload for method, _url, payload in seen if method == "PATCH"]
        self.assertEqual(len(patch), 1, "an existing tag is edited, not silently reused")
        self.assertTrue(patch[0]["prerelease"])
        self.assertEqual(patch[0]["body"], "body")


class TestPublishRefusals(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exe = _fake_build(os.path.join(self._tmp.name, product.ASSET_NAME))

    def _publish(self, **overrides):
        payload = dict(
            tag=f"v{product.APP_VERSION}",
            repo=product.RELEASES_REPO,
            exe=self.exe,
            web_support="",
            notes="",
            token="",
            out_dir=self._tmp.name,
            skip_upload=True,
        )
        payload.update(overrides)
        return publish_release.publish(**payload)

    def test_a_mismatched_tag_never_reaches_the_network(self):
        with self.assertRaises(ValueError):
            self._publish(tag="v0.6.9.0")

    def test_a_missing_build_is_refused(self):
        with self.assertRaises(FileNotFoundError):
            self._publish(exe=os.path.join(self._tmp.name, "nope.exe"))

    def test_a_dry_run_writes_a_verifiable_manifest_and_uploads_nothing(self):
        result = self._publish()
        self.assertFalse(result["uploaded"])
        manifest_path = result["manifest_path"]
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path, encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertEqual(written["sha256"], update_service.file_sha256(self.exe))
        self.assertEqual(written["download_url"], publish_release.asset_download_url(
            product.RELEASES_REPO, f"v{product.APP_VERSION}", product.ASSET_NAME
        ))
        self.assertEqual(written["release_url"], publish_release.release_page_url(product.RELEASES_REPO))
        # The body is written out too, so a hand upload (no token on the release
        # machine) pastes a file instead of retyping the notes.
        self.assertTrue(os.path.isfile(result["body_path"]))
        with open(result["body_path"], encoding="utf-8") as handle:
            body = handle.read()
        self.assertTrue(body.startswith("**Download:**"))
        self.assertIn(product.APP_VERSION, body)

    def test_publishing_without_a_token_says_which_variable_to_set(self):
        with self.assertRaises(ValueError) as ctx:
            self._publish(skip_upload=False)
        self.assertIn("GITHUB_TOKEN", str(ctx.exception))

    def test_the_cli_dry_run_succeeds_without_a_token(self):
        code = publish_release.main(
            ["--tag", f"v{product.APP_VERSION}", "--exe", self.exe, "--no-web-support", "--dry-run"]
        )
        self.assertEqual(code, 0)

    def test_the_cli_publishes_an_alpha_tag_as_a_prerelease(self):
        result = self._publish(tag=f"v{product.APP_VERSION}-alpha.1", prerelease=True)
        self.assertIn("pre-release", result["body"])
        with open(result["manifest_path"], encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertEqual(written["version"], product.APP_VERSION, "the updater compares the build version")

    def test_the_cli_refuses_an_alpha_tag_without_the_flag(self):
        with self.assertRaises(ValueError):
            self._publish(tag=f"v{product.APP_VERSION}-alpha.1")

    def test_the_cli_explains_itself_without_arguments(self):
        self.assertEqual(publish_release.main([]), 2)


if __name__ == "__main__":
    unittest.main()
