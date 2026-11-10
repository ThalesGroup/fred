# Copyright Thales 2026
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

"""Alembic env for the ppt_builder capability's own tree, versioned under
`cap_ppt_builder_alembic_version`; `python -m fred_runtime migrate` runs it."""

from __future__ import annotations

import functools

from alembic import context
from fred_capability_ppt_filler.builder.analysis_job import PptBuilderBase
from fred_capability_ppt_filler.builder.deck_plans import DeckPlanRow  # noqa: F401
from fred_core.common import load_postgres_config
from fred_core.sql import make_alembic_env
from fred_core.sql.alembic_env import _build_url
from sqlalchemy import Column, Computed, ForeignKey, Index, MetaData, Table, Uuid

# One configuration read per migration run, however often Alembic needs the URL.
_postgres_config = functools.cache(load_postgres_config)

_metadata = MetaData()
for table in PptBuilderBase.metadata.tables.values():
    table.to_metadata(_metadata)
if _build_url(_postgres_config).startswith("postgresql"):
    Table(
        "session_metadata",
        _metadata,
        Column("session_id", Uuid, primary_key=True),
        schema="control_plane",
    )
    _deck_plans = _metadata.tables["cap_ppt_builder_deck_plan"]
    _deck_plans.append_column(
        Column(
            "conversation_id",
            Uuid,
            Computed("session_id::uuid", persisted=True),
            ForeignKey(
                "control_plane.session_metadata.session_id",
                ondelete="CASCADE",
                name="cap_ppt_builder_deck_plan_conversation_fk",
            ),
            nullable=False,
        )
    )
    Index("cap_ppt_builder_deck_plan_conversation_idx", _deck_plans.c.conversation_id)

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=_metadata,
    get_postgres_config=_postgres_config,
    version_table="cap_ppt_builder_alembic_version",
    owned_tables=["cap_ppt_builder_analysis", "cap_ppt_builder_deck_plan"],
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
