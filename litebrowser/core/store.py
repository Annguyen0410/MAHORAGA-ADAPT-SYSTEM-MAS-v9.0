"""Versioned JSON stores: locking, atomic writes and upgrades in one place.

Every service used to re-implement "read the file, normalise it, write it back",
and each store carried its own idea of versioning (or none). Changing a store's
shape therefore had no upgrade path, and a newer build reading an older profile
silently reinterpreted the data.

A store is described once:

    PLAN_STORE = StoreSpec(
        name="personal_plan.json",
        version=PLAN_VERSION,
        default=_default_plan,
    )

and then read/written through :func:`read_store` / :func:`write_store`, which:

* take the per-profile lock (the profile has one writer, always);
* write atomically via ``storage_utils.write_json``;
* stamp the schema version on every write;
* upgrade older payloads through the stepwise registry in ``core/migrations.py``
  and persist the upgraded payload exactly once;
* refuse to rewrite a payload written by a *newer* build (no silent downgrade).
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from litebrowser.core import migrations
from litebrowser.core.log import get_logger
from litebrowser.core.profile_lock import profile_locked
from litebrowser.core.storage_utils import read_json, write_json

_log = get_logger("store")

VERSION_KEY = "version"
LEGACY_VERSION = 1


class StoreWriteError(OSError):
    """A store cannot be safely rewritten by this build."""


@dataclass(frozen=True)
class StoreSpec:
    name: str
    version: int
    default: Callable[[], Any]
    subdir: str = ""
    migrate: Callable[[dict, int], dict] | None = field(default=None, compare=False)


def store_path(base_dir: str, spec: StoreSpec) -> str:
    directory = os.path.join(base_dir, spec.subdir) if spec.subdir else base_dir
    return os.path.join(directory, spec.name)


def stored_version(raw: Any) -> int:
    """Version of a payload on disk; missing/!garbage means the legacy version."""
    if not isinstance(raw, dict):
        return LEGACY_VERSION
    try:
        return int(raw.get(VERSION_KEY, LEGACY_VERSION) or LEGACY_VERSION)
    except (TypeError, ValueError, OverflowError):
        return LEGACY_VERSION


def _upgrade(raw: Any, spec: StoreSpec, path: str) -> tuple[Any, bool]:
    """Return (payload, persist?) for a payload read from ``path``."""
    if not isinstance(raw, dict):
        return spec.default(), False
    version = stored_version(raw)
    if version > spec.version:
        # A newer build wrote this profile. Leave it alone: rewriting would drop
        # fields this build does not know about.
        _log.warning(
            "%s is version %s but this build understands %s — leaving it untouched",
            path,
            version,
            spec.version,
        )
        return raw, False
    if version == spec.version:
        return raw, False
    try:
        if spec.migrate is not None:
            upgraded = spec.migrate(dict(raw), version)
        else:
            upgraded = migrations.migrate(spec.name, dict(raw), version, spec.version)
    except migrations.MissingMigration as exc:
        _log.warning("cannot upgrade %s: %s", path, exc)
        return raw, False
    if not isinstance(upgraded, dict):
        return raw, False
    upgraded[VERSION_KEY] = spec.version
    _log.info("upgraded %s from version %s to %s", path, version, spec.version)
    return upgraded, True


def read_store(base_dir: str, spec: StoreSpec) -> Any:
    """Read a store, upgrading and persisting an older payload once."""
    path = store_path(base_dir, spec)
    if not os.path.isfile(path):
        return spec.default()
    with profile_locked(base_dir):
        raw = read_json(path, None)
        payload, persist = _upgrade(raw, spec, path)
        if persist:
            write_json(path, payload)
    return payload


def write_store(base_dir: str, spec: StoreSpec, data: Any) -> dict:
    """Stamp the version and write a store atomically under the profile lock."""
    path = store_path(base_dir, spec)
    payload = dict(data) if isinstance(data, dict) else {}
    with profile_locked(base_dir):
        if os.path.isfile(path):
            existing = read_json(path, None)
            if existing is None:
                raise StoreWriteError(f"Cannot overwrite unreadable store: {spec.name}")
            if stored_version(existing) > spec.version:
                raise StoreWriteError(
                    f"{spec.name} belongs to a newer Mei build; upgrade before editing it"
                )
        if stored_version(payload) > spec.version:
            raise StoreWriteError(f"Unsupported {spec.name} schema version")
        payload[VERSION_KEY] = spec.version
        write_json(path, payload)
    return payload
