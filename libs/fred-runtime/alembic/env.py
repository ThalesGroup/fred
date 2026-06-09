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

from __future__ import annotations

from logging.config import fileConfig

from fred_core.history.history_models import SessionHistoryRow  # noqa: F401
from fred_core.sql import make_alembic_env
from sqlalchemy import MetaData

from alembic import context
from fred_runtime.app.config_loader import load_agent_pod_config

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build a MetaData scoped to only the tables fred-runtime owns.
# SessionHistoryRow shares Base with other backends (users, session, teammetadata),
# so we must not pass Base.metadata directly — that would make alembic check
# report drift for tables managed by control-plane-backend.
_runtime_metadata = MetaData()
SessionHistoryRow.__table__.to_metadata(_runtime_metadata)

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=_runtime_metadata,
    get_postgres_config=lambda: load_agent_pod_config().storage.postgres,
    version_table="alembic_version_runtime",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
