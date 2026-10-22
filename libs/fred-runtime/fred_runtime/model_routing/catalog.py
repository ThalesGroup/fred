# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
YAML catalog loader for v2 model-routing policies.

This keeps model-routing configuration isolated from the main Fred configuration
file and provides a strict Pydantic contract for externalized model catalogs.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
import yaml
from fred_core.common import ModelConfiguration
from pydantic import Field, PrivateAttr, field_validator, model_validator

from .contracts import (
    FrozenModel,
    ModelCapability,
    ModelProfile,
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


def _valid_model_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def base_url_from_models_url(models_url: str) -> str:
    parts = urlsplit(models_url)
    if (
        models_url != models_url.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in models_url)
        or parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "?" in models_url
        or "#" in models_url
        or not parts.path.endswith("/models")
        or parts.path.endswith("//models")
    ):
        raise ValueError(
            "discovery URL must be an HTTP(S) /models URL without credentials, query or fragment"
        )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path[: -len("/models")], "", "")
    ).rstrip("/")


class ModelDiscoverySource(FrozenModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    base_url: str
    default_model_id: str | None = None
    include_model_ids: tuple[str, ...] | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or "?" in value
            or "#" in value
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                "discovery base_url must be an HTTP(S) URL without credentials, query or fragment"
            )
        return value.rstrip("/")

    @model_validator(mode="after")
    def _validate_ids(self) -> "ModelDiscoverySource":
        if self.default_model_id is not None and not _valid_model_id(
            self.default_model_id
        ):
            raise ValueError("discovery default_model_id is invalid")
        if self.include_model_ids is not None and (
            not self.include_model_ids
            or any(not _valid_model_id(item) for item in self.include_model_ids)
            or len(set(self.include_model_ids)) != len(self.include_model_ids)
        ):
            raise ValueError(
                "discovery include_model_ids must contain distinct nonblank ids"
            )
        return self


def _positive_int(value: object) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def _display_name(item: dict[str, Any]) -> str | None:
    for key in ("name", "display_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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
    default_profile_by_capability: dict[ModelCapability, str] = Field(
        default_factory=dict
    )
    profiles: tuple[ModelProfile, ...] = ()
    agent_profile_overrides: dict[str, str] = Field(default_factory=dict)
    discovery: ModelDiscoverySource | None = None
    _discovered_profile_ids: tuple[str, ...] = PrivateAttr(default=())

    @property
    def discovered_profile_ids(self) -> tuple[str, ...]:
        return self._discovered_profile_ids

    @model_validator(mode="after")
    def _validate_discovery_default(self) -> "ModelCatalog":
        if (
            self.discovery is not None
            and self.discovery.default_model_id is not None
            and ModelCapability.CHAT in self.default_profile_by_capability
        ):
            raise ValueError(
                "discovery default_model_id conflicts with the static chat default"
            )
        return self

    def resolve_discovery(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        models_url: str | None = None,
        allow_missing_default: bool = False,
    ) -> "ModelCatalog":
        source = self.discovery
        if source is None:
            return self
        base_url = (
            base_url_from_models_url(models_url)
            if models_url is not None
            else source.base_url
        )
        credential = os.getenv("OPENAI_API_KEY")
        if not credential:
            raise ValueError(
                f"Model discovery source {source.source_id!r} requires OPENAI_API_KEY"
            )
        try:
            with httpx.Client(
                timeout=5.0, follow_redirects=False, transport=transport
            ) as client:
                with client.stream(
                    "GET",
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {credential}"},
                ) as response:
                    if response.status_code != 200:
                        raise ValueError(f"HTTP {response.status_code}")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 1_048_576:
                            raise ValueError("response exceeds 1 MiB")
                        chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            cause = (
                str(exc)
                if isinstance(exc, ValueError)
                and not isinstance(exc, json.JSONDecodeError)
                else type(exc).__name__
            )
            raise ValueError(
                f"Model discovery source {source.source_id!r} failed: {cause}"
            ) from None
        return self._resolve_discovery_payload(
            payload, base_url=base_url, allow_missing_default=allow_missing_default
        )

    async def resolve_discovery_async(
        self,
        *,
        models_url: str | None = None,
        allow_missing_default: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "ModelCatalog":
        source = self.discovery
        if source is None:
            return self
        base_url = (
            base_url_from_models_url(models_url) if models_url else source.base_url
        )
        credential = os.getenv("OPENAI_API_KEY")
        if not credential:
            raise ValueError(
                f"Model discovery source {source.source_id!r} requires OPENAI_API_KEY"
            )
        try:
            async with httpx.AsyncClient(
                timeout=5.0, follow_redirects=False, transport=transport
            ) as client:
                async with client.stream(
                    "GET",
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {credential}"},
                ) as response:
                    if response.status_code != 200:
                        raise ValueError(f"HTTP {response.status_code}")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 1_048_576:
                            raise ValueError("response exceeds 1 MiB")
                        chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            cause = (
                str(exc)
                if isinstance(exc, ValueError)
                and not isinstance(exc, json.JSONDecodeError)
                else type(exc).__name__
            )
            raise ValueError(
                f"Model discovery source {source.source_id!r} failed: {cause}"
            ) from None
        return self._resolve_discovery_payload(
            payload, base_url=base_url, allow_missing_default=allow_missing_default
        )

    def _resolve_discovery_payload(
        self, payload: Any, *, base_url: str, allow_missing_default: bool
    ) -> "ModelCatalog":
        source = self.discovery
        if source is None:
            return self
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError(
                f"Model discovery source {source.source_id!r} returned no data list"
            )

        included = (
            set(source.include_model_ids)
            if source.include_model_ids is not None
            else None
        )
        selected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in payload["data"]:
            candidate_id = item.get("id") if isinstance(item, dict) else None
            if included is not None and (
                not isinstance(candidate_id, str) or candidate_id not in included
            ):
                continue
            if not isinstance(item, dict) or not _valid_model_id(candidate_id):
                raise ValueError(
                    f"Model discovery source {source.source_id!r} returned an invalid model id"
                )
            model_id = item["id"]
            if model_id in seen_ids:
                raise ValueError(
                    f"Model discovery source {source.source_id!r} returned duplicate model ids"
                )
            seen_ids.add(model_id)
            selected.append(item)
        if not allow_missing_default and (
            not selected or (included is not None and not included.issubset(seen_ids))
        ):
            raise ValueError(
                f"Model discovery source {source.source_id!r} has no complete selected inventory"
            )

        profiles = list(self.profiles)
        existing_profile_ids = {profile.profile_id for profile in profiles}
        existing_capability_ids = {profile.capability_id for profile in profiles}
        discovered_profile_ids: list[str] = []
        default_profile_id: str | None = None
        for item in selected:
            wire_id = item["id"]
            digest = sha256(wire_id.encode("utf-8")).hexdigest()
            profile_id = f"discovered.chat.{source.source_id}.{digest}"
            context = _positive_int(item.get("context_length")) or _positive_int(
                item.get("max_model_len")
            )
            profile = ModelProfile(
                profile_id=profile_id,
                capability=ModelCapability.CHAT,
                model_id=f"discovered.{source.source_id}.{digest}",
                model_display_name=_display_name(item),
                context_window_tokens=context,
                max_input_tokens=_positive_int(item.get("max_input_tokens")),
                max_output_tokens=_positive_int(item.get("max_output_tokens")),
                model=ModelConfiguration(
                    provider="openai",
                    name=wire_id,
                    settings={"base_url": base_url},
                ),
            )
            if (
                profile_id in existing_profile_ids
                or profile.capability_id in existing_capability_ids
            ):
                raise ValueError(
                    f"Model discovery source {source.source_id!r} conflicts with a static model identity"
                )
            profiles.append(profile)
            discovered_profile_ids.append(profile_id)
            existing_profile_ids.add(profile_id)
            existing_capability_ids.add(profile.capability_id)
            if wire_id == source.default_model_id:
                default_profile_id = profile_id
        defaults = dict(self.default_profile_by_capability)
        if source.default_model_id is not None:
            if default_profile_id is None and not allow_missing_default:
                raise ValueError(
                    f"Model discovery source {source.source_id!r} is missing its default model"
                )
            if default_profile_id is not None:
                defaults[ModelCapability.CHAT] = default_profile_id
        resolved = self.model_copy(
            update={
                "profiles": tuple(profiles),
                "default_profile_by_capability": defaults,
                "discovery": source.model_copy(update={"base_url": base_url}),
            }
        )
        resolved._discovered_profile_ids = tuple(discovered_profile_ids)
        return resolved

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
            if "base_url" in profile_settings:
                merged_settings.pop("openai_api_base", None)
            elif "openai_api_base" in profile_settings:
                merged_settings.pop("base_url", None)
            resolved_model = profile.model.model_copy(
                update={"settings": merged_settings}
            )
            resolved_profiles.append(
                profile.model_copy(update={"model": resolved_model})
            )

        return ModelRoutingPolicy(
            default_profile_by_capability=dict(self.default_profile_by_capability),
            profiles=tuple(resolved_profiles),
            agent_profile_overrides=dict(self.agent_profile_overrides),
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
    return load_model_catalog(path).resolve_discovery().to_policy()
