# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import List

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import ValidationError

from app.core.stores.resources.base_resource_store import (
    BaseResourceStore,
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
)
from app.features.resources.structures import Resource, ResourceKind


class DuckdbResourceStore(BaseResourceStore):
    def __init__(self, db_path: Path):
        self.table_name = "resources"
        self.store = DuckDBTableStore(db_path, prefix="resource_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    # --- schema ---

    def _ensure_schema(self):
        full_table = self._table()
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{full_table}" (
                    id TEXT PRIMARY KEY,
                    kind TEXT,
                    version TEXT,
                    name TEXT,
                    description TEXT,
                    labels VARCHAR[],
                    author TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    content TEXT,
                    library_tags VARCHAR[]
                )
            """)
            # Optional: light migration from earlier drifted schema
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{full_table}")').fetchall()}
            # Add missing columns if the table existed with older layout
            if "labels" not in cols:
                conn.execute(f'ALTER TABLE "{full_table}" ADD COLUMN labels VARCHAR[]')
            if "library_tags" not in cols:
                conn.execute(f'ALTER TABLE "{full_table}" ADD COLUMN library_tags VARCHAR[]')
            if "version" not in cols and "current_version" in cols:
                # If they had current_version, create a view/alias by adding proper column and copying
                conn.execute(f'ALTER TABLE "{full_table}" ADD COLUMN version TEXT')
                conn.execute(f'UPDATE "{full_table}" SET version = current_version')
            if "author" not in cols and "user" in cols:
                conn.execute(f'ALTER TABLE "{full_table}" ADD COLUMN author TEXT')
                conn.execute(f'UPDATE "{full_table}" SET author = user')
            if "content" not in cols and "uri" in cols:
                conn.execute(f'ALTER TABLE "{full_table}" ADD COLUMN content TEXT')
                conn.execute(f'UPDATE "{full_table}" SET content = uri')

    # --- serde ---

    def _serialize(self, r: Resource) -> tuple:
        return (
            r.id,
            r.kind.value,
            r.version,
            r.name,
            r.description,
            (r.labels or []),
            r.author,
            r.created_at,
            r.updated_at,
            r.content,
            (r.library_tags or []),
        )

    def _deserialize(self, row: tuple) -> Resource:
        try:
            return Resource(
                id=row[0],
                kind=ResourceKind(row[1]),
                version=row[2],
                name=row[3],
                description=row[4],
                labels=list(row[5] or []),
                author=row[6],
                created_at=row[7],
                updated_at=row[8],
                content=row[9],
                library_tags=list(row[10] or []),
            )
        except ValidationError as e:
            raise ResourceNotFoundError(f"Invalid resource structure for {row[0]}: {e}")

    # --- CRUD ---

    def list_resources_for_user(self, user: str, kind: ResourceKind) -> List[Resource]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT * FROM "{self._table()}" WHERE author = ? AND kind = ?',
                [user, kind.value],
            ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_all_resources(self, kind: ResourceKind) -> List[Resource]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT * FROM "{self._table()}" WHERE kind = ?',
                [kind.value],
            ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_resource_by_id(self, resource_id: str) -> Resource:
        with self.store._connect() as conn:
            row = conn.execute(
                f'SELECT * FROM "{self._table()}" WHERE id = ?',
                [resource_id],
            ).fetchone()
        if not row:
            raise ResourceNotFoundError(f"No resource with ID {resource_id}")
        return self._deserialize(row)

    def create_resource(self, resource: Resource) -> Resource:
        # ensure not exists
        try:
            self.get_resource_by_id(resource.id)
            raise ResourceAlreadyExistsError(f"Resource with ID {resource.id} already exists.")
        except ResourceNotFoundError:
            pass

        with self.store._connect() as conn:
            conn.execute(
                f'INSERT INTO "{self._table()}" (id, kind, version, name, description, labels, author, created_at, updated_at, content, library_tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                self._serialize(resource),
            )
        return resource

    def update_resource(self, resource_id: str, resource: Resource) -> Resource:
        # ensure exists
        self.get_resource_by_id(resource_id)

        with self.store._connect() as conn:
            conn.execute(
                f"""
                UPDATE "{self._table()}"
                SET
                    kind = ?,
                    version = ?,
                    name = ?,
                    description = ?,
                    labels = ?,
                    author = ?,
                    created_at = ?,
                    updated_at = ?,
                    content = ?,
                    library_tags = ?
                WHERE id = ?
                """,
                (
                    resource.kind.value,
                    resource.version,
                    resource.name,
                    resource.description,
                    (resource.labels or []),
                    resource.author,
                    resource.created_at,
                    resource.updated_at,
                    resource.content,
                    (resource.library_tags or []),
                    resource_id,
                ),
            )
        return resource

    def delete_resource(self, resource_id: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(
                f'DELETE FROM "{self._table()}" WHERE id = ?',
                [resource_id],
            )
        if result.rowcount == 0:
            raise ResourceNotFoundError(f"No resource with ID {resource_id}")

    def get_resources_in_tag(self, tag_id: str) -> List[Resource]:
        # library_tags is a LIST(VARCHAR), so we can use list_contains
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT * FROM "{self._table()}" WHERE list_contains(library_tags, ?)',
                [tag_id],
            ).fetchall()
        if not rows:
            raise ResourceNotFoundError(f"No resources found for tag {tag_id}")
        return [self._deserialize(r) for r in rows]
