"""Plugins: a manifest is a contract, and a broken one must never be trusted.

The promise of a *declarative* plugin system is that nothing runs that Mei did
not write — so the interesting tests are not "does the importer work" but:

* every manifest that ships with the app validates, and each one says what store
  it touches;
* a manifest is refused when it is malformed, when it asks for a newer API, when
  it uses a kind nothing executes, or when it names a store that does not exist —
  refused as a *problem row*, never as an exception;
* a refusal leaves the profile exactly as it was;
* an importer/skipper reports honest numbers, and a missing file is an error the
  dialog can print.

``services/plugins.py`` keeps discovery, validation and the runners.
"""
import json
import os
import tempfile
import unittest

from litebrowser.core import prefs
from litebrowser.services import flashcard_service, life_service, personal_service, plugins

TODOIST_HEADERS = "TYPE,DATE,CONTENT,PRIORITY,DESCRIPTION\n"


class _ProfileTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write_plugin(self, manifest: dict, plugin_id: str = "") -> str:
        folder = os.path.join(plugins.plugins_dir(self.base), plugin_id or manifest.get("id", "plug"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, plugins.MANIFEST_NAME)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        return path

    def _csv(self, name: str, text: str) -> str:
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def _plugin(self, plugin_id: str) -> plugins.Plugin:
        found = {plugin.id: plugin for plugin in plugins.load_plugins(self.base)["plugins"]}
        self.assertIn(plugin_id, found)
        return found[plugin_id]


class TestShippedManifests(_ProfileTmp):
    def test_the_app_ships_manifests_that_all_validate(self):
        found = plugins.load_plugins(self.base)
        self.assertEqual(found["problems"], [])
        shipped = [plugin for plugin in found["plugins"] if plugin.builtin]
        self.assertGreaterEqual(len(shipped), 3)
        ids = {plugin.id for plugin in shipped}
        self.assertIn("todoist-csv", ids)
        self.assertIn("notes-to-csv", ids)
        for plugin in shipped:
            self.assertEqual(plugin.api, plugins.PLUGIN_API_VERSION)
            self.assertTrue(plugin.touches(), plugin.id)
            self.assertIn(plugin.target, plugins.TARGETS)

    def test_build_configurations_include_builtin_manifests(self):
        import ast
        from pathlib import Path
        import tomllib

        root = Path(__file__).resolve().parents[1]
        spec = ast.parse((root / "Mei.spec").read_text(encoding="utf-8"))
        data = next(node.value for node in spec.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "datas" for target in node.targets))
        entries = ast.literal_eval(data)
        self.assertIn(("litebrowser\\data\\plugins", "litebrowser\\data\\plugins"), entries)
        script = (root / "build_exe.bat").read_text(encoding="utf-8")
        self.assertIn('--add-data "litebrowser\\data\\plugins;litebrowser\\data\\plugins"', script)
        package = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("data/plugins/*.json", package["tool"]["setuptools"]["package-data"]["litebrowser"])

    def test_a_manifest_found_by_id_exposes_what_it_touches(self):
        task_plugin = self._plugin("todoist-csv")
        self.assertIn("Quick tasks", task_plugin.touches())
        export_plugin = self._plugin("notes-to-csv")
        self.assertIn("Writes a file from Notes", export_plugin.touches())


class TestValidation(_ProfileTmp):
    def _problems_for(self, manifest: dict, plugin_id: str = "bad") -> list[dict]:
        self._write_plugin(manifest, plugin_id)
        return plugins.load_plugins(self.base)["problems"]

    def test_a_missing_field_is_a_problem_not_a_crash(self):
        problems = self._problems_for({"id": "x1", "name": "X", "version": "1", "api": 1})
        self.assertTrue(problems)
        self.assertIn("missing field(s)", problems[0]["reason"])
        self.assertIn("kind", problems[0]["reason"])

    def test_an_unknown_field_is_refused(self):
        problems = self._problems_for(
            {"id": "x2", "name": "X", "version": "1", "api": 1, "kind": "importer", "target": "tasks", "run": "rm -rf /"}
        )
        self.assertIn("unknown field(s)", problems[0]["reason"])

    def test_a_kind_without_an_executor_is_refused(self):
        problems = self._problems_for({"id": "x3", "name": "X", "version": "1", "api": 1, "kind": "widget"})
        self.assertIn("kind must be one of", problems[0]["reason"])
        self.assertNotIn("widget", plugins.KINDS, "no kind is listed without a runner")

    def test_a_newer_api_is_refused_with_instructions(self):
        problems = self._problems_for(
            {"id": "x4", "name": "X", "version": "1", "api": 99, "kind": "importer", "target": "tasks"}
        )
        self.assertIn("update Mei", problems[0]["reason"])

    def test_an_unknown_target_is_refused(self):
        problems = self._problems_for(
            {"id": "x5", "name": "X", "version": "1", "api": 1, "kind": "importer", "target": "registry"}
        )
        self.assertIn("target must be one of", problems[0]["reason"])

    def test_a_bad_id_and_bad_mapping_are_refused(self):
        problems = self._problems_for(
            {"id": "Not An Id", "name": "X", "version": "1", "api": 1, "kind": "importer", "target": "tasks"}
        )
        self.assertIn("id must be", problems[0]["reason"])
        problems = self._problems_for(
            {
                "id": "x6",
                "name": "X",
                "version": "1",
                "api": 1,
                "kind": "importer",
                "target": "tasks",
                "mapping": ["title", "CONTENT"],
            }
        )
        self.assertIn("mapping must be", problems[0]["reason"])

    def test_broken_json_is_a_problem_and_a_stray_file_is_ignored(self):
        folder = os.path.join(plugins.plugins_dir(self.base), "broken")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, plugins.MANIFEST_NAME), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with open(os.path.join(plugins.plugins_dir(self.base), "README.md"), "w", encoding="utf-8") as handle:
            handle.write("notes to self")
        found = plugins.load_plugins(self.base)
        reasons = " | ".join(problem["reason"] for problem in found["problems"])
        self.assertIn("cannot be read", reasons)
        self.assertEqual(len(found["problems"]), 1, "a non-manifest file is not a problem")
        self.assertTrue(found["plugins"], "the shipped manifests still load")

    def test_a_user_plugin_wins_over_a_shipped_one_with_the_same_id(self):
        self._write_plugin(
            {
                "id": "todoist-csv",
                "name": "Mine, not the built-in",
                "version": "2.0",
                "api": 1,
                "kind": "importer",
                "target": "tasks",
                "mapping": {"title": "Task"},
            }
        )
        found = {plugin.id: plugin for plugin in plugins.load_plugins(self.base)["plugins"]}
        self.assertEqual(found["todoist-csv"].name, "Mine, not the built-in")
        self.assertFalse(found["todoist-csv"].builtin)


class TestRunning(_ProfileTmp):
    def test_the_todoist_importer_adds_tasks_with_their_notes(self):
        path = self._csv(
            "todoist.csv",
            TODOIST_HEADERS + "task,2026-09-26,Buy ink,4,black ink for the printer\ntask,,,,\ntask,2026-09-27,Read chapter 4,2,\n",
        )
        report = plugins.run_plugin(self._plugin("todoist-csv"), self.base, path)
        titles = sorted(task["title"] for task in life_service.load_tasks(self.base))
        self.assertEqual(titles, ["Buy ink", "Read chapter 4"])
        self.assertEqual(report["imported"], 2)
        self.assertEqual(report["rows"], 3)
        self.assertEqual(report["skipped"], 1, "the row with no CONTENT is counted, not silently dropped")
        self.assertIn("CONTENT", report["columns"])
        note = [task for task in life_service.load_tasks(self.base) if task["title"] == "Buy ink"][0]
        self.assertIn("black ink", note["notes"])

    def test_a_tab_separated_export_is_read_too(self):
        path = self._csv("ticktick.tsv", "Title\tContent\tList Name\nShip the alpha\tfinish M3\tStudy\n")
        report = plugins.run_plugin(self._plugin("ticktick-csv"), self.base, path)
        self.assertEqual(report["imported"], 1)
        task = life_service.load_tasks(self.base)[0]
        self.assertEqual(task["title"], "Ship the alpha")
        self.assertEqual(task["bucket"], "Study")

    def test_a_user_importer_can_target_notes_and_cards(self):
        self._write_plugin(
            {
                "id": "notes-import",
                "name": "Notes → Mei",
                "version": "1",
                "api": 1,
                "kind": "importer",
                "target": "notes",
                "mapping": {"title": "Title", "body": "Body", "category": "Category"},
            }
        )
        path = self._csv("notes.csv", "Title,Body,Category\nKrebs cycle,citrate,Study\n")
        plugins.run_plugin(self._plugin("notes-import"), self.base, path)
        notes = personal_service.list_notes(self.base)
        self.assertEqual([note["title"] for note in notes], ["Krebs cycle"])
        self.assertIn("citrate", notes[0]["content"])

        self._write_plugin(
            {
                "id": "cards-import",
                "name": "Cards → Mei",
                "version": "1",
                "api": 1,
                "kind": "importer",
                "target": "cards",
                "mapping": {"front": "Front", "back": "Back"},
            }
        )
        deck = self._csv("cards.csv", "Front,Back\nHow many OSI layers?,7\n,no front\n")
        report = plugins.run_plugin(self._plugin("cards-import"), self.base, deck)
        self.assertEqual(report["imported"], 1)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(len(flashcard_service.load_cards(self.base)), 1)

    def test_the_notes_exporter_writes_a_file_other_apps_can_read(self):
        personal_service.create_note(self.base, "Krebs cycle", "citrate", "Study")
        target = os.path.join(self._tmp.name, "out", "notes.csv")
        report = plugins.run_plugin(self._plugin("notes-to-csv"), self.base, target)
        self.assertTrue(os.path.isfile(target))
        self.assertEqual(report["rows"], 1)
        with open(target, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("title,category,body", text)
        self.assertIn("Krebs cycle", text)
        self.assertIn("citrate", text)
        self.assertIn("wrote 1 row(s)", plugins.report_line(report, self._plugin("notes-to-csv")))

    def test_the_deck_exporter_carries_the_schedule(self):
        flashcard_service.add_card(self.base, "Question", "Answer")
        target = os.path.join(self._tmp.name, "deck.csv")
        report = plugins.run_plugin(self._plugin("deck-to-csv"), self.base, target)
        self.assertEqual(report["rows"], 1)
        with open(target, encoding="utf-8") as handle:
            rows = handle.read().splitlines()
        self.assertEqual(rows[0], "front,back,due")
        self.assertEqual(rows[1].split(",")[0], "Question")

    def test_a_missing_file_is_an_error_the_dialog_can_print(self):
        with self.assertRaises(plugins.PluginError):
            plugins.run_plugin(self._plugin("todoist-csv"), self.base, os.path.join(self._tmp.name, "nope.csv"))

    def test_a_kind_that_cannot_be_run_raises_rather_than_guessing(self):
        handmade = plugins.Plugin(
            id="handmade", name="Hand made", version="1", kind="widget", target="tasks", format="csv"
        )
        with self.assertRaises(plugins.PluginError):
            plugins.run_plugin(handmade, self.base, os.path.join(self._tmp.name, "x.csv"))

    def test_a_refused_manifest_leaves_the_profile_alone(self):
        life_service.add_task(self.base, "Keep me")
        self._write_plugin({"id": "x7", "name": "X", "version": "1", "api": 1, "kind": "importer"})
        found = plugins.load_plugins(self.base)
        self.assertTrue(found["problems"])
        self.assertEqual([task["title"] for task in life_service.load_tasks(self.base)], ["Keep me"])
        self.assertEqual(flashcard_service.load_cards(self.base), [])


if __name__ == "__main__":
    unittest.main()
