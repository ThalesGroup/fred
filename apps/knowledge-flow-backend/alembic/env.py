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

from logging.config import fileConfig

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.sql import make_alembic_env
from sqlalchemy import MetaData

import knowledge_flow_backend.core.stores.resources.resource_models  # noqa: F401
from alembic import context
from knowledge_flow_backend.common.config_loader import load_configuration

# Import Base and every ORM model so they all register with Base.metadata
# before autogenerate inspects it.  These imports must stay here (not in
# knowledge_flow_backend/models/__init__.py) to avoid circular imports at runtime.
from knowledge_flow_backend.models.base import Base

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build a MetaData scoped to the tables Knowledge Flow owns in the SHARED `fred` database.
#
# `DocumentMetadataRow`/`TagRow` share CoreBase with tables owned by other backends
# (session, teammetadata, users — control-plane) and, since OPS-04 / issue #2170, with
# task_run/task_event_log, which now live in Knowledge Flow's own dedicated database and
# are migrated by the separate `alembic_tasks` chain. Passing `CoreBase.metadata` directly
# would make this chain claim all of them: `alembic check` reports drift for tables it does
# not own, and `--autogenerate` emits spurious create/drop operations for them.
#
# Note the include_name/table-name filter in make_alembic_env cannot substitute for this.
# Alembic filters the *connection* side by name, but builds the metadata side from
# `sorted_tables` unfiltered, so an unwanted table in the MetaData is still requested.
# Same reasoning and same pattern as libs/fred-runtime/alembic/env.py.
_knowledge_flow_metadata = MetaData()
for _table in Base.metadata.tables.values():
    _table.to_metadata(_knowledge_flow_metadata)
DocumentMetadataRow.__table__.to_metadata(_knowledge_flow_metadata)  # type: ignore[attr-defined]
TagRow.__table__.to_metadata(_knowledge_flow_metadata)  # type: ignore[attr-defined]

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=_knowledge_flow_metadata,
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_knowledge_flow",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
