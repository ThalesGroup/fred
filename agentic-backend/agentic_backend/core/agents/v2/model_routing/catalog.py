"""
YAML catalog loader for v2 model-routing policies.

This keeps model-routing configuration isolated from the main Fred configuration
file and provides a strict Pydantic contract for externalized model catalogs.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field

from .contracts import (
    FrozenModel,
    ModelCapability,
    ModelProfile,
    ModelRouteRule,
    ModelRoutingPolicy,
)


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, override_value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged[key] = _deep_merge_dict(base_value, override_value)
        else:
            merged[key] = deepcopy(override_value)
    return merged


class ModelCatalog(FrozenModel):
    """
    File contract for `models_catalog.yaml`.

    Versioning is explicit so we can evolve schema without guessing intent.
    """

    version: Literal["v1"] = "v1"
    common_model_settings: dict[str, Any] = Field(default_factory=dict)
    common_model_settings_by_capability: dict[ModelCapability, dict[str, Any]] = Field(
        default_factory=dict
    )
    default_profile_by_capability: dict[ModelCapability, str]
    profiles: tuple[ModelProfile, ...]
    rules: tuple[ModelRouteRule, ...] = ()

    def to_policy(self) -> ModelRoutingPolicy:
        resolved_profiles: list[ModelProfile] = []
        for profile in self.profiles:
            global_defaults = self.common_model_settings
            capability_defaults = self.common_model_settings_by_capability.get(
                profile.capability, {}
            )
            profile_settings = profile.model.settings or {}
            merged_settings = _deep_merge_dict(global_defaults, capability_defaults)
            merged_settings = _deep_merge_dict(merged_settings, profile_settings)
            resolved_model = profile.model.model_copy(
                update={"settings": merged_settings}
            )
            resolved_profiles.append(
                profile.model_copy(update={"model": resolved_model})
            )

        return ModelRoutingPolicy(
            default_profile_by_capability=dict(self.default_profile_by_capability),
            profiles=tuple(resolved_profiles),
            rules=self.rules,
        )


def load_model_catalog(path: str | Path) -> ModelCatalog:
    catalog_path = Path(path)
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"Model catalog file is empty: {catalog_path}")
    if not isinstance(payload, dict):
        raise ValueError(f"Model catalog must be a YAML mapping object: {catalog_path}")
    return ModelCatalog.model_validate(payload)


def load_model_routing_policy_from_catalog(path: str | Path) -> ModelRoutingPolicy:
    return load_model_catalog(path).to_policy()
