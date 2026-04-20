from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Annotated, Literal, Optional, Union

from fred_core import (
    SecurityConfiguration,
)
from fred_core.common import (
    PostgresStoreConfig,
    TemporalSchedulerConfig,
)
from fred_core.scheduler import SchedulerBackend
from pydantic import BaseModel, Field, model_validator


class AppConfig(BaseModel):
    name: str = "Control Plane Backend"
    base_url: str = "/control-plane/v1"
    address: str = "127.0.0.1"
    port: int = 8222
    log_level: str = "info"


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
    required: bool = False
    default: Any | None = None
    enum: list[str] | None = None
    min: float | None = None
    max: float | None = None
    pattern: str | None = None
    item_type: str | None = None
    ui: ManagedAgentUiHints = Field(default_factory=ManagedAgentUiHints)


class ManagedMcpServerRef(BaseModel):
    """Logical MCP reference kept in the managed-agent tuning payload."""

    id: str
    require_tools: list[str] = Field(default_factory=list)


class ManagedAgentTuning(BaseModel):
    """Minimal runtime-compatible tuning payload owned by control-plane."""

    role: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    fields: list[ManagedAgentFieldSpec] = Field(default_factory=list)
    mcp_servers: list[ManagedMcpServerRef] = Field(default_factory=list)


class PlatformConfig(BaseModel):
    """
    Control-plane deployment configuration for product/runtime coordination.

    Contains ONLY infrastructure references (which runtime pods exist).
    Managed agent instance enrollment (which team has which agents) is
    DB-backed and never stored in this deployment config.
    """

    frontend: FrontendBootstrapConfig = Field(default_factory=FrontendBootstrapConfig)
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


class Configuration(BaseModel):
    app: AppConfig
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    scheduler: SchedulerConfig
    security: SecurityConfiguration = Field(default_factory=_default_security)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    policies: PolicyConfig = Field(default_factory=PolicyConfig)


class AppState(BaseModel):
    service: str = "control-plane"
    loaded_config_file: Optional[str] = None
    loaded_env_file: Optional[str] = None
