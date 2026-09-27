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

"""Configuration, naming, and the models every component's configuration uses."""

from fred_pod.common.config_files import ConfigFiles
from fred_pod.common.config_loader import (
    TConfig,
    get_config,
    load_configuration_with_config_files,
    load_postgres_config,
    parse_yaml_mapping_file,
)
from fred_pod.common.naming import (
    CONTRIBUTED_NAME_PATTERN,
    KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX,
    MAX_NAME_CHARS,
    PREFIX_PATTERN,
    InvalidContributedName,
    knowledge_base_catalog_id,
    knowledge_base_name_from_catalog_id,
    prefix_covers,
    require_contributed_name,
)
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
    "CONTRIBUTED_NAME_PATTERN",
    "DEFAULT_POD_SQLITE_PATH",
    "KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX",
    "MAX_NAME_CHARS",
    "PREFIX_PATTERN",
    "BaseModelWithId",
    "ConfigFiles",
    "DuckdbStoreConfig",
    "InMemoryStoreConfig",
    "InvalidContributedName",
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
    "TConfig",
    "TemporalSchedulerConfig",
    "default_postgres_store_config",
    "get_config",
    "knowledge_base_catalog_id",
    "knowledge_base_name_from_catalog_id",
    "load_configuration_with_config_files",
    "load_postgres_config",
    "parse_yaml_mapping_file",
    "prefix_covers",
    "require_contributed_name",
]
