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

import json
from pathlib import Path
from typing import List
from pydantic import ValidationError
from app.core.stores.prompts.base_prompt_store import (
    BasePromptStore,
    PromptNotFoundError,
    PromptAlreadyExistsError,
)
from app.features.prompts.structure import Prompt
from fred_core.store.duckdb_store import DuckDBTableStore


class DuckdbPromptStore(BasePromptStore):
    def __init__(self, db_path: Path):
        self.table_name = "prompts"
        self.store = DuckDBTableStore(db_path, prefix="prompt_")
        self._ensure_schema()

    def _ensure_schema(self):
        full_table = self.store._prefixed(self.table_name)
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    content TEXT,
                    description TEXT,
                    tags JSON,
                    owner_id TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)

    def _serialize(self, prompt: Prompt) -> tuple:
        return (
            prompt.id,
            prompt.name,
            prompt.content,
            prompt.description,
            json.dumps(prompt.tags),
            prompt.owner_id,
            prompt.created_at,
            prompt.updated_at,
        )

    def _deserialize(self, row: tuple) -> Prompt:
        try:
            return Prompt(
                id=row[0],
                name=row[1],
                content=row[2],
                description=row[3],
                tags=json.loads(row[4]) if row[4] else [],
                owner_id=row[5],
                created_at=row[6],
                updated_at=row[7],
            )
        except ValidationError as e:
            raise PromptNotFoundError(f"Invalid prompt structure for {row[0]}: {e}")

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    def list_prompts_for_user(self, user: str) -> List[Prompt]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()} WHERE owner_id = ?", [user]).fetchall()
        return [self._deserialize(row) for row in rows]

    def get_all_prompts(self) -> list[Prompt]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()}").fetchall()
        return [self._deserialize(row) for row in rows]
    
    def get_prompt_by_id(self, prompt_id: str) -> Prompt:
        with self.store._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._table()} WHERE id = ?", [prompt_id]).fetchone()
        if not row:
            raise PromptNotFoundError(f"No prompt with ID {prompt_id}")
        return self._deserialize(row)

    def create_prompt(self, prompt: Prompt) -> Prompt:
        try:
            self.get_prompt_by_id(prompt.id)
            raise PromptAlreadyExistsError(f"Prompt with ID {prompt.id} already exists.")
        except PromptNotFoundError:
            pass
        with self.store._connect() as conn:
            conn.execute(f"INSERT INTO {self._table()} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", self._serialize(prompt))
        return prompt

    def update_prompt(self, prompt_id: str, prompt: Prompt) -> Prompt:
        self.get_prompt_by_id(prompt_id)  # Ensure it exists
        with self.store._connect() as conn:
            conn.execute(
                f"""
                UPDATE {self._table()}
                SET name = ?, content = ?, description = ?, tags = ?, owner_id = ?, created_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    prompt.name,
                    prompt.content,
                    prompt.description,
                    json.dumps(prompt.tags),
                    prompt.owner_id,
                    prompt.created_at,
                    prompt.updated_at,
                    prompt_id,
                ),
            )
        return prompt

    def delete_prompt(self, prompt_id: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(f"DELETE FROM {self._table()} WHERE id = ?", [prompt_id])
        if result.rowcount == 0:
            raise PromptNotFoundError(f"No prompt with ID {prompt_id}")

    def get_prompt_in_tag(self, tag_id: str) -> List[Prompt]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self._table()}
                WHERE json_contains(tags, to_json(?))
                """,
                [tag_id],
            ).fetchall()
        if not rows:
            raise PromptNotFoundError(f"No prompts found for tag {tag_id}")
        return [self._deserialize(row) for row in rows]
