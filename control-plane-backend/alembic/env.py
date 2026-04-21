from __future__ import annotations

from logging.config import fileConfig

from fred_core.sql import make_alembic_env
from fred_core.users.user_models import UserRow  # noqa: F401

import control_plane_backend.models.purge_queue_models  # noqa: F401
import control_plane_backend.models.team_metadata_models  # noqa: F401
from alembic import context
from control_plane_backend.common.config_loader import load_configuration

# Import Base and every ORM model so they all register with Base.metadata
# before autogenerate inspects it.  These imports must stay here (not in
# control_plane_backend/models/__init__.py) to avoid circular imports at runtime.
from control_plane_backend.models.base import Base

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=Base.metadata,
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_control_plane",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
