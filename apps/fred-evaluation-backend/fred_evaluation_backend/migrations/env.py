from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from fred_core.sql import make_alembic_env

from fred_evaluation_backend.campaigns.base import Base
import fred_evaluation_backend.campaigns.models  # noqa: F401

from fred_evaluation_backend.config.loader import load_configuration

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=[Base.metadata],
    get_postgres_config=lambda: load_configuration().database,
    version_table="alembic_version_evaluation",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()