# Copyright Thales 2025
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

from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.common.lru_cache import ThreadSafeLRUCache
from fred_core.common.structures import (
    BaseModelWithId,
    DuckdbStoreConfig,
    LogStoreConfig,
    ModelConfiguration,
    OpenSearchIndexConfig,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    PostgresTableConfig,
    SQLStorageConfig,
    StoreConfig,
    TemporalSchedulerConfig,
)
from fred_core.common.utils import raise_internal_error
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.filesystem.minio_filesystem import MinioFilesystem
from fred_core.filesystem.structures import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_core.logs.base_log_store import BaseLogStore
from fred_core.logs.log_setup import StoreEmitHandler, log_setup
from fred_core.logs.log_structures import (
    InMemoryLogStorageConfig,
    LogEventDTO,
    LogFilter,
    LogQuery,
    LogQueryResult,
    LogStorageConfig,
    TailFileResponse,
)
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.logs.opensearch_log_store import OpenSearchLogStore
from fred_core.model.factory import get_embeddings, get_model, get_structured_chain
from fred_core.model.models import ModelProvider
from fred_core.security.authorization import (
    NO_AUTHZ_CHECK_USER,
    TODO_PASS_REAL_USER,
    Action,
    AuthorizationError,
    Resource,
    authorize_or_raise,
    is_authorized,
)
from fred_core.security.authorization_decorator import authorize
from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
    make_m2m_asgi_client,
)
from fred_core.security.keycloak.keycloack_admin_client import (
    KeycloackDisabled,
    create_keycloak_admin,
)
from fred_core.security.oidc import (
    decode_jwt,
    get_current_user,
    get_keycloak_client_id,
    get_keycloak_url,
    initialize_user_security,
    oauth2_scheme,
    split_realm_url,
)
from fred_core.security.outbound import BearerAuth, ClientCredentialsProvider
from fred_core.security.rbac import RBACProvider
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    AgentPermission,
    DocumentPermission,
    OrganizationPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    TagPermission,
    TeamPermission,
)
from fred_core.security.rebac.rebac_factory import rebac_factory
from fred_core.security.structure import (
    KeycloakUser,
    M2MSecurity,
    OpenFgaRebacConfig,
    RebacConfiguration,
    SecurityConfiguration,
    UserSecurity,
)
from fred_core.store.opensearch_mapping_validator import validate_index_mapping
from fred_core.store.sql_store import SQLTableStore
from fred_core.store.structures import StoreInfo
from fred_core.store.vector_search import VectorSearchHit

__all__ = [
    "BaseLogStore",
    "LogEventDTO",
    "LogFilter",
    "LogQuery",
    "LogQueryResult",
    "OpenSearchLogStore",
    "RamLogStore",
    "StoreEmitHandler",
    "TailFileResponse",
    "log_setup",
    "LogStorageConfig",
    "InMemoryLogStorageConfig",
    "raise_internal_error",
    "get_current_user",
    "decode_jwt",
    "initialize_user_security",
    "KeycloakUser",
    "SecurityConfiguration",
    "M2MSecurity",
    "RebacConfiguration",
    "UserSecurity",
    "TODO_PASS_REAL_USER",
    "NO_AUTHZ_CHECK_USER",
    "BaseFilesystem",
    "LocalFilesystem",
    "MinioFilesystem",
    "FilesystemResourceInfoResult",
    "FilesystemResourceInfo",
    "RBACProvider",
    "Action",
    "Resource",
    "AuthorizationError",
    "is_authorized",
    "authorize_or_raise",
    "authorize",
    "oauth2_scheme",
    "register_exception_handlers",
    "BaseModelWithId",
    "OpenSearchStoreConfig",
    "OpenSearchIndexConfig",
    "DuckdbStoreConfig",
    "PostgresStoreConfig",
    "PostgresTableConfig",
    "SQLStorageConfig",
    "StoreConfig",
    "ThreadSafeLRUCache",
    "VectorSearchHit",
    "ClientCredentialsProvider",
    "BearerAuth",
    "LogStoreConfig",
    "M2MAuthConfig",
    "M2MTokenProvider",
    "M2MBearerAuth",
    "make_m2m_asgi_client",
    "split_realm_url",
    "validate_index_mapping",
    "get_model",
    "get_structured_chain",
    "get_embeddings",
    "ModelConfiguration",
    "TemporalSchedulerConfig",
    "SQLStorageConfig",
    "SQLTableStore",
    "StoreInfo",
    "ModelProvider",
    "RebacReference",
    "Relation",
    "RelationType",
    "TagPermission",
    "DocumentPermission",
    "TeamPermission",
    "ORGANIZATION_ID",
    "AgentPermission",
    "OrganizationPermission",
    "RebacPermission",
    "RebacDisabledResult",
    "RebacEngine",
    "OpenFgaRebacEngine",
    "OpenFgaRebacConfig",
    "rebac_factory",
    "get_keycloak_url",
    "get_keycloak_client_id",
    "KeycloackDisabled",
    "create_keycloak_admin",
]
