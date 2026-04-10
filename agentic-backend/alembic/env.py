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

import fred_core.session.stores.session_models  # noqa: F401

# fred-core ORM models (session table) — included so Alembic manages them here.
from fred_core.models.base import Base as FredCoreBase
from fred_core.sql import make_alembic_env

import agentic_backend.core.agents.store.agent_models  # noqa: F401
import agentic_backend.core.feedback.store.feedback_models  # noqa: F401
import agentic_backend.core.mcp.store.mcp_server_models  # noqa: F401
import agentic_backend.core.monitoring.history_models  # noqa: F401
import agentic_backend.core.session.stores.session_attachment_models  # noqa: F401
import agentic_backend.scheduler.store.task_models  # noqa: F401
from agentic_backend.common.config_loader import load_configuration

# Import Base and every ORM model so they all register with Base.metadata
# before autogenerate inspects it.  These imports must stay here (not in
# agentic_backend/models/__init__.py) to avoid circular imports at runtime.
from agentic_backend.models.base import Base
from alembic import context

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

run_migrations_offline, run_migrations_online = make_alembic_env(
    # All agentic-backend tables (+ fred-core session table) are captured here.
    target_metadata=[Base.metadata, FredCoreBase.metadata],
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_agentic",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
