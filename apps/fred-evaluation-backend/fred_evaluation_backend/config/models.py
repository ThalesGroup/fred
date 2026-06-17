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
    # Base URL used to resolve relative evaluate_url paths returned by prepare-execution.
    # In prod this is empty (ingress handles routing). In local dev, set to http://localhost:8000.
    runtime_base_url: str = ""


class SecurityConfig(BaseModel):
    user: UserSecurity = UserSecurity(
        enabled=False,
        realm_url=AnyUrl("http://localhost:8080/realms/app"),
        client_id="app",
    )
    authorized_origins: list[str] = []


class JudgeProfileSettings(BaseModel):
    api_key_env: str | None = None
    api_base: str | None = None
    request_timeout: int = 30


class JudgeProfile(BaseModel):
    provider: str  # litellm | openai | ollama
    model: str
    settings: JudgeProfileSettings = JudgeProfileSettings()


class WorkerConfig(BaseModel):
    max_concurrent_cases: int = 4
    poll_interval_seconds: int = 5
    judge_profiles: dict[str, JudgeProfile] = {}


class EvaluationConfig(BaseModel):
    app: AppConfig = AppConfig()
    database: PostgresStoreConfig = PostgresStoreConfig()
    control_plane: ControlPlaneConfig = ControlPlaneConfig()
    security: SecurityConfig = SecurityConfig()
    worker: WorkerConfig = WorkerConfig()
