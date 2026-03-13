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
from agentic_backend.core.agents.v2.model_routing.catalog import (
    ModelCatalog,
    _deep_merge_dict,
    load_model_catalog,
)
from agentic_backend.core.agents.v2.model_routing.contracts import (
    ModelCapability,
    ModelRoutingPolicy,
)

logger = logging.getLogger(__name__)

AGENTS_CATALOG_ENV = "FRED_AGENTS_CATALOG_FILE"
AGENTS_CATALOG_OVERRIDE_ENV = "FRED_AGENTS_CATALOG_OVERRIDE_FILE"
MCP_CATALOG_ENV = "FRED_MCP_CATALOG_FILE"
MCP_CATALOG_OVERRIDE_ENV = "FRED_MCP_CATALOG_OVERRIDE_FILE"
MODELS_CATALOG_ENV = "FRED_MODELS_CATALOG_FILE"
MODELS_CATALOG_OVERRIDE_ENV = "FRED_MODELS_CATALOG_OVERRIDE_FILE"
MODELS_CATALOG_COMPAT_ENV = "FRED_V2_MODELS_CATALOG_FILE"
MODEL_ROUTING_PRESETS_ENABLED_ENV = "FRED_V2_MODEL_ROUTING_PRESETS_ENABLED"
MODELS_DEFAULT_CHAT_PROFILE_ENV = "FRED_MODELS_DEFAULT_CHAT_PROFILE_ID"
MODELS_DEFAULT_LANGUAGE_PROFILE_ENV = "FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID"
AGENTS_CATALOG_DEFAULT_PATH = "./config/agents_catalog.yaml"
AGENTS_CATALOG_OVERRIDE_DEFAULT_PATH = "./config/agents_catalog_override.yaml"
MCP_CATALOG_DEFAULT_PATH = "./config/mcp_catalog.yaml"
MCP_CATALOG_OVERRIDE_DEFAULT_PATH = "./config/mcp_catalog_override.yaml"
MODELS_CATALOG_DEFAULT_PATH = "./config/models_catalog.yaml"
MODELS_CATALOG_OVERRIDE_DEFAULT_PATH = "./config/models_catalog_override.yaml"


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
        catalog_exists=catalog_path.exists(),
        presets_enabled=_env_bool(
            MODEL_ROUTING_PRESETS_ENABLED_ENV, default_presets_enabled
        ),
    )


def load_agents_catalog(path: str | Path) -> AgentsCatalog:
    catalog_path = Path(path)
    return AgentsCatalog.model_validate(_load_yaml_mapping(catalog_path))


def _merge_agents(
    base: AgentsCatalog,
    override_data: dict[str, Any],
) -> AgentsCatalog:
    """Deep merge Agents catalog overrides."""
    merged_data = base.model_dump()

    # Merge agents by id
    if "agents" in override_data:
        agents_by_id = {a.id: a for a in base.agents}
        for ovr in override_data["agents"]:
            agent_id = ovr.get("id")
            if agent_id and agent_id in agents_by_id:
                agent_dict = agents_by_id[agent_id].model_dump()
                merged_agent_dict = _deep_merge_dict(agent_dict, ovr)
                agents_by_id[agent_id] = AgentSettings.model_validate(merged_agent_dict)
        merged_data["agents"] = list(agents_by_id.values())

    # Merge react_profiles by profile_id
    if "react_profiles" in override_data and override_data["react_profiles"]:
        profiles_by_id = {p.profile_id: p for p in (base.react_profiles or [])}
        for ovr in override_data["react_profiles"]:
            pid = ovr.get("profile_id")
            if pid and pid in profiles_by_id:
                p_dict = profiles_by_id[pid].model_dump()
                merged_p_dict = _deep_merge_dict(p_dict, ovr)
                profiles_by_id[pid] = ReactProfileCatalogItem.model_validate(merged_p_dict)
        merged_data["react_profiles"] = list(profiles_by_id.values())

    return AgentsCatalog.model_validate(merged_data)


def load_mcp_catalog(path: str | Path) -> McpCatalog:
    catalog_path = Path(path)
    return McpCatalog.model_validate(_load_yaml_mapping(catalog_path))


def _merge_mcp_servers(
    base_servers: list[MCPServerConfiguration],
    override_servers: list[dict],
) -> list[MCPServerConfiguration]:
    """Deep merge MCP server overrides into base servers by `id`.

    For each override entry, find the matching base server by `id` and update
    only the fields present in the override.  Unmatched overrides are ignored
    with a warning.
    """
    base_by_id = {s.id: s for s in base_servers}
    for ovr in override_servers:
        server_id = ovr.get("id")
        if not server_id:
            logger.warning("[CONFIG][CATALOG] MCP override entry without 'id', skipping.")
            continue
        if server_id not in base_by_id:
            logger.warning(
                "[CONFIG][CATALOG] MCP override id=%s not found in base catalog, skipping.",
                server_id,
            )
            continue
        base_server = base_by_id[server_id]
        merged_data = base_server.model_dump()
        merged_data = _deep_merge_dict(merged_data, ovr)
        base_by_id[server_id] = MCPServerConfiguration.model_validate(merged_data)
    return list(base_by_id.values())


def _merge_models_catalog(
    base: ModelCatalog,
    override_data: dict[str, Any],
) -> ModelCatalog:
    """Deep merge Models catalog overrides."""
    merged_data = base.model_dump()

    if "common_model_settings" in override_data:
        merged_data["common_model_settings"] = _deep_merge_dict(
            merged_data["common_model_settings"], override_data["common_model_settings"]
        )

    if "default_profile_by_capability" in override_data:
        merged_data["default_profile_by_capability"].update(
            override_data["default_profile_by_capability"]
        )

    if "profiles" in override_data:
        profiles_by_id = {p.profile_id: p for p in base.profiles}
        for ovr in override_data["profiles"]:
            pid = ovr.get("profile_id")
            if pid and pid in profiles_by_id:
                # Need to handle model.settings deep merge specifically
                base_profile_dict = profiles_by_id[pid].model_dump()
                if "model" in ovr and "settings" in ovr["model"]:
                    base_profile_dict["model"]["settings"] = _deep_merge_dict(
                        base_profile_dict["model"].get("settings", {}),
                        ovr["model"]["settings"],
                    )
                    # Merge other model fields if any
                    for k, v in ovr["model"].items():
                        if k != "settings":
                            base_profile_dict["model"][k] = v
                    # Merge other profile fields if any
                    for k, v in ovr.items():
                        if k != "model":
                            base_profile_dict[k] = v
                else:
                    base_profile_dict.update(ovr)
                profiles_by_id[pid] = profiles_by_id[pid].model_validate(
                    base_profile_dict
                )
        merged_data["profiles"] = list(profiles_by_id.values())

    if "rules" in override_data:
        merged_data["rules"] = override_data["rules"]

    return ModelCatalog.model_validate(merged_data)


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
    Apply optional external catalogs over configuration YAML.

    Precedence rule (intermediate migration phase):
    - if a catalog file exists, it overrides the corresponding section from
      configuration.yaml.
    - if it does not exist, current configuration.yaml values remain unchanged.
    """

    # ReAct profile visibility is catalog-driven.
    # Safe default is "none exposed" when no catalog/profile section is provided.
    configuration.ai.react_profile_allowlist = []

    agents_catalog_path = _resolve_catalog_path(
        AGENTS_CATALOG_ENV, AGENTS_CATALOG_DEFAULT_PATH
    )
    if agents_catalog_path.exists():
        agents_catalog = load_agents_catalog(agents_catalog_path)
        configuration.ai.agents = [
            agent.model_copy(deep=True) for agent in agents_catalog.agents
        ]

        # Apply Agents catalog override
        agents_override_path = _resolve_catalog_path(
            AGENTS_CATALOG_OVERRIDE_ENV, AGENTS_CATALOG_OVERRIDE_DEFAULT_PATH
        )
        if agents_override_path.exists():
            override_data = _load_yaml_mapping(agents_override_path)
            agents_catalog = _merge_agents(agents_catalog, override_data)
            configuration.ai.agents = [
                agent.model_copy(deep=True) for agent in agents_catalog.agents
            ]
            logger.info(
                "[CONFIG][CATALOG] Applied agents catalog override from %s.",
                agents_override_path,
            )

        allowlist: list[str] = []
        seen: set[str] = set()
        for item in agents_catalog.react_profiles or []:
            if not item.enabled:
                continue
            profile_id = item.profile_id.strip()
            if not profile_id or profile_id in seen:
                continue
            seen.add(profile_id)
            allowlist.append(profile_id)
        configuration.ai.react_profile_allowlist = allowlist
        logger.info(
            "[CONFIG][CATALOG] Applied react profile allowlist from %s (enabled_profiles=%d).",
            agents_catalog_path,
            len(allowlist),
        )
        logger.info(
            "[CONFIG][CATALOG] Loaded agents catalog from %s (agents=%d).",
            agents_catalog_path,
            len(configuration.ai.agents),
        )

    mcp_catalog_path = _resolve_catalog_path(MCP_CATALOG_ENV, MCP_CATALOG_DEFAULT_PATH)
    if mcp_catalog_path.exists():
        mcp_catalog = load_mcp_catalog(mcp_catalog_path)
        configuration.mcp.servers = [
            server.model_copy(deep=True) for server in mcp_catalog.servers
        ]
        logger.info(
            "[CONFIG][CATALOG] Loaded MCP catalog from %s (servers=%d).",
            mcp_catalog_path,
            len(configuration.mcp.servers),
        )

        # Apply MCP catalog override (deep merge by server id)
        mcp_override_path = _resolve_catalog_path(
            MCP_CATALOG_OVERRIDE_ENV, MCP_CATALOG_OVERRIDE_DEFAULT_PATH
        )
        if mcp_override_path.exists():
            override_data = _load_yaml_mapping(mcp_override_path)
            override_servers = override_data.get("servers", [])
            configuration.mcp.servers = _merge_mcp_servers(
                configuration.mcp.servers, override_servers
            )
            logger.info(
                "[CONFIG][CATALOG] Applied MCP catalog override from %s (overrides=%d).",
                mcp_override_path,
                len(override_servers),
            )

    models_catalog_path = resolve_models_catalog_path()
    if models_catalog_path.exists():
        models_catalog = load_model_catalog(models_catalog_path)

        # Apply Models catalog override
        models_override_path = _resolve_catalog_path(
            MODELS_CATALOG_OVERRIDE_ENV, MODELS_CATALOG_OVERRIDE_DEFAULT_PATH
        )
        if models_override_path.exists():
            override_data = _load_yaml_mapping(models_override_path)
            models_catalog = _merge_models_catalog(models_catalog, override_data)
            logger.info(
                "[CONFIG][CATALOG] Applied models catalog override from %s.",
                models_override_path,
            )

        policy = models_catalog.to_policy()
        chat_override_profile = os.getenv(MODELS_DEFAULT_CHAT_PROFILE_ENV)
        language_override_profile = os.getenv(MODELS_DEFAULT_LANGUAGE_PROFILE_ENV)
        chat_default = _resolve_default_model_from_catalog(
            policy=policy,
            capability=ModelCapability.CHAT,
            profile_override_id=chat_override_profile,
        )
        if chat_default is None:
            raise ValueError(
                "models catalog is missing a chat default. "
                "Set 'default_profile_by_capability.chat'."
            )
        language_default = _resolve_default_model_from_catalog(
            policy=policy,
            capability=ModelCapability.LANGUAGE,
            profile_override_id=language_override_profile,
        )
        configuration.ai.default_chat_model = chat_default[1]
        configuration.ai.default_language_model = (
            language_default[1]
            if language_default is not None
            else chat_default[1].model_copy(deep=True)
        )
        logger.info(
            "[CONFIG][CATALOG] Loaded models catalog from %s (chat=%s, language=%s).",
            models_catalog_path,
            chat_default[0],
            language_default[0] if language_default is not None else chat_default[0],
        )

    _validate_required_model_defaults(configuration)

    return configuration
