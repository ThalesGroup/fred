"""Kea snapshot zip reader for the swift importer (MIGR-05)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


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
                    except Exception:
                        pass
                yield row

    def openfga_tuples(self) -> list[dict[str, Any]]:
        """Return the raw OpenFGA tuples list, empty list if absent."""
        try:
            return json.loads(self._zf.read("openfga/tuples.json"))
        except KeyError:
            return []

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
