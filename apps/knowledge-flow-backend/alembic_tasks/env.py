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

"""Alembic environment for Knowledge Flow's DEDICATED TASK DATABASE (OPS-04, #2170).

Knowledge Flow shares its main Postgres database with control-plane. Both persist tasks
through the same `fred_core.tasks` tables, which carry no per-service discriminator, so
sharing one database makes each backend's `GET /tasks` return the other's rows and the
Activity page shows every task twice. This chain owns `task_run`/`task_event_log` in a
database of Knowledge Flow's own; the main chain (`alembic/`) keeps owning
tag/metadata/resource in the shared database.

Run it with: ``alembic -c alembic_tasks.ini upgrade head`` (or ``make db-upgrade-tasks``).
"""

from __future__ import annotations

from logging.config import fileConfig

from fred_core.common import PostgresStoreConfig
from fred_core.sql import make_alembic_env
from fred_core.tasks import task_metadata

from alembic import context
from knowledge_flow_backend.common.config_loader import load_configuration

# Alembic Config object — provides access to values in alembic_tasks.ini.
config = context.config

# Set up Python logging from alembic_tasks.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _task_postgres_config() -> PostgresStoreConfig:
    """Return the dedicated task database's connection config.

    Raises rather than silently falling back to `storage.postgres`: this chain owns the
    task tables, and pointing it at the shared database would have it manage — and on
    ``downgrade``, DROP — the copy that control-plane owns there. The runtime fallback in
    ``ApplicationContext.get_task_pg_async_engine`` is deliberately softer, because a
    process must still boot before the dedicated database is provisioned; a migration has
    no such excuse.

    Never called when DATABASE_URL is set — ``make_alembic_env`` checks that first, which
    is how CI targets a throwaway database without a config file.
    """
    task_postgres = load_configuration().storage.task_postgres
    if task_postgres is None:
        raise RuntimeError(
            "storage.task_postgres is not configured. This chain migrates Knowledge Flow's "
            "dedicated task database (OPS-04, issue #2170) and must not be run against the "
            "shared 'fred' database, where control-plane owns task_run/task_event_log. "
            "Configure storage.task_postgres, or set DATABASE_URL to target a database explicitly."
        )
    return task_postgres


run_migrations_offline, run_migrations_online = make_alembic_env(
    # Scoped to exactly the tables fred_core.tasks owns — see `task_metadata()` for why
    # passing the shared `Base.metadata` would make this chain claim other backends'
    # tables, and why Alembic's name filters cannot substitute for the scoping.
    target_metadata=task_metadata(),
    get_postgres_config=_task_postgres_config,
    # Distinct from the main chain's `alembic_version_knowledge_flow` so that a
    # mis-pointed URL cannot corrupt the other chain's recorded revision.
    version_table="alembic_version_knowledge_flow_tasks",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
