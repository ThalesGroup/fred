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

from fred_core.sql import make_alembic_env

import knowledge_flow_backend.core.stores.metadata.metadata_models  # noqa: F401
import knowledge_flow_backend.core.stores.resources.resource_models  # noqa: F401
import knowledge_flow_backend.core.stores.tags.tag_models  # noqa: F401
import knowledge_flow_backend.features.scheduler.store.task_models  # noqa: F401
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

run_migrations_offline, run_migrations_online = make_alembic_env(
    # All knowledge-flow-backend tables are captured here.
    target_metadata=Base.metadata,
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_knowledge_flow",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
