from __future__ import annotations

from fred_core.common.structures import PostgresStoreConfig
from fred_core.security.structure import UserSecurity
from pydantic import AnyUrl, BaseModel


class AppConfig(BaseModel):
    base_url: str = "/evaluation/v1"
    log_level: str = "info"
    gcu_version: str | None = None


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
    security: SecurityConfig = SecurityConfig()