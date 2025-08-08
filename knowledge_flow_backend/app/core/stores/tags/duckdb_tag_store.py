import logging
from pathlib import Path
from typing import List

from fred_core import KeycloakUser
from fred_core.store.duckdb_store import DuckDBTableStore
from app.core.stores.tags.base_tag_store import BaseTagStore, TagNotFoundError, TagAlreadyExistsError
from app.features.tag.structure import Tag, TagType

logger = logging.getLogger(__name__)


class DuckdbTagStore(BaseTagStore):
    """
    DuckDB implementation of BaseTagStore.
    Creates table if not exists. Tags are scoped per user via `owner_id`.
    """

    def __init__(self, db_path: Path):
        self.table_name = "tags"
        self.store = DuckDBTableStore(db_path, prefix="tag_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    def _ensure_schema(self) -> None:
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._table()} (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    owner_id TEXT,
                    name TEXT,
                    description TEXT,
                    type TEXT
                )
            """)
        logger.info(f"[TAGS] DuckDB table '{self._table()}' ensured.")

    def _serialize(self, tag: Tag) -> tuple:
        return (tag.id, tag.created_at, tag.updated_at, tag.owner_id, tag.name, tag.description, tag.type.value)

    def _deserialize(self, row: tuple) -> Tag:
        return Tag(id=row[0], created_at=row[1], updated_at=row[2], owner_id=row[3], name=row[4], description=row[5], type=TagType(row[6]))

    def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        try:
            with self.store._connect() as conn:
                rows = conn.execute(f"SELECT * FROM {self._table()} WHERE owner_id = ?", [user.uid]).fetchall()
            return [self._deserialize(row) for row in rows]
        except Exception as e:
            logger.error(f"[TAGS] Failed to list tags for user '{user.uid}': {e}")
            raise

    def get_tag_by_id(self, tag_id: str) -> Tag:
        with self.store._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._table()} WHERE id = ?", [tag_id]).fetchone()
        if not row:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        return self._deserialize(row)

    def create_tag(self, tag: Tag) -> Tag:
        try:
            # Check existence first
            self.get_tag_by_id(tag.id)
            raise TagAlreadyExistsError(f"Tag with id '{tag.id}' already exists.")
        except TagNotFoundError:
            pass  # Expected path
        try:
            with self.store._connect() as conn:
                conn.execute(f"INSERT INTO {self._table()} VALUES (?, ?, ?, ?, ?, ?, ?)", self._serialize(tag))
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
                    UPDATE {self._table()}
                    SET created_at = ?, updated_at = ?, owner_id = ?, name = ?, description = ?, type = ?
                    WHERE id = ?
                    """,
                    (tag.created_at, tag.updated_at, tag.owner_id, tag.name, tag.description, tag.type.value, tag_id),
                )
            logger.info(f"[TAGS] Updated tag '{tag_id}'")
            return tag
        except Exception as e:
            logger.error(f"[TAGS] Failed to update tag '{tag_id}': {e}")
            raise

    def delete_tag_by_id(self, tag_id: str) -> None:
        try:
            with self.store._connect() as conn:
                result = conn.execute(f"DELETE FROM {self._table()} WHERE id = ?", [tag_id])
            if result.rowcount == 0:
                raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
            logger.info(f"[TAGS] Deleted tag '{tag_id}'")
        except TagNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[TAGS] Failed to delete tag '{tag_id}': {e}")
            raise
