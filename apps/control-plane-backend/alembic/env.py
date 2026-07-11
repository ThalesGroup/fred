from __future__ import annotations

from logging.config import fileConfig

import control_plane_backend.models.agent_instance_models  # noqa: F401
import control_plane_backend.models.capability_settings_models  # noqa: F401
import control_plane_backend.models.prompt_models  # noqa: F401
import control_plane_backend.models.purge_queue_models  # noqa: F401
import control_plane_backend.models.session_attachment_models  # noqa: F401
import control_plane_backend.models.session_metadata_models  # noqa: F401
import fred_core.documents.document_models  # noqa: F401 — registers metadata table with CoreBase
import fred_core.tasks.orm_models  # noqa: F401 — registers task_run / task_event_log with CoreBase
import fred_core.teams.team_metatada_models  # noqa: F401
from alembic import context
from control_plane_backend.config.loader import load_configuration

# Import Base and every ORM model so they all register with Base.metadata
# before autogenerate inspects it.  These imports must stay here (not in
# control_plane_backend/models/__init__.py) to avoid circular imports at runtime.
from control_plane_backend.models.base import Base
from fred_core.models.base import Base as CoreBase
from fred_core.sql import make_alembic_env
from fred_core.users.user_models import UserRow  # noqa: F401

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

run_migrations_offline, run_migrations_online = make_alembic_env(
    # Both metadata objects so autogenerate sees CPB tables and shared task tables.
    target_metadata=[Base.metadata, CoreBase.metadata],
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_control_plane",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
