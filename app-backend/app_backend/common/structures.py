from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class AppConfig(BaseModel):
    name: str = "Fred Single Process Backend"
    docs_enabled: bool = False


class EmbeddedServiceConfig(BaseModel):
    enabled: bool = True
    path_prefix: str
    config_file: str

    @field_validator("path_prefix")
    @classmethod
    def validate_path_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("path_prefix must not be empty")
        if not normalized.startswith("/"):
            raise ValueError("path_prefix must start with '/'")
        if normalized != "/" and normalized.endswith("/"):
            normalized = normalized.rstrip("/")
        return normalized

    @field_validator("config_file")
    @classmethod
    def validate_path_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("path must not be empty")
        return normalized


class ServicesConfig(BaseModel):
    control_plane: EmbeddedServiceConfig
    agentic: EmbeddedServiceConfig
    knowledge_flow: EmbeddedServiceConfig


class Configuration(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    services: ServicesConfig

    @model_validator(mode="after")
    def validate_unique_prefixes(self) -> "Configuration":
        enabled_prefixes = []
        for service in (
            self.services.control_plane,
            self.services.agentic,
            self.services.knowledge_flow,
        ):
            if service.enabled:
                enabled_prefixes.append(service.path_prefix)

        duplicates = {
            prefix for prefix in enabled_prefixes if enabled_prefixes.count(prefix) > 1
        }
        if duplicates:
            values = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate path_prefix among enabled services: {values}")
        return self
