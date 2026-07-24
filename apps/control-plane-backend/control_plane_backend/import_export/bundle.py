"""Kea snapshot zip reader for the swift importer (MIGR-05)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from control_plane_backend.import_export.schemas import BundleUserEntry

# Canonical contract — swift-native baseline (PLATFORM-IMPORT-RFC.md). Two
# independent version numbers because they change at different rates:
# format_version is the container's own shape (which top-level files/tables
# exist); users_schema_version is BundleUserEntry's field set, which already
# grew once (identity fields) without a container version bump.
SUPPORTED_FORMAT_VERSIONS: frozenset[int] = frozenset({1})
SUPPORTED_USERS_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


class UnsupportedBundleFormatError(ValueError):
    """manifest.json declares a format/schema version this importer doesn't understand."""


class SnapshotManifest(BaseModel):
    """Typed, validated `manifest.json` — parity with `BundleUserEntry`.

    Replaces the previous hand-built `@dataclass` populated via
    `raw.get(key, default)`, which accepted any JSON shape silently.
    `format_version`/`users_schema_version` are checked against the supported
    sets in `open_bundle()` — no other field changes behavior.
    """

    model_config = ConfigDict(frozen=True)

    format_version: int
    users_schema_version: int
    source_platform: str = "kea"
    created_at: str = ""
    tables: dict[str, int] = Field(default_factory=dict)
    tuple_count: int = 0
    realm_exported: bool = False
    content_keys: list[str] = Field(default_factory=list)


class KBundle:
    """An opened kea snapshot zip, ready to iterate over tables and tuples."""

    def __init__(self, zf: zipfile.ZipFile, manifest: SnapshotManifest) -> None:
        self._zf = zf
        self.manifest = manifest

    def iter_table(self, table: str) -> Iterator[dict[str, Any]]:
        """Yield one dict per row from a postgres/<table>.jsonl entry.

        `table` must be the file name the producer actually wrote: kea bundles
        use main's `migration/snapshot.py::EXPORT_TABLES` names verbatim
        (`teammetadata`, `mcp-server`, …); swift-native bundles use the names
        `exporter.py` writes (`team_metadata`, `agent_instance`, …).
        """
        try:
            data = self._zf.read(f"postgres/{table}.jsonl").decode("utf-8")
        except KeyError:
            return
        for line in data.splitlines():
            line = line.strip()
            if line:
                row = json.loads(line)
                # payload_json may be a nested JSON string — normalise to dict
                if "payload_json" in row and isinstance(row["payload_json"], str):
                    try:
                        row["payload_json"] = json.loads(row["payload_json"])
                    except json.JSONDecodeError:  # nosec B110 - not nested JSON: keep raw string
                        pass
                yield row

    def openfga_tuples(self) -> list[dict[str, Any]]:
        """Return the raw OpenFGA tuples list, empty list if absent."""
        try:
            return json.loads(self._zf.read("openfga/tuples.json"))
        except KeyError:
            return []

    def demo_users(self) -> list[BundleUserEntry]:
        """Return the typed users.json provisioning list, empty list if absent.

        AUTHZ-07 Part 8 §40.2 / PLATFORM-IMPORT-RFC.md §6: declarative platform
        provisioning for identities/teams/roles/users. Unlike `postgres/<table>.jsonl`
        rows, these entries are not Postgres rows — each one describes an optional
        Keycloak identity to create (email/first_name/last_name/password) plus the
        desired Fred-side authorization state (team membership, team roles, platform
        roles) for that identity. See `importer.py`'s users phase (identity creation,
        then role provisioning) for how each entry is applied.
        """
        try:
            raw = json.loads(self._zf.read("users.json"))
        except KeyError:
            return []
        return [BundleUserEntry.model_validate(entry) for entry in raw]

    def close(self) -> None:
        self._zf.close()


def open_bundle(data: bytes) -> KBundle:
    """Open a snapshot zip from raw bytes, parse and validate its manifest.

    Rejects a bundle whose `format_version`/`users_schema_version` isn't in
    the supported set — no silent default when the key is absent or wrong,
    per the canonical contract in `PLATFORM-IMPORT-RFC.md`.
    """
    zf = zipfile.ZipFile(io.BytesIO(data))
    raw = json.loads(zf.read("manifest.json"))
    # Kea's exporter (main branch, `migration/snapshot.py`) predates the
    # `users_schema_version` field and will never emit it — kea bundles also
    # never carry a `users.json`, so the field is meaningless for them. Default
    # it for non-swift bundles only; swift producers must keep declaring both
    # versions explicitly (no silent default), per PLATFORM-IMPORT-RFC.md §4.
    if raw.get("source_platform", "kea") != "swift":
        raw.setdefault("users_schema_version", 1)
    manifest = SnapshotManifest.model_validate(raw)
    if manifest.format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise UnsupportedBundleFormatError(
            f"Unsupported bundle format_version {manifest.format_version}; "
            f"this importer understands {sorted(SUPPORTED_FORMAT_VERSIONS)}"
        )
    if manifest.users_schema_version not in SUPPORTED_USERS_SCHEMA_VERSIONS:
        raise UnsupportedBundleFormatError(
            f"Unsupported users.json schema version {manifest.users_schema_version}; "
            f"this importer understands {sorted(SUPPORTED_USERS_SCHEMA_VERSIONS)}"
        )
    return KBundle(zf, manifest)
