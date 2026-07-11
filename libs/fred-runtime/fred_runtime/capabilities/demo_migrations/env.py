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

"""
Alembic env for the demo capability's OWN migration tree (#1979, RFC §7.1).

This tree is fully self-contained: its metadata is only the demo capability's
tables, and its history is versioned under `cap_demo_echo_alembic_version` —
never rebased against fred-runtime's tree or another capability's. `python -m
fred_runtime migrate` runs it after fred-runtime's own tree.
"""

from __future__ import annotations

from alembic import context
from fred_core.sql import make_alembic_env
from fred_runtime.app.config_loader import load_agent_pod_config
from fred_runtime.capabilities.demo import DemoBase

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=DemoBase.metadata,
    get_postgres_config=lambda: load_agent_pod_config().storage.postgres,
    version_table="cap_demo_echo_alembic_version",
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
