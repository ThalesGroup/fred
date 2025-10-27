# agentic_backend/core/agents/store/duckdb_agent_store.py
# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import TypeAdapter

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.base_agent_store import (
    SCOPE_GLOBAL,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)

AgentSettingsAdapter = TypeAdapter(AgentSettings)


class DuckDBAgentStore(BaseAgentStore):
    """
    Minimal single-table DuckDB store for AgentSettings.

    Schema:
      agents(
        doc_id        TEXT PRIMARY KEY,        -- "<name>:<scope>:<scope_id or 'NULL'>"
        name          TEXT NOT NULL,
        scope         TEXT NOT NULL,           -- "GLOBAL" | "USER"
        scope_id      TEXT,                    -- NULL for GLOBAL
        payload_json  TEXT                     -- full AgentSettings as JSON (incl. tuning if present)
      )
    """

    TABLE = "agents"

    def __init__(self, db_path: Path):
        # Keep same helper + prefix style as your other stores
        self.store = DuckDBTableStore(prefix="agents_", db_path=db_path)
        self._ensure_schema()

    # ------------------------- schema -------------------------

    def _ensure_schema(self) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    doc_id        TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    scope         TEXT NOT NULL,
                    scope_id      TEXT,
                    payload_json  TEXT
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_scope ON {self.TABLE}(scope, scope_id)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_name ON {self.TABLE}(name)"
            )

    # ------------------------- helpers ------------------------

    @staticmethod
    def _doc_id(name: str, scope: str, scope_id: Optional[str]) -> str:
        return f"{name}:{scope}:{scope_id if scope_id is not None else 'NULL'}"

    # -------------------------- CRUD --------------------------

    def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        doc_id = self._doc_id(settings.name, scope, scope_id)

        # Serialize AgentSettings to dict → ensure tuning is included (if provided separately)
        payload = AgentSettingsAdapter.dump_python(
            settings, mode="json", exclude_none=True
        )
        if tuning is not None and "tuning" not in payload:
            try:
                payload["tuning"] = tuning.model_dump(exclude_none=True)
            except Exception:
                # If already embedded / incompatible, ignore silently
                pass

        payload_json = json.dumps(payload)

        with self.store._connect() as conn:
            try:
                conn.execute("BEGIN")
                conn.execute(
                    f"DELETE FROM {self.TABLE} WHERE doc_id = ?",
                    (doc_id,),
                )
                conn.execute(
                    f"""
                    INSERT INTO {self.TABLE} (doc_id, name, scope, scope_id, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doc_id, settings.name, scope, scope_id, payload_json),
                )
                conn.execute("COMMIT")
                logger.info("[AGENTS] Saved agent '%s' (ID: %s)", settings.name, doc_id)
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(
                    "[AGENTS] Failed to save '%s' (ID: %s): %s",
                    settings.name,
                    doc_id,
                    e,
                )
                raise

    def load_by_scope(
        self,
        scope: str,
        scope_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        with self.store._connect() as conn:
            if scope_id is None:
                rows = conn.execute(
                    f"SELECT payload_json FROM {self.TABLE} WHERE scope = ? AND scope_id IS NULL",
                    (scope,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT payload_json FROM {self.TABLE} WHERE scope = ? AND scope_id = ?",
                    (scope, scope_id),
                ).fetchall()

        out: List[AgentSettings] = []
        for (payload_json,) in rows:
            try:
                payload = json.loads(payload_json) if payload_json else {}
                out.append(AgentSettingsAdapter.validate_python(payload))
            except Exception as e:
                logger.error("[AGENTS] Failed to parse AgentSettings: %s", e)
        return out

    def load_all_global_scope(self) -> List[AgentSettings]:
        return self.load_by_scope(scope=SCOPE_GLOBAL, scope_id=None)

    def get(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> Optional[AgentSettings]:
        doc_id = self._doc_id(name, scope, scope_id)
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT payload_json FROM {self.TABLE} WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0]) if row[0] else {}
            return AgentSettingsAdapter.validate_python(payload)
        except Exception as e:
            logger.error("[AGENTS] Failed to parse AgentSettings for '%s': %s", name, e)
            return None

    def delete(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        doc_id = self._doc_id(name, scope, scope_id)
        with self.store._connect() as conn:
            conn.execute(
                f"DELETE FROM {self.TABLE} WHERE doc_id = ?",
                (doc_id,),
            )
        logger.info("[AGENTS] Deleted agent '%s' (ID: %s)", name, doc_id)
