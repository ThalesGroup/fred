from __future__ import annotations

from fred_core.common.structures import PostgresStoreConfig
from fred_core.security.structure import UserSecurity
from pydantic import AnyUrl, BaseModel


class AppConfig(BaseModel):
    base_url: str = "/evaluation/v1"
    log_level: str = "info"
    gcu_version: str | None = None


class ControlPlaneConfig(BaseModel):
    base_url: str = "http://localhost:8222/control-plane/v1"
    credential_ref: str = "EVALUATION_CONTROL_PLANE_TOKEN"


class SecurityConfig(BaseModel):
    user: UserSecurity = UserSecurity(
        enabled=False,
        realm_url=AnyUrl("http://localhost:8080/realms/app"),
        client_id="app",
    )
    authorized_origins: list[str] = []


class EvaluationConfig(BaseModel):
    app: AppConfig = AppConfig()
    database: PostgresStoreConfig = PostgresStoreConfig()
    control_plane: ControlPlaneConfig = ControlPlaneConfig()
    security: SecurityConfig = SecurityConfig()