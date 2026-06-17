from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

from fred_core import (
    SecurityConfiguration,
)
from fred_core.common import (
    KpiObservabilityConfig,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    TemporalSchedulerConfig,
)
from fred_core.scheduler import SchedulerBackend
from fred_sdk.contracts.models import TuningValue
from pydantic import BaseModel, Field, model_validator


class AppConfig(BaseModel):
    name: str = "Control Plane Backend"
    base_url: str = "/control-plane/v1"
    address: str = "127.0.0.1"
    port: int = 8222
    log_level: str = "info"
    gcu_version: str | None = None
    default_team_max_resources_storage_size: int | None = Field(
        default=None,
        description="Default maximum resources storage size in bytes for a team",
    )
    personal_max_resources_storage_size: int | None = Field(
        default=None,
        description="Maximum resources storage size in bytes for a personal space",
    )


class ObservabilityConfig(BaseModel):
    kpi: KpiObservabilityConfig = Field(default_factory=KpiObservabilityConfig)


class FrontendFeatureFlags(BaseModel):
    """Typed feature flags exposed to the frontend bootstrap."""

    enableK8Features: bool = False
    enableElecWarfare: bool = False


class FrontendUiSettings(BaseModel):
    """Small typed UI settings surface owned by control-plane."""

    siteDisplayName: str = "Fred"
    agentsNicknameSingular: str = "agent"
    agentsNicknamePlural: str = "agents"


class FrontendBootstrapConfig(BaseModel):
    """Static frontend bootstrap configuration served by control-plane."""

    feature_flags: FrontendFeatureFlags = Field(default_factory=FrontendFeatureFlags)
    ui_settings: FrontendUiSettings = Field(default_factory=FrontendUiSettings)


class RuntimeCatalogSourceConfig(BaseModel):
    """Configured runtime endpoint used for read-only template aggregation."""

    runtime_id: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    enabled: bool = True
    ingress_prefix: str | None = Field(
        default=None,
        description=(
            "Ingress-relative URL prefix for browser-facing runtime access, "
            "e.g. /runtime/agents-v2. Required for execution preparation. "
            "MUST NOT be a cluster-internal hostname or pod IP."
        ),
    )


class ManagedAgentUiHints(BaseModel):
    """Small UI metadata kept compatible with runtime tuning fields."""

    multiline: bool = False
    max_lines: int = 6
    placeholder: str | None = None
    markdown: bool = False
    textarea: bool = False
    group: str | None = None
    hide: bool = False


class ManagedAgentFieldSpec(BaseModel):
    """Locally owned tunable-field shape sent back to fred-runtime."""

    key: str
    type: str
    title: str
    description: str | None = None
    description_by_lang: dict[str, str] | None = None
    required: bool = False
    default: Any | None = None
    default_by_lang: dict[str, str] | None = None
    enum: list[str] | None = None
    min: float | None = None
    max: float | None = None
    pattern: str | None = None
    item_type: str | None = None
    ui: ManagedAgentUiHints = Field(default_factory=ManagedAgentUiHints)


class ManagedMcpServerRef(BaseModel):
    """Logical MCP reference kept in the managed-agent tuning payload."""

    id: str
    display_name: str = ""
    require_tools: list[str] = Field(default_factory=list)
    config_fields: list[ManagedAgentFieldSpec] = Field(default_factory=list)
    locked: bool = Field(
        default=False,
        description=(
            "When True the server is part of the template's canonical tool set. "
            "The frontend renders its toggle as read-only; the operator can "
            "configure its config_fields but cannot remove the server."
        ),
    )


class ManagedAgentTuning(BaseModel):
    """Minimal runtime-compatible tuning payload owned by control-plane."""

    role: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    fields: list[ManagedAgentFieldSpec] = Field(default_factory=list)
    mcp_servers: list[ManagedMcpServerRef] = Field(default_factory=list)
    selected_mcp_server_ids: list[str] | None = Field(
        default=None,
        description=(
            "Admin-chosen MCP server activation policy. "
            "None means inherit the template default selection (all declared "
            "servers active); [] means activate no MCP servers; a non-empty "
            "list means activate exactly that subset."
        ),
    )
    mcp_config_values: dict[str, dict[str, TuningValue]] = Field(
        default_factory=dict,
        description=(
            "Per-server MCP configuration values keyed first by server id and "
            "then by ManagedAgentFieldSpec.key. Only keys declared by the "
            "matching server's config_fields are stored."
        ),
    )
    values: dict[str, TuningValue] = Field(
        default_factory=dict,
        description=(
            "User-set agent tuning values keyed by ManagedAgentFieldSpec.key. "
            "Only keys present in `fields` are stored. Frozen snapshot — not "
            "re-merged when the template evolves."
        ),
    )


class PlatformConfig(BaseModel):
    """
    Control-plane deployment configuration for product/runtime coordination.

    Contains ONLY infrastructure references (which runtime pods exist).
    Managed agent instance enrollment (which team has which agents) is
    DB-backed and never stored in this deployment config.
    """

    frontend: FrontendBootstrapConfig = Field(default_factory=FrontendBootstrapConfig)
    knowledge_flow_base_url: str = Field(
        default="http://127.0.0.1:8111/knowledge-flow/v1",
        description=(
            "Server-side base URL used by control-plane when it must orchestrate "
            "Knowledge Flow attachment cleanup on behalf of the authenticated user."
        ),
    )
    runtime_catalog_sources: list[RuntimeCatalogSourceConfig] = Field(
        default_factory=list
    )


class SchedulerConfig(BaseModel):
    enabled: bool = False
    backend: SchedulerBackend = SchedulerBackend.TEMPORAL
    temporal: TemporalSchedulerConfig = Field(default_factory=TemporalSchedulerConfig)


class PolicyConfig(BaseModel):
    purge_catalog_path: str = "./conversation_policy_catalog.yaml"


def _default_security() -> SecurityConfiguration:
    return SecurityConfiguration.model_validate(
        {
            "m2m": {
                "enabled": False,
                "realm_url": "http://localhost:8080/realms/app",
                "client_id": "control-plane",
                "secret_env_var": "KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET",  # nosec B105 # pragma: allowlist secret
            },
            "user": {
                "enabled": False,
                "realm_url": "http://localhost:8080/realms/app",
                "client_id": "app",
            },
            "authorized_origins": [],
            "rebac": None,
        }
    )


def _default_postgres_store() -> PostgresStoreConfig:
    return PostgresStoreConfig(
        sqlite_path="~/.fred/control-plane/control_plane.sqlite3"
    )


class MinioContentStorageConfig(BaseModel):
    type: Literal["minio"]
    endpoint: str = Field(default="http://localhost:9000", description="MinIO API URL")
    access_key: str = Field(..., description="MinIO access key")
    secret_key: str | None = Field(
        default_factory=lambda: os.getenv("MINIO_SECRET_KEY"),
        description="MinIO secret key (from MINIO_SECRET_KEY env by default)",
    )
    bucket_name: str = Field(
        default="control-plane-content",
        description="Content store bucket name (suffix '-objects' is used for banner objects)",
    )
    secure: bool = Field(default=False, description="Use TLS (https)")
    public_endpoint: str | None = Field(
        default=None,
        description="Optional public endpoint used to generate browser-facing presigned URLs",
    )
    public_secure: bool | None = Field(
        default=None,
        description="Optional TLS override for public endpoint (auto-inferred when omitted)",
    )

    @model_validator(mode="before")
    @classmethod
    def load_env_if_missing(cls, values: dict[str, object]) -> dict[str, object]:
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))
        if not values.get("secret_key"):
            raise ValueError("Missing MINIO_SECRET_KEY environment variable")
        return values


class LocalContentStorageConfig(BaseModel):
    type: Literal["local"] = "local"
    root_path: str = Field(
        default=str(Path("~/.fred/control-plane/content-storage")),
        description="Local storage directory",
    )


ContentStorageConfig = Annotated[
    Union[LocalContentStorageConfig, MinioContentStorageConfig],
    Field(discriminator="type"),
]


def _default_content_storage() -> LocalContentStorageConfig:
    return LocalContentStorageConfig()


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig = Field(default_factory=_default_postgres_store)
    content_storage: ContentStorageConfig = Field(
        default_factory=_default_content_storage
    )
    opensearch: Optional[OpenSearchStoreConfig] = None


class Configuration(BaseModel):
    app: AppConfig
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    scheduler: SchedulerConfig
    security: SecurityConfiguration = Field(default_factory=_default_security)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    policies: PolicyConfig = Field(default_factory=PolicyConfig)


class AppState(BaseModel):
    service: str = "control-plane"
    loaded_config_file: Optional[str] = None
    loaded_env_file: Optional[str] = None
