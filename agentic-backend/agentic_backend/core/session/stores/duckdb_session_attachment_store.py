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

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fred_core.store.duckdb_store import DuckDBTableStore

from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
    SessionAttachmentRecord,
)

logger = logging.getLogger(__name__)


def _to_iso_utc(dt: datetime | str | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DuckdbSessionAttachmentStore(BaseSessionAttachmentStore):
    """
    DuckDB-backed storage for session attachments summaries.
    Mirrors the PostgreSQL/OpenSearch attachment stores for backward compatibility.
    """

    def __init__(self, db_path: Path):
        self.store = DuckDBTableStore(prefix="session_", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attachments (
                    session_id TEXT,
                    attachment_id TEXT,
                    name TEXT,
                    mime TEXT,
                    size_bytes BIGINT,
                    summary_md TEXT,
                    document_uid TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (session_id, attachment_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachments_session ON attachments(session_id, created_at)"
            )

    def save(self, record: SessionAttachmentRecord) -> None:
        now = datetime.now(timezone.utc)
        created_at = _to_iso_utc(record.created_at) or _to_iso_utc(now)
        updated_at = _to_iso_utc(record.updated_at) or _to_iso_utc(now)
        with self.store._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO attachments
                (session_id, attachment_id, name, mime, size_bytes, summary_md, document_uid, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
                    record.attachment_id,
                    record.name,
                    record.mime,
                    record.size_bytes,
                    record.summary_md,
                    record.document_uid,
                    created_at,
                    updated_at,
                ),
            )

    def list_for_session(self, session_id: str) -> List[SessionAttachmentRecord]:
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, attachment_id, name, mime, size_bytes, summary_md, document_uid, created_at, updated_at
                FROM attachments
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        records: List[SessionAttachmentRecord] = []
        for r in rows:
            records.append(
                SessionAttachmentRecord(
                    session_id=r[0],
                    attachment_id=r[1],
                    name=r[2],
                    mime=r[3],
                    size_bytes=r[4],
                    summary_md=r[5],
                    document_uid=r[6],
                    created_at=r[7],
                    updated_at=r[8],
                )
            )
        return records

    def delete(self, session_id: str, attachment_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "DELETE FROM attachments WHERE session_id = ? AND attachment_id = ?",
                (session_id, attachment_id),
            )

    def delete_for_session(self, session_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute("DELETE FROM attachments WHERE session_id = ?", (session_id,))
