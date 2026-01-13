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
from typing import List, Optional

from fred_core.sql import BaseSqlStore
from pydantic import TypeAdapter
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.base_agent_store import (
    SCOPE_GLOBAL,
    AgentNotFoundError,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)

AgentSettingsAdapter = TypeAdapter(AgentSettings)


class PostgresAgentStore(BaseAgentStore):
    """
    PostgreSQL-backed agent store using JSONB.
    """

    def __init__(self, engine: Engine, table_name: str, prefix: str = "agents_"):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._seed_marker_id = "__static_seeded__"

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("doc_id", String, primary_key=True),
            Column("name", String, index=True),
            Column("scope", String, index=True),
            Column("scope_id", String, index=True),
            Column("payload_json", JSONB),
            keep_existing=True,
        )

        metadata.create_all(self.store.engine)
        logger.info("[AGENTS][PG] Table ready: %s", self.table_name)

    @staticmethod
    def _doc_id(name: str, scope: str, scope_id: Optional[str]) -> str:
        return f"{name}:{scope}:{scope_id if scope_id is not None else 'NULL'}"

    def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        doc_id = self._doc_id(settings.name, scope, scope_id)
        if doc_id == self._seed_marker_id:
            raise ValueError("Invalid agent name: reserved for seed marker")

        payload = AgentSettingsAdapter.dump_python(
            settings, mode="json", exclude_none=True
        )
        if tuning is not None and "tuning" not in payload:
            try:
                payload["tuning"] = tuning.model_dump(exclude_none=True)
            except Exception:
                logger.warning(
                    "[STORE][PG][AGENTS] Could not embed tuning into AgentSettings for '%s'",
                    settings.name,
                )
                pass

        with self.store.begin() as conn:
            self.store.upsert(
                conn,
                self.table,
                values={
                    "doc_id": doc_id,
                    "name": settings.name,
                    "scope": scope,
                    "scope_id": scope_id,
                    "payload_json": payload,
                },
                pk_cols=["doc_id"],
            )

    def load_by_scope(
        self,
        scope: str,
        scope_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        with self.store.begin() as conn:
            if scope_id is None:
                rows = conn.execute(
                    select(self.table.c.payload_json, self.table.c.doc_id).where(
                        self.table.c.scope == scope, self.table.c.scope_id.is_(None)
                    )
                ).fetchall()
            else:
                rows = conn.execute(
                    select(self.table.c.payload_json, self.table.c.doc_id).where(
                        self.table.c.scope == scope, self.table.c.scope_id == scope_id
                    )
                ).fetchall()

        out: List[AgentSettings] = []
        for payload_json, doc_id in rows:
            if doc_id == self._seed_marker_id:
                continue
            try:
                out.append(AgentSettingsAdapter.validate_python(payload_json or {}))
            except Exception as e:
                logger.error("[STORE][PG][AGENTS] Failed to parse AgentSettings: %s", e)
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
        if doc_id == self._seed_marker_id:
            return None
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table.c.payload_json).where(self.table.c.doc_id == doc_id)
            ).fetchone()
        if not row:
            return None
        try:
            return AgentSettingsAdapter.validate_python(row[0] or {})
        except Exception as e:
            logger.error(
                "[STORE][PG][AGENTS] Failed to parse AgentSettings for '%s': %s",
                name,
                e,
            )
            return None

    def delete(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        doc_id = self._doc_id(name, scope, scope_id)
        if doc_id == self._seed_marker_id:
            return
        with self.store.begin() as conn:
            result = conn.execute(
                self.table.delete().where(self.table.c.doc_id == doc_id)
            )
        if result.rowcount == 0:
            raise AgentNotFoundError(f"Agent '{name}' not found")

    def static_seeded(self) -> bool:
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table.c.doc_id).where(
                    self.table.c.doc_id == self._seed_marker_id
                )
            ).fetchone()
        return bool(row)

    def mark_static_seeded(self) -> None:
        with self.store.begin() as conn:
            self.store.upsert(
                conn,
                self.table,
                values={
                    "doc_id": self._seed_marker_id,
                    "name": self._seed_marker_id,
                    "scope": SCOPE_GLOBAL,
                    "scope_id": None,
                    "payload_json": {},
                },
                pk_cols=["doc_id"],
            )
