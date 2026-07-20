from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

from fred_core import (
    LogStorageConfig,
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
    bootstrap_token_env_var: str | None = Field(
        default=None,
        description=(
            "Name of the environment variable holding the one-time root "
            "platform-admin bootstrap secret (AUTHZ-07) — same pattern as "
            "SecurityConfiguration.m2m.secret_env_var. The value comes from a "
            "Kubernetes Secret populated by the deployment's own secrets "
            "pipeline (git-ignored file at C1, SOPS/sealed-secrets or a cloud "
            "secret manager at C2, an external Vault at C3 — RFC-0001 §6's "
            "existing 'secrets source' knob, not a new one). Fred never "
            "generates or logs this value. Checked before bootstrap_token_file."
        ),
    )
    bootstrap_token_file: str | None = Field(
        default=None,
        description=(
            "Path to the one-time root platform-admin bootstrap secret, for "
            "local dev only (AUTHZ-07). Must be provided explicitly (e.g. "
            "`make bootstrap-token`) — Fred never generates or logs this value "
            "itself, in any environment. Ignored if bootstrap_token_env_var is "
            "set. None disables the POST /bootstrap/platform-admin endpoint."
        ),
    )
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


class FrontendBootstrapConfig(BaseModel):
    """Static frontend bootstrap configuration served by control-plane."""

    feature_flags: FrontendFeatureFlags = Field(default_factory=FrontendFeatureFlags)


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
    # Mirrors fred_sdk UIHints.widget: names a frontend stock form
    # widget (e.g. "document_libraries"); unknown/None falls back to the
    # type-derived default input.
    widget: str | None = None


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


class ManagedAgentTuning(BaseModel):
    """Minimal runtime-compatible tuning payload owned by control-plane."""

    role: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    fields: list[ManagedAgentFieldSpec] = Field(default_factory=list)
    # The MCP tuning trio (mcp_servers / selected_mcp_server_ids /
    # mcp_config_values) was retired at Tier 1 (#1978, RFC §3.8): an MCP server
    # is now an ordinary capability keyed by its plain catalog server id
    # (#1988). Its activation lives in `selected_capability_ids` and its
    # per-server config in `capability_config`.
    selected_capability_ids: list[str] | None = Field(
        default=None,
        description=(
            "Capability activation policy (#1974, RFC AGENT-CAPABILITY §3.8). "
            "None means inherit the template default selection; [] means "
            "activate no capabilities; a non-empty list means activate exactly "
            "that set. Validated at save time against the capabilities the "
            "instance's bound pod advertises (unknown ids -> HTTP 422)."
        ),
    )
    capability_config: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-capability stored config keyed by capability id. Each slice "
            "is the pod-validated {'schema_version', 'config'} envelope "
            "returned by the pod's validate-config round-trip, persisted "
            "VERBATIM — opaque to control-plane; the pod is the schema "
            "authority (RFC §3.8). Asset binaries never appear here — only "
            "KF storage keys."
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


class CapabilitiesConfig(BaseModel):
    """Deployment policy for agent-capability team scoping (CAPAB-01 / #1980).

    RFC AGENT-CAPABILITY §8.3. Security-sensitive operators can start every
    capability admin-gated (`default_policy: explicit`) instead of honoring the
    `manifest.team_scope: default_on` seeds.

    The personal-space class position is now pure FGA runtime state, admin-
    toggleable via `PUT /admin/capabilities/{id}/personal-scope` (RFC §8.4,
    amended 2026-07-16 — the former `personal_defaults` config-seeding list is
    withdrawn).
    """

    default_policy: Literal["seed", "explicit"] = Field(
        default="seed",
        description=(
            "seed = honor manifest default-on seeds at first registration; "
            "explicit = ignore seeds, start everything admin-gated."
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
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
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


class GcsContentStorageConfig(BaseModel):
    """
    Google Cloud Storage content store. Authentication uses Application Default
    Credentials / Workload Identity (no JSON key required).
    """

    type: Literal["gcs"]
    bucket_name: str = Field(
        default="control-plane-content",
        description="Content store bucket name (suffix '-objects' is used for banner objects)",
    )
    project_id: str | None = Field(
        default=None, description="GCP project id; inferred from ADC when empty."
    )
    signing_service_account_email: str | None = Field(
        default=None,
        description=(
            "Service account email used to sign V4 signed URLs for browser-facing "
            "banner/logo images, via IAM signBlob under Workload Identity (no JSON "
            "key). Required for content_storage.type=gcs; startup fails clearly when "
            "omitted. The Workload Identity service account must hold "
            "iam.serviceAccounts.signBlob on this account, which must have "
            "storage.objects.get on the objects bucket."
        ),
    )


ContentStorageConfig = Annotated[
    Union[
        LocalContentStorageConfig, MinioContentStorageConfig, GcsContentStorageConfig
    ],
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
    log_store: Optional[LogStorageConfig] = None


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
