# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Bundle format contract for the kea migration snapshot.

The snapshot is a single zip archive::

    kea-snapshot-<ts>.zip
    |-- manifest.json          # this module's SnapshotManifest
    |-- postgres/<table>.jsonl  # one JSON object per row, one row per line
    |-- openfga/tuples.json     # every relationship tuple, unfiltered
    |-- keycloak/realm.json     # Keycloak partial export (users + groups)
    `-- content/<key>           # team banner objects, keyed by storage key

The structured files (postgres/openfga/keycloak) are the contract consumed by
both the kea re-import (Phase 1) and the future swift import (Phase 2).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Allowed characters in a user-supplied filename label; everything else is
# collapsed to a dash so the label can never escape the object key.
_LABEL_FORBIDDEN = re.compile(r"[^a-zA-Z0-9_-]+")
_LABEL_MAX_LEN = 40


def sanitize_label(label: str | None) -> str:
    """Reduce a free-text label to a filename-safe slug (possibly empty)."""
    if not label:
        return ""
    slug = _LABEL_FORBIDDEN.sub("-", label.strip()).strip("-").lower()
    return slug[:_LABEL_MAX_LEN].strip("-")


# Durable, user-owned tables to export, in FK-safe restore order.
#
# The runbook keep-list is tag -> metadata -> resource -> teammetadata ->
# users -> agent. We additionally keep ``mcp-server`` because it holds agent
# tooling configuration that would otherwise be lost on restore.
#
# Deliberately excluded (ephemeral / rebuildable): session, session_history,
# session_attachments, session_purge_queue, tasks, sched_workflow_tasks,
# feedbacks, alembic_version*.
EXPORT_TABLES: tuple[str, ...] = (
    "tag",
    "metadata",
    "resource",
    "mcp-server",
    "teammetadata",
    "users",
    "agent",
)

# Format version of the bundle. Bump when the on-disk layout changes so the
# swift-side importer can refuse bundles it does not understand.
BUNDLE_FORMAT_VERSION = 1


class SnapshotManifest(BaseModel):
    """Machine-readable description of a snapshot bundle's contents."""

    format_version: int = BUNDLE_FORMAT_VERSION
    source_platform: str = "kea"
    created_at: str = Field(description="UTC ISO-8601 timestamp of the export")
    tables: dict[str, int] = Field(
        default_factory=dict, description="Row count per exported Postgres table"
    )
    tuple_count: int = 0
    realm_exported: bool = False
    content_keys: list[str] = Field(
        default_factory=list, description="Storage keys of bundled content objects"
    )


class SnapshotRequest(BaseModel):
    """Body of the export endpoint (all fields optional)."""

    label: str | None = Field(
        default=None,
        description="Optional human label embedded in the bundle filename",
    )


class SnapshotResponse(BaseModel):
    """Returned by the export endpoint."""

    object_key: str = Field(description="Key of the bundle in object storage")
    download_url: str = Field(description="Presigned URL to download the bundle")
    manifest: SnapshotManifest


class ImportReport(BaseModel):
    """Returned by the import endpoint — doubles as a verification checklist."""

    source_platform: str
    tables: dict[str, int] = Field(
        default_factory=dict, description="Rows upserted per Postgres table"
    )
    tuples_written: int = 0
    tuples_skipped: int = 0
    content_restored: int = 0
    warnings: list[str] = Field(default_factory=list)
