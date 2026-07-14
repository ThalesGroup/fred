"""Kea snapshot zip reader for the swift importer (MIGR-05)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from control_plane_backend.import_export.schemas import BundleUserEntry


@dataclass(frozen=True)
class SnapshotManifest:
    format_version: int
    source_platform: str
    created_at: str
    tables: dict[str, int]
    tuple_count: int
    realm_exported: bool
    content_keys: list[str]


class KBundle:
    """An opened kea snapshot zip, ready to iterate over tables and tuples."""

    def __init__(self, zf: zipfile.ZipFile, manifest: SnapshotManifest) -> None:
        self._zf = zf
        self.manifest = manifest

    def iter_table(self, table: str) -> Iterator[dict[str, Any]]:
        """Yield one dict per row from a postgres/<table>.jsonl entry."""
        path = f"postgres/{table}.jsonl"
        try:
            data = self._zf.read(path).decode("utf-8")
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

        AUTHZ-07 Part 8 §40.2 / PLATFORM-IMPORT-RFC.md §10: declarative platform
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
    """Open a kea snapshot zip from raw bytes and parse its manifest."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    raw = json.loads(zf.read("manifest.json"))
    manifest = SnapshotManifest(
        format_version=raw.get("format_version", 1),
        source_platform=raw.get("source_platform", "kea"),
        created_at=raw.get("created_at", ""),
        tables=raw.get("tables", {}),
        tuple_count=raw.get("tuple_count", 0),
        realm_exported=raw.get("realm_exported", False),
        content_keys=raw.get("content_keys", []),
    )
    return KBundle(zf, manifest)
