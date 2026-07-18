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
from fred_core.documents import (
    AccessInfo,
    BaseDocumentMetadataStore,
    DocSummary,
    DocumentMetadata,
    DocumentMetadataDeserializationError,
    DocumentMetadataRow,
    FileInfo,
    FileType,
    Identity,
    PostgresDocumentMetadataStore,
    Processing,
    ProcessingGraph,
    ProcessingGraphEdge,
    ProcessingGraphNode,
    ProcessingStage,
    ProcessingStatus,
    ProcessingSummary,
    ReportExtensionV1,
    ReportFormat,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.filesystem.gcs_filesystem import GcsFilesystem
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.filesystem.minio_filesystem import MinioFilesystem
from fred_core.filesystem.structures import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_core.logs.audit_log import emit_audit_log
from fred_core.logs.base_log_store import BaseLogStore
from fred_core.logs.log_setup import AUDIT_LOGGER_NAME, StoreEmitHandler, log_setup
from fred_core.logs.log_store_factory import build_log_store
from fred_core.logs.log_structures import (
    InMemoryLogStorageConfig,
    LogCategory,
    LogEventDTO,
    LogStorageConfig,
)
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.logs.opensearch_log_store import OpenSearchLogStore
from fred_core.model.factory import get_embeddings, get_model, get_structured_chain
from fred_core.model.models import ModelProvider
from fred_core.security.authorization import (
    NO_AUTHZ_CHECK_USER,
    TODO_PASS_REAL_USER,
)
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
from fred_core.security.models import (
    Action,
    AuthorizationError,
    Resource,
)
from fred_core.security.oidc import (
    decode_jwt,
    get_current_user,
    get_current_user_without_gcu,
    get_keycloak_client_id,
    get_keycloak_url,
    initialize_user_security,
    oauth2_scheme,
    split_realm_url,
)
from fred_core.security.outbound import BearerAuth, ClientCredentialsProvider
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS,
    AgentPermission,
    CapabilityPermission,
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
    is_service_agent,
)
from fred_core.session import SessionSchema
from fred_core.session.stores import BaseSessionStore, PostgresSessionStore
from fred_core.teams.metadata_store import (
    TeamMetadata,
    TeamMetadataPatch,
    TeamMetadataRow,
    TeamMetadataStore,
)

from .common import get_config
from .users import (
    BaseUserStore,
    GcuVersionsType,
    PostgresUserStore,
    UserRow,
    get_user_store,
)

__all__ = [
    "BaseLogStore",
    "LogCategory",
    "LogEventDTO",
    "OpenSearchLogStore",
    "AUDIT_LOGGER_NAME",
    "RamLogStore",
    "StoreEmitHandler",
    "build_log_store",
    "emit_audit_log",
    "log_setup",
    "LogStorageConfig",
    "InMemoryLogStorageConfig",
    "get_current_user",
    "get_current_user_without_gcu",
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
    "GcsFilesystem",
    "FilesystemResourceInfoResult",
    "FilesystemResourceInfo",
    "is_service_agent",
    "SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS",
    "Action",
    "Resource",
    "AuthorizationError",
    "oauth2_scheme",
    "ClientCredentialsProvider",
    "BearerAuth",
    "M2MAuthConfig",
    "M2MTokenProvider",
    "M2MBearerAuth",
    "make_m2m_asgi_client",
    "split_realm_url",
    "get_model",
    "get_structured_chain",
    "get_embeddings",
    "ModelProvider",
    "BaseSessionStore",
    "PostgresSessionStore",
    "SessionSchema",
    "RebacReference",
    "Relation",
    "RelationType",
    "TagPermission",
    "DocumentPermission",
    "TeamPermission",
    "ORGANIZATION_ID",
    "AgentPermission",
    "OrganizationPermission",
    "CapabilityPermission",
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
    "BaseUserStore",
    "PostgresUserStore",
    "UserRow",
    "GcuVersionsType",
    "get_user_store",
    "get_config",
    "TeamMetadata",
    "TeamMetadataPatch",
    "TeamMetadataStore",
    "TeamMetadataRow",
    # documents
    "AccessInfo",
    "BaseDocumentMetadataStore",
    "DocSummary",
    "DocumentMetadata",
    "DocumentMetadataDeserializationError",
    "DocumentMetadataRow",
    "FileInfo",
    "FileType",
    "Identity",
    "PostgresDocumentMetadataStore",
    "Processing",
    "ProcessingGraph",
    "ProcessingGraphEdge",
    "ProcessingGraphNode",
    "ProcessingStage",
    "ProcessingStatus",
    "ProcessingSummary",
    "ReportExtensionV1",
    "ReportFormat",
    "SourceInfo",
    "SourceType",
    "Tagging",
]
