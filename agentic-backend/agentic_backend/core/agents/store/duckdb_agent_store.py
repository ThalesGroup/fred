# agentic_backend/core/agents/store/duckdb_agent_store.py
# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import TypeAdapter, ValidationError

# ⬇️ New source of truth: AgentSettings = Annotated[Union[Agent, Leader], ...]
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)

# Union (de)serializer for Pydantic v2
AgentSettingsAdapter = TypeAdapter(AgentSettings)


class DuckdbAgentStore(BaseAgentStore):
    """
    Fred rationale:
    - DuckDB is our **dev/test** backend; same contract as OpenSearch so switching is trivial.
    - We persist the whole Pydantic union payload as JSON; schema stays stable across migrations.
    """

    def __init__(self, db_path: Path):
        self.table_name = "agents"
        self.store = DuckDBTableStore(prefix="agent_", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # Minimal schema: natural key + raw JSON payload
        with self.store._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self.store._prefixed(self.table_name)}" (
                    name TEXT PRIMARY KEY,
                    settings_json TEXT
                )
                """
            )

    def save(self, settings: AgentSettings) -> None:
        """
        Why TypeAdapter.dump_json:
        - `AgentSettings` is a discriminated union, not a BaseModel type.
        - Dump via adapter guarantees the discriminator and nested models are serialized consistently.
        """
        try:
            json_bytes = AgentSettingsAdapter.dump_json(settings, exclude_none=True)
            json_str = json_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError(
                f"Failed to serialize AgentSettings for {getattr(settings, 'name', '?')}: {e}"
            )

        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO "{self.store._prefixed(self.table_name)}" (name, settings_json)
                VALUES (?, ?)
                """,
                (settings.name, json_str),
            )
        logger.info(f"[AGENTS] ✅ AgentSettings for '{settings.name}' saved to DuckDB")

    def get(self, name: str) -> Optional[AgentSettings]:
        """
        Union-safe load:
        - Do NOT call `AgentSettings(**data)`; `Annotated[Union[...]]` is not callable.
        - Use `TypeAdapter(AgentSettings).validate_json(...)`.
        """
        with self.store._connect() as conn:
            row = conn.execute(
                f'SELECT settings_json FROM "{self.store._prefixed(self.table_name)}" WHERE name = ?',
                (name,),
            ).fetchone()

        if not row:
            return None

        try:
            return AgentSettingsAdapter.validate_json(row[0])
        except ValidationError as e:
            logger.error(f"[AGENTS] ❌ Failed to parse AgentSettings for '{name}': {e}")
            return None

    def load_all(self) -> List[AgentSettings]:
        """
        Keep it simple (dev-scale). If this grows, add pagination.
        """
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT settings_json FROM "{self.store._prefixed(self.table_name)}"'
            ).fetchall()

        settings_list: List[AgentSettings] = []
        for (json_str,) in rows:
            try:
                settings = AgentSettingsAdapter.validate_json(json_str)
                settings_list.append(settings)
            except ValidationError as e:
                logger.error(f"[AGENTS] ❌ Skipping malformed AgentSettings row: {e}")

        logger.info(
            f"[AGENTS] ✅ Loaded {len(settings_list)} agent settings from DuckDB"
        )
        return settings_list

    def delete(self, name: str) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f'DELETE FROM "{self.store._prefixed(self.table_name)}" WHERE name = ?',
                (name,),
            )
        logger.info(f"[AGENTS] 🗑️ AgentSettings for '{name}' deleted from DuckDB")
