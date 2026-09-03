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

import fred_core.documents.document_models  # noqa: F401 — registers metadata + tag tables with CoreBase (via fred_core.documents.__init__)
from fred_core.models.base import Base as CoreBase
from fred_core.sql import make_alembic_env

from alembic import context
from knowledge_flow_backend.common.config_loader import load_configuration

# Importing table_ownership registers every KFB ORM model with Base.metadata
# (resource, kf_task_*) before autogenerate inspects it, and carries the
# declared owned-table set.
from knowledge_flow_backend.models.base import Base
from knowledge_flow_backend.models.table_ownership import OWNED_TABLES

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

run_migrations_offline, run_migrations_online = make_alembic_env(
    # Both metadata objects so autogenerate resolves KFB tables (incl. its own
    # kf_task_* pair, #2170) and the shared fred-core tables it references.
    # CoreBase also carries tables OTHER trees migrate (users, session*,
    # teammetadata, session_history) — owned_tables is what keeps this tree's
    # autogenerate and `alembic check` off them (#2314).
    target_metadata=[Base.metadata, CoreBase.metadata],
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_knowledge_flow",
    owned_tables=OWNED_TABLES,
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
