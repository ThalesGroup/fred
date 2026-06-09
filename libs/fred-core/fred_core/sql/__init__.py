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
Lightweight SQL utilities shared across services.

Usage:
    from fred_core.sql import create_engine_from_config, BaseSqlStore
    from fred_core.sql import SeedMarkerMixin, PydanticJsonMixin
"""

from fred_core.sql.alembic_env import make_alembic_env
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.sql.base_sql import (
    AsyncBaseSqlStore,
    BaseSqlStore,
    advisory_lock_key,
    create_async_engine_from_config,
    create_engine_from_config,
    json_for_engine,
    run_ddl_with_advisory_lock,
)
from fred_core.sql.mixin import PydanticJsonMixin, SeedMarkerMixin

__all__ = [
    "make_alembic_env",
    "make_session_factory",
    "use_session",
    "BaseSqlStore",
    "AsyncBaseSqlStore",
    "create_engine_from_config",
    "create_async_engine_from_config",
    "PydanticJsonMixin",
    "SeedMarkerMixin",
    "json_for_engine",
    "run_ddl_with_advisory_lock",
    "advisory_lock_key",
]
