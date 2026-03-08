from __future__ import annotations

from typing import Literal, Optional

from fred_core import (
    PostgresStoreConfig,
    PostgresTableConfig,
    SecurityConfiguration,
    TemporalSchedulerConfig,
)
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str = "Control Plane Backend"
    base_url: str = "/control-plane/v1"
    address: str = "127.0.0.1"
    port: int = 8222
    log_level: str = "info"


class SchedulerConfig(BaseModel):
    enabled: bool = False
    backend: Literal["temporal"] = "temporal"
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
                "secret_env_var": "KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET",  # nosec B105 - env var name, not a secret value
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


def _default_session_store() -> PostgresTableConfig:
    return PostgresTableConfig(type="postgres", table="session")


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig = Field(default_factory=_default_postgres_store)
    session_store: PostgresTableConfig = Field(default_factory=_default_session_store)
    purge_queue_table: str = "session_purge_queue"


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
