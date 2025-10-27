# agentic_backend/core/agents/store/duckdb_agent_store.py
# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple, TypeVar

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import (  # BaseModel is needed for TypeVar
    BaseModel,
    TypeAdapter,
    ValidationError,
)

# ⬇️ Two distinct Pydantic models (immutable metadata vs. mutable tuning)
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.base_agent_store import (
    SCOPE_GLOBAL,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)

# Union (de)serializers for Pydantic v2
AgentSettingsAdapter = TypeAdapter(AgentSettings)
AgentTuningAdapter = TypeAdapter(AgentTuning)

# Define a TypeVar to handle generic Pydantic models for type safety in helper methods
T = TypeVar("T", bound=BaseModel)


class DuckdbAgentStore(BaseAgentStore):
    """
    DuckDB persistent storage for agent data, using two separate tables:
    agents_settings (for immutable metadata) and agents_tuning (for mutable configuration).
    Retrievals (get, load_by_scope) merge the two into a single AgentSettings.

    ⚠ Scope semantics:
      - Global scope is represented with scope_id = NULL in SQL (not empty string).
      - Predicates use `IS NULL` when Python scope_id is None, otherwise `= ?`.
      - Inserts pass None to persist SQL NULL.

    This aligns all CRUD paths with BaseAgentStore expectations for global scope.
    """

    def __init__(self, db_path: Path):
        self.settings_table_name = "agents_settings"
        self.tuning_table_name = "agents_tuning"
        self.store = DuckDBTableStore(prefix="agent_", db_path=db_path)

        # Ensure both tables exist with the correct, final schema
        self._ensure_schema(self.settings_table_name)
        self._ensure_schema(self.tuning_table_name)
        logger.info(
            f"[STORE] DuckdbAgentStore initialized with two tables: {self.settings_table_name}, {self.tuning_table_name}"
        )

    # ----------------------------------------------------------------------
    # SCHEMA MANAGEMENT (CLEAN ENFORCEMENT)
    # ----------------------------------------------------------------------

    def _ensure_schema(self, table_name: str) -> None:
        """
        Enforces the exact required schema: (name, scope, scope_id, data_json).
        Drops and recreates the table if non-conformant or missing.

        Rationale: we need a stable schema with a composite PK.
        `scope_id` must allow NULL so global scope can be represented as SQL NULL.
        """
        table_full_name = self.store._prefixed(table_name)
        required_column_count = 4

        with self.store._connect() as conn:
            current_column_count = 0
            table_exists = False

            try:
                columns = conn.execute(
                    f"PRAGMA table_info('{table_full_name}')"
                ).fetchall()
                current_column_count = len(columns)
                table_exists = True
            except Exception as e:
                if "Catalog Error" not in str(e):
                    raise

            needs_recreation = not table_exists or (
                table_exists and current_column_count != required_column_count
            )

            if needs_recreation:
                if table_exists:
                    conn.execute(f'DROP TABLE IF EXISTS "{table_full_name}"')
                    logger.warning(
                        f"🗑️ Detected non-conformant schema in '{table_full_name}'. Dropped table."
                    )

                conn.execute(
                    f"""
                    CREATE TABLE "{table_full_name}" (
                        name TEXT NOT NULL,
                        scope TEXT NOT NULL DEFAULT '{SCOPE_GLOBAL}',
                        scope_id TEXT,          -- IMPORTANT: allow NULL to represent global scope
                        data_json TEXT,
                        PRIMARY KEY (name, scope, scope_id)
                    )
                    """
                )
                logger.info(
                    f"[STORE][DUCKDB] Created fresh table '{table_full_name}' with composite PRIMARY KEY."
                )
            else:
                logger.debug(
                    f"[STORE][DUCKDB] Schema for '{table_full_name}' is verified and up to date."
                )

    # ----------------------------------------------------------------------
    # INTERNAL HELPERS
    # ----------------------------------------------------------------------

    def _save_data(
        self,
        name: str,
        data: Any,
        adapter: TypeAdapter,
        table_name: str,
        scope: str,
        scope_id: Optional[str],
    ) -> None:
        """
        Serialize and save a Pydantic object to a specific table.

        Key point: pass `scope_id` through as-is (None -> SQL NULL).
        This ensures global scope rows are actually stored with NULL scope_id.
        """
        try:
            json_bytes = adapter.dump_json(data, exclude_none=True)
            json_str = json_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError(
                f"Failed to serialize {type(data).__name__} for '{name}': {e}"
            )

        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO "{self.store._prefixed(table_name)}" 
                (name, scope, scope_id, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (name, scope, scope_id, json_str),  # NOTE: scope_id may be None -> NULL
            )
        logger.debug(
            f"Saved {table_name} for '{name}' (Scope: {scope}, ScopeID: {scope_id})"
        )

    def _get_data(
        self,
        name: str,
        adapter: TypeAdapter[T],
        table_name: str,
        scope: str,
        scope_id: Optional[str],
    ) -> Optional[T]:
        """
        Retrieve and deserialize a single Pydantic object.
        Scope predicate uses IS NULL when scope_id is None, else equality.
        """
        if scope_id is None:
            where_clause = "WHERE name = ? AND scope = ? AND scope_id IS NULL"
            params = (name, scope)
        else:
            where_clause = "WHERE name = ? AND scope = ? AND scope_id = ?"
            params = (name, scope, scope_id)

        with self.store._connect() as conn:
            row = conn.execute(
                f'SELECT data_json FROM "{self.store._prefixed(table_name)}" {where_clause}',
                params,
            ).fetchone()

        if not row:
            return None

        try:
            return adapter.validate_json(row[0])
        except ValidationError as e:
            logger.error(
                f"❌ Failed to validate JSON for '{name}' (Scope: {scope}, ScopeID: {scope_id}): {e}"
            )
            return None

    def _load_data_by_scope(
        self,
        adapter: TypeAdapter[T],
        table_name: str,
        scope: str,
        scope_id: Optional[str],
    ) -> List[Tuple[str, T]]:
        """
        Load all Pydantic objects for a specific scope.
        Returns: list of (agent_name, deserialized_object).

        Global scope uses `scope_id IS NULL`.
        """
        if scope_id is None:
            where_clause = "WHERE scope = ? AND scope_id IS NULL"
            params = (scope,)
        else:
            where_clause = "WHERE scope = ? AND scope_id = ?"
            params = (scope, scope_id)

        data_list: List[Tuple[str, T]] = []
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT name, data_json FROM "{self.store._prefixed(table_name)}" {where_clause}',
                params,
            ).fetchall()

        for name, json_str in rows:
            try:
                data = adapter.validate_json(json_str)
                data_list.append((name, data))
            except ValidationError as e:
                logger.error(
                    f"❌ Skipping malformed row for agent '{name}' in {table_name} (Scope: {scope}, ScopeID: {scope_id}): {e}"
                )

        return data_list

    # ----------------------------------------------------------------------
    # BASE AGENT STORE IMPLEMENTATION (Merge on Retrieve)
    # ----------------------------------------------------------------------

    def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        """Save AgentSettings and AgentTuning to separate tables (global scope -> NULL scope_id)."""
        self._save_data(
            settings.name,
            settings,
            AgentSettingsAdapter,
            self.settings_table_name,
            scope,
            scope_id,
        )

        self._save_data(
            settings.name,
            tuning,
            AgentTuningAdapter,
            self.tuning_table_name,
            scope,
            scope_id,
        )

        logger.info(
            f"[AGENTS] ✅ Agent '{settings.name}' settings and tuning saved to DuckDB (Scope: {scope}, ScopeID: {scope_id})"
        )

    def save_all(
        self,
        settings_tuning_list: List[Tuple[AgentSettings, AgentTuning]],
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        """
        Batch save for both settings and tuning.

        Critical fix: we forward `scope_id` as-is so None persists as SQL NULL.
        This ensures load_by_scope(..., scope_id=None) can find these rows with IS NULL.
        """
        settings_to_insert = []
        tuning_to_insert = []

        for settings, tuning in settings_tuning_list:
            try:
                s_json_bytes = AgentSettingsAdapter.dump_json(
                    settings, exclude_none=True
                )
                settings_to_insert.append(
                    (settings.name, scope, scope_id, s_json_bytes.decode("utf-8"))
                )

                t_json_bytes = AgentTuningAdapter.dump_json(tuning, exclude_none=True)
                tuning_to_insert.append(
                    (settings.name, scope, scope_id, t_json_bytes.decode("utf-8"))
                )

            except Exception as e:
                logger.error(
                    f"[STORE][DUCKDB] Failed to serialize Agent data for batch save {settings.name}: {e}"
                )

        def _bulk_insert(
            data_list: List[Tuple[str, str, Optional[str], str]], table_name: str
        ):
            if not data_list:
                return

            with self.store._connect() as conn:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO "{self.store._prefixed(table_name)}" 
                    (name, scope, scope_id, data_json)
                    SELECT * FROM UNNEST(?, ?, ?, ?)
                    """,
                    (
                        [d[0] for d in data_list],
                        [d[1] for d in data_list],
                        [d[2] for d in data_list],  # may contain None -> SQL NULL
                        [d[3] for d in data_list],
                    ),
                )
            logger.debug(f"Batch saved {len(data_list)} items to {table_name}")

        _bulk_insert(settings_to_insert, self.settings_table_name)
        _bulk_insert(tuning_to_insert, self.tuning_table_name)

        logger.debug(
            f"[STORE][DUCKDB] Batch saved {len(settings_to_insert)} agent data sets to DuckDB (Scope: {scope}, ScopeID: {scope_id})"
        )

    def get(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> Optional[AgentSettings]:
        """
        Retrieve AgentSettings and its AgentTuning for (name, scope, scope_id).
        Global scope path uses IS NULL, matching save/save_all behavior.
        """
        settings_loaded: Optional[AgentSettings] = self._get_data(
            name, AgentSettingsAdapter, self.settings_table_name, scope, scope_id
        )
        if not settings_loaded:
            return None

        tuning_loaded: Optional[AgentTuning] = self._get_data(
            name, AgentTuningAdapter, self.tuning_table_name, scope, scope_id
        )

        if tuning_loaded:
            return settings_loaded.model_copy(update={"tuning": tuning_loaded})

        logger.warning(
            f"[STORE][DUCKDB] AgentTuning missing for '{name}' (Scope: {scope}, ScopeID: {scope_id}). Returning base settings."
        )
        return settings_loaded

    def load_by_scope(
        self,
        scope: str,
        scope_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        """
        Load and merge all AgentSettings and their Tunings for a given scope.
        Global scope path filters with `scope_id IS NULL`.
        """
        named_settings_list: List[Tuple[str, AgentSettings]] = self._load_data_by_scope(
            AgentSettingsAdapter, self.settings_table_name, scope, scope_id
        )

        named_tuning_list: List[Tuple[str, AgentTuning]] = self._load_data_by_scope(
            AgentTuningAdapter, self.tuning_table_name, scope, scope_id
        )

        tuning_map = {name: tuning for name, tuning in named_tuning_list}

        final_list: List[AgentSettings] = []
        for name, settings in named_settings_list:
            tuning = tuning_map.get(name)
            if tuning:
                final_list.append(settings.model_copy(update={"tuning": tuning}))
            else:
                logger.warning(
                    f"⚠️ Missing tuning data for agent '{name}' in scope {scope} (ScopeID: {scope_id}). Loading with tuning=None."
                )
                final_list.append(settings)

        logger.info(
            f"[STORE][DUCKDB] Loaded {len(final_list)} complete agent configurations from DuckDB (Scope: {scope}, ScopeID: {scope_id})"
        )
        return final_list

    def load_all_global_scope(self) -> List[AgentSettings]:
        """Convenience wrapper around load_by_scope(SCOPE_GLOBAL, None)."""
        return self.load_by_scope(scope=SCOPE_GLOBAL)

    def delete(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        """
        Delete both settings and tuning entries for the composite key.
        Uses `IS NULL` for global scope deletes.
        """
        if scope_id is None:
            where_clause = "WHERE name = ? AND scope = ? AND scope_id IS NULL"
            params = (name, scope)
        else:
            where_clause = "WHERE name = ? AND scope = ? AND scope_id = ?"
            params = (name, scope, scope_id)

        with self.store._connect() as conn:
            conn.execute(
                f'DELETE FROM "{self.store._prefixed(self.settings_table_name)}" {where_clause}',
                params,
            )
            conn.execute(
                f'DELETE FROM "{self.store._prefixed(self.tuning_table_name)}" {where_clause}',
                params,
            )

        logger.info(
            f"[STORE][DUCKDB] Agent data for '{name}' deleted from both DuckDB tables (Scope: {scope}, ScopeID: {scope_id})"
        )
