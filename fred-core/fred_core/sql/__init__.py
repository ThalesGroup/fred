"""
Lightweight SQL utilities shared across services.

Usage:
    from fred_core.sql import create_engine_from_config, BaseSqlStore
    from fred_core.sql import SeedMarkerMixin, PydanticJsonMixin
"""

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
