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

"""Configuration models shared by every component.

Moved to `fred_pod.common.structures` so a pod can read its configuration without installing the
agents platform. Re-exported here so existing imports keep working."""

from fred_pod.common.structures import (
    DEFAULT_POD_SQLITE_PATH,
    BaseModelWithId,
    DuckdbStoreConfig,
    InMemoryStoreConfig,
    KpiLogSinkConfig,
    KpiObservabilityConfig,
    KpiOpenSearchSinkConfig,
    KpiPrometheusSinkConfig,
    LogStoreConfig,
    ModelConfiguration,
    OpenSearchIndexConfig,
    OpenSearchStoreConfig,
    OwnerFilter,
    PostgresStoreConfig,
    PostgresTableConfig,
    StoreConfig,
    TemporalSchedulerConfig,
    default_postgres_store_config,
)

__all__ = [
    "DEFAULT_POD_SQLITE_PATH",
    "BaseModelWithId",
    "DuckdbStoreConfig",
    "InMemoryStoreConfig",
    "KpiLogSinkConfig",
    "KpiObservabilityConfig",
    "KpiOpenSearchSinkConfig",
    "KpiPrometheusSinkConfig",
    "LogStoreConfig",
    "ModelConfiguration",
    "OpenSearchIndexConfig",
    "OpenSearchStoreConfig",
    "OwnerFilter",
    "PostgresStoreConfig",
    "PostgresTableConfig",
    "StoreConfig",
    "TemporalSchedulerConfig",
    "default_postgres_store_config",
]
