# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from pathlib import Path
from typing import List, Optional

from fred_core import KeycloakUser
from fred_core.store.duckdb_store import DuckDBTableStore

from knowledge_flow_backend.core.stores.tags.base_tag_store import BaseTagStore, TagAlreadyExistsError, TagNotFoundError
from knowledge_flow_backend.features.tag.structure import Tag, TagType

logger = logging.getLogger(__name__)


def _compose_full_path(path: Optional[str], name: str) -> str:
    return f"{path}/{name}" if path else name


class DuckdbTagStore(BaseTagStore):
    """
    DuckDB implementation of BaseTagStore.
    Creates table if not exists and migrates schema if needed.
    Tags are scoped per user via `owner_id`.
    """

    def __init__(self, db_path: Path):
        self.table_name = "tags"
        self.store = DuckDBTableStore(db_path, prefix="tag_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    def _ensure_schema(self) -> None:
        with self.store._connect() as conn:
            # 1) Create table if it doesn't exist (with the full, current schema)
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self._table()}" (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    owner_id TEXT,
                    name TEXT,
                    path TEXT,
                    description TEXT,
                    type TEXT
                )
                """
            )

            # 2) Idempotent migration: add missing columns if upgrading from older schema
            cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{self._table()}")').fetchall()}
            if "path" not in cols:
                conn.execute(f'ALTER TABLE "{self._table()}" ADD COLUMN path TEXT')
                logger.info(f"[TAGS] Migrated DuckDB table '{self._table()}' - added column 'path'.")

        logger.info(f"[TAGS] DuckDB table '{self._table()}' ensured.")

    # ---- (De)serialization helpers using explicit column order ----

    def _serialize(self, tag: Tag) -> tuple:
        # Order MUST match the INSERT column list below
        return (
            tag.id,
            tag.created_at,
            tag.updated_at,
            tag.owner_id,
            tag.name,
            tag.path,
            tag.description,
            tag.type.value,
        )

    def _deserialize(self, row: tuple) -> Tag:
        # Row order MUST match the SELECT column list used in queries
        return Tag(
            id=row[0],
            created_at=row[1],
            updated_at=row[2],
            owner_id=row[3],
            name=row[4],
            path=row[5],
            description=row[6],
            type=TagType(row[7]),
        )

    # ---- CRUD ----

    def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        try:
            with self.store._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT id, created_at, updated_at, owner_id, name, path, description, type
                    FROM "{self._table()}"
                    ORDER BY COALESCE(path, ''), name
                    """,
                ).fetchall()
            return [self._deserialize(row) for row in rows]
        except Exception as e:
            logger.error(f"[TAGS] Failed to list tags for user '{user.uid}': {e}")
            raise

    def get_tag_by_id(self, tag_id: str) -> Tag:
        with self.store._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, created_at, updated_at, owner_id, name, path, description, type
                FROM "{self._table()}"
                WHERE id = ?
                """,
                [tag_id],
            ).fetchone()
        if not row:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        return self._deserialize(row)

    def create_tag(self, tag: Tag) -> Tag:
        # Fail if already exists
        try:
            self.get_tag_by_id(tag.id)
            raise TagAlreadyExistsError(f"Tag with id '{tag.id}' already exists.")
        except TagNotFoundError:
            pass
        try:
            with self.store._connect() as conn:
                conn.execute(
                    f"""
                    INSERT INTO "{self._table()}" (
                        id, created_at, updated_at, owner_id, name, path, description, type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._serialize(tag),
                )
            logger.info(f"[TAGS] Created tag '{tag.id}' for user '{tag.owner_id}'")
            return tag
        except Exception as e:
            logger.error(f"[TAGS] Failed to create tag '{tag.id}': {e}")
            raise

    def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        self.get_tag_by_id(tag_id)  # Raises if not found
        try:
            with self.store._connect() as conn:
                conn.execute(
                    f"""
                    UPDATE "{self._table()}"
                    SET created_at = ?,
                        updated_at = ?,
                        owner_id   = ?,
                        name       = ?,
                        path       = ?,         -- ✅ update path
                        description= ?,
                        type       = ?
                    WHERE id = ?
                    """,
                    (
                        tag.created_at,
                        tag.updated_at,
                        tag.owner_id,
                        tag.name,
                        tag.path,  # ✅ include path
                        tag.description,
                        tag.type.value,
                        tag_id,
                    ),
                )
            logger.info(f"[TAGS] Updated tag '{tag_id}'")
            return tag
        except Exception as e:
            logger.error(f"[TAGS] Failed to update tag '{tag_id}': {e}")
            raise

    def delete_tag_by_id(self, tag_id: str) -> None:
        try:
            with self.store._connect() as conn:
                result = conn.execute(f'DELETE FROM "{self._table()}" WHERE id = ?', [tag_id])
            if result.rowcount == 0:
                raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
            logger.info(f"[TAGS] Deleted tag '{tag_id}'")
        except TagNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[TAGS] Failed to delete tag '{tag_id}': {e}")
            raise

    # ---- Lookup by full path (owner + type + "a/b/name") ----

    def get_by_owner_type_full_path(self, owner_id: str, tag_type: TagType, full_path: str) -> Tag | None:
        """
        Match against computed full_path:
          - if path is NULL/empty → full_path = name
          - else → full_path = path || '/' || name
        """
        with self.store._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, created_at, updated_at, owner_id, name, path, description, type
                FROM {self._table()}
                WHERE owner_id = ?
                  AND type = ?
                  AND CASE WHEN path IS NULL OR path = ''
                           THEN name
                           ELSE path || '/' || name
                      END = ?
                LIMIT 1
                """,
                [owner_id, tag_type.value, full_path],
            ).fetchone()
        return self._deserialize(row) if row else None

    @staticmethod
    def _normalize_path_for_query(p: str) -> str:
        # Mirror service normalization; DB comparisons are done case-insensitively via LOWER()
        parts = [seg.strip() for seg in p.split("/") if seg.strip()]
        return "/".join(parts)
