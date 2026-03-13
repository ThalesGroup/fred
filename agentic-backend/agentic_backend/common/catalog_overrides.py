from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.common.structures import AgentSettings, Configuration
from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.agents.v2.model_routing.contracts import (
    ModelCapability,
    ModelRoutingPolicy,
)

logger = logging.getLogger(__name__)

AGENTS_CATALOG_ENV = "FRED_AGENTS_CATALOG_FILE"
MCP_CATALOG_ENV = "FRED_MCP_CATALOG_FILE"
MODELS_CATALOG_ENV = "FRED_MODELS_CATALOG_FILE"
MODELS_CATALOG_COMPAT_ENV = "FRED_V2_MODELS_CATALOG_FILE"
MODEL_ROUTING_PRESETS_ENABLED_ENV = "FRED_V2_MODEL_ROUTING_PRESETS_ENABLED"
MODELS_DEFAULT_CHAT_PROFILE_ENV = "FRED_MODELS_DEFAULT_CHAT_PROFILE_ID"
MODELS_DEFAULT_LANGUAGE_PROFILE_ENV = "FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID"
AGENTS_CATALOG_DEFAULT_PATH = "./config/agents_catalog.yaml"
MCP_CATALOG_DEFAULT_PATH = "./config/mcp_catalog.yaml"
MODELS_CATALOG_DEFAULT_PATH = "./config/models_catalog.yaml"


class _CatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReactProfileCatalogItem(_CatalogFile):
    profile_id: str = Field(..., min_length=1)
    enabled: bool = True


class AgentsCatalog(_CatalogFile):
    version: Literal["v1"] = "v1"
    agents: list[AgentSettings] = Field(default_factory=list)
    react_profiles: list[ReactProfileCatalogItem] | None = None


class McpCatalog(_CatalogFile):
    version: Literal["v1"] = "v1"
    servers: list[MCPServerConfiguration] = Field(default_factory=list)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"Catalog file is empty: {path}")
    if not isinstance(payload, dict):
        raise ValueError(f"Catalog file must be a YAML mapping object: {path}")
    return payload


def _resolve_catalog_path(env_var: str, default_path: str) -> Path:
    return Path(os.getenv(env_var, default_path))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    logger.warning(
        "[CONFIG][CATALOG] Invalid boolean for %s=%r, defaulting to %s",
        name,
        raw,
        default,
    )
    return default


@dataclass(frozen=True, slots=True)
class ModelRoutingBootstrapConfig:
    """
    Centralized bootstrap configuration for v2 model routing.

    This object intentionally carries only configuration-source decisions.
    Runtime/model logic stays in routed factory + resolver layers.
    """

    catalog_path: Path
    catalog_exists: bool
    presets_enabled: bool


def resolve_models_catalog_path() -> Path:
    """
    Resolve canonical models catalog path with compatibility fallback.

    Precedence:
    1. FRED_MODELS_CATALOG_FILE
    2. FRED_V2_MODELS_CATALOG_FILE (compat)
    3. ./config/models_catalog.yaml
    """

    explicit = os.getenv(MODELS_CATALOG_ENV)
    if explicit:
        return Path(explicit)
    compat = os.getenv(MODELS_CATALOG_COMPAT_ENV)
    if compat:
        return Path(compat)
    return Path(MODELS_CATALOG_DEFAULT_PATH)


def resolve_model_routing_bootstrap_config(
    *, default_presets_enabled: bool = False
) -> ModelRoutingBootstrapConfig:
    """
    Resolve startup inputs required to build routed chat-model factory.

    This is the single source of truth used by runtime wiring code so env
    parsing does not spread into agent runtime factories.
    """

    catalog_path = resolve_models_catalog_path()
    return ModelRoutingBootstrapConfig(
        catalog_path=catalog_path,
        # Catalog loading is globally disabled for now.
        catalog_exists=False,
        presets_enabled=_env_bool(
            MODEL_ROUTING_PRESETS_ENABLED_ENV, default_presets_enabled
        ),
    )


def load_agents_catalog(path: str | Path) -> AgentsCatalog:
    catalog_path = Path(path)
    return AgentsCatalog.model_validate(_load_yaml_mapping(catalog_path))


def load_mcp_catalog(path: str | Path) -> McpCatalog:
    catalog_path = Path(path)
    return McpCatalog.model_validate(_load_yaml_mapping(catalog_path))


def _resolve_default_model_from_catalog(
    *,
    policy: ModelRoutingPolicy,
    capability: ModelCapability,
    profile_override_id: str | None = None,
) -> tuple[str, Any] | None:
    default_profile_id = (
        profile_override_id or policy.default_profile_by_capability.get(capability)
    )
    if default_profile_id is None:
        return None
    for profile in policy.profiles:
        if profile.profile_id == default_profile_id:
            if profile.capability != capability:
                raise ValueError(
                    f"models catalog profile override '{default_profile_id}' has "
                    f"capability '{profile.capability.value}', expected "
                    f"'{capability.value}'."
                )
            return profile.profile_id, profile.model.model_copy(deep=True)
    raise ValueError(
        f"models catalog profile '{default_profile_id}' for capability "
        f"'{capability.value}' was not found in profiles."
    )


def _validate_required_model_defaults(configuration: Configuration) -> None:
    if configuration.ai.default_chat_model is not None:
        return
    raise ValueError(
        "Missing required chat model configuration. "
        "Define 'ai.default_chat_model' in configuration YAML "
        "or provide a models catalog with "
        "'default_profile_by_capability.chat'."
    )


def apply_external_catalog_overrides(configuration: Configuration) -> Configuration:
    """
    Keep runtime configuration YAML as the single source of truth.

    Catalog files (agents/MCP/models) are intentionally ignored.
    """

    # ReAct profile visibility is catalog-driven.
    # Safe default is "none exposed" when no catalog/profile section is provided.
    configuration.ai.react_profile_allowlist = []
    logger.warning(
        "[CONFIG][CATALOG] Catalog loading is disabled. Using configuration YAML only."
    )

    _validate_required_model_defaults(configuration)

    return configuration
