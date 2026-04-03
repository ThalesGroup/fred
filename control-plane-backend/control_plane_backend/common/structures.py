from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

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
    scheduler: SchedulerConfig
    security: SecurityConfiguration = Field(default_factory=_default_security)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    policies: PolicyConfig = Field(default_factory=PolicyConfig)


class AppState(BaseModel):
    service: str = "control-plane"
    loaded_config_file: Optional[str] = None
    loaded_env_file: Optional[str] = None
