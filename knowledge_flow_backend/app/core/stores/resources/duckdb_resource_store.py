# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

import json
from pathlib import Path
from typing import List
from pydantic import ValidationError

from fred_core.store.duckdb_store import DuckDBTableStore

from app.core.stores.resources.base_resource_store import BaseResourceStore, ResourceAlreadyExistsError, ResourceNotFoundError
from app.features.resources.structures import Resource, ResourceKind


class DuckdbResourceStore(BaseResourceStore):
    def __init__(self, db_path: Path):
        self.table_name = "resources"
        self.store = DuckDBTableStore(db_path, prefix="resource_")
        self._ensure_schema()

    def _ensure_schema(self):
        full_table = self.store._prefixed(self.table_name)
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    id TEXT PRIMARY KEY,
                    kind TEXT,
                    current_version TEXT,
                    name TEXT,
                    description TEXT,
                    family TEXT,
                    tags JSON,
                    user TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    uri TEXT
                )
            """)

    def _serialize(self, resource: Resource) -> tuple:
        return (
            resource.id,
            resource.kind.value,
            resource.version,
            resource.name,
            resource.description,
            resource.family,
            json.dumps(resource.tags),
            resource.author,
            resource.created_at,
            resource.updated_at,
        )

    def _deserialize(self, row: tuple) -> Resource:
        try:
            return Resource(
                id=row[0],
                kind=ResourceKind(row[1]),
                version=row[2],
                name=row[3],
                description=row[4],
                family=row[5],
                tags=json.loads(row[6]) if row[6] else [],
                author=row[7],
                created_at=row[8],
                updated_at=row[9],
                content=row[10],
            )
        except ValidationError as e:
            raise ResourceNotFoundError(f"Invalid resource structure for {row[0]}: {e}")

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    # -------------------
    # CRUD IMPLEMENTATION
    # -------------------

    def list_resources_for_user(self, user: str, kind: ResourceKind) -> List[Resource]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()} WHERE user = ? AND kind = ?", [user, kind.value]).fetchall()
        return [self._deserialize(row) for row in rows]

    def get_all_resources(self, kind: ResourceKind) -> list[Resource]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()} WHERE kind = ?", [kind.value]).fetchall()
        return [self._deserialize(row) for row in rows]

    def get_resource_by_id(self, resource_id: str) -> Resource:
        with self.store._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._table()} WHERE id = ?", [resource_id]).fetchone()
        if not row:
            raise ResourceNotFoundError(f"No resource with ID {resource_id}")
        return self._deserialize(row)

    def create_resource(self, resource: Resource) -> Resource:
        try:
            self.get_resource_by_id(resource.id)
            raise ResourceAlreadyExistsError(f"Resource with ID {resource.id} already exists.")
        except ResourceNotFoundError:
            pass
        with self.store._connect() as conn:
            conn.execute(f"INSERT INTO {self._table()} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", self._serialize(resource))
        return resource

    def update_resource(self, resource_id: str, resource: Resource) -> Resource:
        self.get_resource_by_id(resource_id)  # Ensure exists
        with self.store._connect() as conn:
            conn.execute(
                f"""
                UPDATE {self._table()}
                SET kind = ?, current_version = ?, name = ?, description = ?, family = ?, tags = ?, 
                    user = ?, created_at = ?, updated_at = ?, uri = ?
                WHERE id = ?
                """,
                (
                    resource.kind.value,
                    resource.version,
                    resource.name,
                    resource.description,
                    resource.family,
                    json.dumps(resource.tags),
                    resource.author,
                    resource.created_at,
                    resource.updated_at,
                    resource.content,
                    resource_id,
                ),
            )
        return resource

    def delete_resource(self, resource_id: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(f"DELETE FROM {self._table()} WHERE id = ?", [resource_id])
        if result.rowcount == 0:
            raise ResourceNotFoundError(f"No resource with ID {resource_id}")

    def get_resources_in_tag(self, tag_id: str) -> List[Resource]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self._table()}
                WHERE json_contains(tags, to_json(?))
                """,
                [tag_id],
            ).fetchall()
        if not rows:
            raise ResourceNotFoundError(f"No resources found for tag {tag_id}")
        return [self._deserialize(row) for row in rows]
