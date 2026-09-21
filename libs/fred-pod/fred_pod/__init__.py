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
What a Fred component needs to *be* a pod: configuration, identity, naming.

A Knowledge Base pod, a capability pod, an MCP server pod and an agent pod all
read a `configuration.yaml`, get a machine-to-machine token and name things
under a prefix they own. That floor is this distribution, and it depends on
four third-party packages — pydantic, PyYAML, python-dotenv, httpx.

"What do I need to run a Fred component?" → `fred-pod`.
"What do I need to build an agent?" → `fred-core` / `fred-sdk`.

Unlike `fred-core`, importing this package is cheap and stays cheap: a
separate distribution cannot import what it does not depend on, so the
boundary is enforced by the build rather than by discipline.
"""

from fred_pod.common.config_files import ConfigFiles
from fred_pod.common.config_loader import (
    TConfig,
    get_config,
    load_configuration_with_config_files,
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
)
from fred_pod.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
    make_m2m_asgi_client,
)
from fred_pod.security.structure import (
    LOCAL_DEV_CLIENT_ID,
    SERVICE_AGENT_ROLE,
    KeycloakUser,
    M2MSecurity,
    OpenFgaRebacConfig,
    RebacBaseConfig,
    RebacConfiguration,
    SecurityConfiguration,
    UserSecurity,
    is_service_agent,
)

__all__ = [
    # Configuration
    "ConfigFiles",
    "TConfig",
    "get_config",
    "load_configuration_with_config_files",
    "parse_yaml_mapping_file",
    # Naming
    "CONTRIBUTED_NAME_PATTERN",
    "KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX",
    "MAX_NAME_CHARS",
    "PREFIX_PATTERN",
    "InvalidContributedName",
    "knowledge_base_catalog_id",
    "knowledge_base_name_from_catalog_id",
    "prefix_covers",
    "require_contributed_name",
    # Configuration models
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
    # Identity
    "LOCAL_DEV_CLIENT_ID",
    "SERVICE_AGENT_ROLE",
    "KeycloakUser",
    "M2MAuthConfig",
    "M2MBearerAuth",
    "M2MSecurity",
    "M2MTokenProvider",
    "OpenFgaRebacConfig",
    "RebacBaseConfig",
    "RebacConfiguration",
    "SecurityConfiguration",
    "UserSecurity",
    "is_service_agent",
    "make_m2m_asgi_client",
]
