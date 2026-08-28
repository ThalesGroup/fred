from __future__ import annotations

from logging.config import fileConfig

import fred_core.documents.document_models  # noqa: F401 — registers metadata table with CoreBase
import fred_core.teams.team_metatada_models  # noqa: F401
from alembic import context
from control_plane_backend.config.loader import load_configuration

# Importing table_ownership registers every CP ORM model with Base.metadata
# before autogenerate inspects it, and carries the declared owned-table set.
from control_plane_backend.models.base import Base
from control_plane_backend.models.table_ownership import OWNED_TABLES
from fred_core.models.base import Base as CoreBase
from fred_core.sql import make_alembic_env
from fred_core.users.user_models import UserRow  # noqa: F401

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

run_migrations_offline, run_migrations_online = make_alembic_env(
    # Both metadata objects so autogenerate resolves CPB tables (incl. its own
    # cp_task_* pair, #2170) and the shared fred-core tables it references.
    # CoreBase also carries tables OTHER trees migrate (tag, metadata,
    # document_labels, session_history) — owned_tables is what keeps this
    # tree's autogenerate and `alembic check` off them (#2314).
    target_metadata=[Base.metadata, CoreBase.metadata],
    get_postgres_config=lambda: load_configuration().storage.postgres,
    version_table="alembic_version_control_plane",
    owned_tables=OWNED_TABLES,
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
