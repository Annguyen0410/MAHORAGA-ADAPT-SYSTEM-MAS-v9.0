"""Versioned stores: upgrade path, one-time migration, no silent downgrade."""
import json
import os
import tempfile
import unittest

from litebrowser.core import migrations, prefs
from litebrowser.core.store import StoreWriteError, StoreSpec, read_store, store_path, stored_version, write_store
from litebrowser.services import personal_plan, tab_sets

FAKE = StoreSpec(name="fake_store.json", version=1, default=lambda: {"rows": []})


def _spec(version=1, default=None, migrate=None):
    return StoreSpec(
        name="fake_store.json",
        version=version,
        default=default or (lambda: {"rows": []}),
        migrate=migrate,
    )


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write_raw(self, spec, payload):
        path = store_path(self.base, spec)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return path

    def _read_raw(self, spec):
        path = store_path(self.base, spec)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


class TestReadWrite(_Base):
    def test_missing_store_returns_default(self):
        self.assertEqual(read_store(self.base, FAKE), {"rows": []})

    def test_write_stamps_the_version(self):
        write_store(self.base, FAKE, {"rows": [1]})
        self.assertEqual(self._read_raw(FAKE)["version"], FAKE.version)

    def test_write_ignores_non_dict_payloads(self):
        write_store(self.base, FAKE, ["nope"])
        self.assertEqual(self._read_raw(FAKE), {"version": FAKE.version})

    def test_stored_version_defaults_to_legacy(self):
        self.assertEqual(stored_version({}), 1)
        self.assertEqual(stored_version({"version": "3"}), 3)
        self.assertEqual(stored_version({"version": "junk"}), 1)
        self.assertEqual(stored_version(None), 1)

    def test_round_trip_preserves_rows(self):
        write_store(self.base, FAKE, {"rows": [{"id": "a"}]})
        self.assertEqual(read_store(self.base, FAKE)["rows"], [{"id": "a"}])


class TestUpgradePath(_Base):
    def test_custom_migrate_callback_runs_once_and_is_persisted(self):
        calls = []

        def migrate(data, from_version):
            calls.append(from_version)
            return {"rows": data.get("rows", []) + ["migrated"]}

        spec = _spec(version=2, migrate=migrate)
        self._write_raw(spec, {"version": 1, "rows": ["a"]})

        self.assertEqual(read_store(self.base, spec)["rows"], ["a", "migrated"])
        self.assertEqual(calls, [1])
        self.assertEqual(self._read_raw(spec)["version"], 2)
        # Second read is a no-op: the upgrade already landed on disk.
        read_store(self.base, spec)
        self.assertEqual(calls, [1])

    def test_legacy_payload_without_version_is_upgraded(self):
        spec = _spec(version=2, migrate=lambda data, _v: {"rows": ["upgraded"]})
        self._write_raw(spec, {"rows": []})  # no "version" key at all
        self.assertEqual(read_store(self.base, spec)["rows"], ["upgraded"])

    def test_registry_steps_run_in_order(self):
        migrations.STEPS.pop("stepped.json", None)

        @migrations.register("stepped.json", from_version=1)
        def step_one(data):
            return {"steps": data.get("steps", []) + ["one"]}

        @migrations.register("stepped.json", from_version=2)
        def step_two(data):
            return {"steps": data.get("steps", []) + ["two"]}

        spec = StoreSpec(name="stepped.json", version=3, default=lambda: {"steps": []})
        self._write_raw(spec, {"version": 1, "steps": []})
        self.assertEqual(read_store(self.base, spec)["steps"], ["one", "two"])
        self.assertEqual(self._read_raw(spec)["version"], 3)
        self.assertEqual(migrations.registered_versions("stepped.json"), (1, 2))

    def test_missing_step_leaves_the_file_alone(self):
        migrations.STEPS.pop("gap.json", None)
        spec = StoreSpec(name="gap.json", version=3, default=lambda: {"rows": []})
        self._write_raw(spec, {"version": 1, "rows": ["keep"]})
        self.assertEqual(read_store(self.base, spec)["rows"], ["keep"])
        self.assertEqual(self._read_raw(spec)["version"], 1, "a half-upgrade must not be written back")

    def test_migration_returning_garbage_is_ignored(self):
        spec = _spec(version=2, migrate=lambda _data, _v: "not a dict")
        self._write_raw(spec, {"version": 1, "rows": ["keep"]})
        self.assertEqual(read_store(self.base, spec)["rows"], ["keep"])
        self.assertEqual(self._read_raw(spec)["version"], 1)


class TestNewerBuildIsNotDowngraded(_Base):
    def test_newer_version_is_read_but_not_rewritten(self):
        spec = _spec(version=1)
        self._write_raw(spec, {"version": 9, "rows": ["from the future"], "extra": True})
        data = read_store(self.base, spec)
        self.assertEqual(data["rows"], ["from the future"])
        self.assertEqual(self._read_raw(spec)["version"], 9, "a newer profile must be left intact")
        self.assertTrue(self._read_raw(spec)["extra"])

    def test_mutation_cannot_downgrade_a_future_store(self):
        spec = _spec(version=1)
        original = {"version": 9, "rows": ["future"], "extra": True}
        self._write_raw(spec, original)
        with self.assertRaises(StoreWriteError):
            write_store(self.base, spec, {"rows": ["older build"]})
        self.assertEqual(self._read_raw(spec), original)

    def test_planner_mutation_leaves_a_future_schema_intact(self):
        original = {"version": 99, "items": [{"id": "x", "title": "Keep"}], "future": True}
        self._write_raw(personal_plan.PLAN_STORE, original)
        with self.assertRaises(StoreWriteError):
            personal_plan.create_item(self.base, "Cannot downgrade")
        self.assertEqual(self._read_raw(personal_plan.PLAN_STORE), original)

    def test_corrupt_store_cannot_be_silently_overwritten(self):
        path = self._write_raw(FAKE, {})
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{broken")
        with self.assertRaises(StoreWriteError):
            write_store(self.base, FAKE, {"rows": []})
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{broken")

    def test_corrupt_store_falls_back_without_deleting_it(self):
        spec = _spec()
        path = self._write_raw(spec, {"version": 1, "rows": ["x"]})
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(read_store(self.base, spec), spec.default())
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{not json")


class TestRealStores(_Base):
    def test_tab_sets_v1_file_is_migrated_to_v2(self):
        path = os.path.join(self.base, tab_sets.TAB_SETS_FILENAME)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "sets": [{"id": "s1", "title": "Old set", "tabs": [{"url": "https://a", "title": "A"}]}],
                },
                handle,
            )
        loaded = tab_sets.load_tab_sets(self.base)
        self.assertEqual([item["id"] for item in loaded["sets"]], ["s1"])
        self.assertEqual(loaded["version"], tab_sets.SCHEMA_VERSION)
        with open(path, encoding="utf-8") as handle:
            on_disk = json.load(handle)
        self.assertEqual(on_disk["version"], tab_sets.SCHEMA_VERSION)
        self.assertEqual(on_disk["sets"][0]["kind"], "collection")
        self.assertEqual(on_disk["sets"][0]["title"], "Old set")

    def test_tab_sets_save_stamps_current_version(self):
        tab_sets.save_tab_sets(self.base, {"sets": [{"id": "s2", "kind": "search", "title": "T", "tabs": []}]})
        with open(os.path.join(self.base, tab_sets.TAB_SETS_FILENAME), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["version"], tab_sets.SCHEMA_VERSION)

    def test_planner_store_is_versioned(self):
        personal_plan.create_item(self.base, "Essay")
        with open(personal_plan.plan_path(self.base), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["version"], personal_plan.PLAN_VERSION)
        # A legacy planner file without the version key still loads.
        with open(personal_plan.plan_path(self.base), "w", encoding="utf-8") as handle:
            json.dump({"items": [{"id": "x", "title": "Legacy"}]}, handle)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["title"], "Legacy")

    def test_planner_v1_file_is_migrated_to_v2(self):
        path = personal_plan.plan_path(self.base)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "items": [{"id": "x", "title": "Legacy"}]}, handle)
        loaded = personal_plan.load_plan(self.base)
        self.assertEqual(loaded["items"][0]["studied_minutes"], 0)
        self.assertEqual(loaded["version"], personal_plan.PLAN_VERSION)
        with open(path, encoding="utf-8") as handle:
            on_disk = json.load(handle)
        self.assertEqual(on_disk["version"], personal_plan.PLAN_VERSION)
        self.assertEqual(on_disk["items"][0]["studied_minutes"], 0)


class TestSyncRegistryAndStoresShareTheContract(_Base):
    def test_sync_bundle_and_report_come_from_one_registry(self):
        from litebrowser.services import sync_service

        bundle = sync_service._bundle(self.base)
        applied = sync_service._apply_bundle(self.base, bundle)
        self.assertEqual(
            [entity.key for entity in sync_service.SYNC_ENTITIES],
            [key for key in bundle if key not in ("app", "kind", "api", "exported_at")],
        )
        self.assertEqual(set(applied), {entity.counter for entity in sync_service.SYNC_ENTITIES})


if __name__ == "__main__":
    unittest.main()
