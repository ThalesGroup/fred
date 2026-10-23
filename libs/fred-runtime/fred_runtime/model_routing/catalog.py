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
from urllib.parse import quote, urlsplit, urlunsplit

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
    discovery: tuple[ModelDiscoverySource, ...] | None = None
    _discovered_profile_ids: tuple[str, ...] = PrivateAttr(default=())
    _discovered_profile_sources: dict[str, str] = PrivateAttr(default_factory=dict)
    _verified_chat_profile_ids: tuple[str, ...] = PrivateAttr(default=())
    _verified_discovery_source_ids: frozenset[str] = PrivateAttr(
        default_factory=frozenset
    )

    @property
    def effective_default_profile_by_capability(self) -> dict[ModelCapability, str]:
        defaults = dict(self.default_profile_by_capability)
        if ModelCapability.CHAT not in defaults:
            manual_chat_ids = [
                profile.profile_id
                for profile in self.profiles
                if profile.capability == ModelCapability.CHAT
                and profile.profile_id not in self._discovered_profile_sources
            ]
            if len(manual_chat_ids) == 1:
                defaults[ModelCapability.CHAT] = manual_chat_ids[0]
        return defaults

    @field_validator("discovery", mode="before")
    @classmethod
    def _validate_discovery_list(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list) or not value:
            raise ValueError("discovery must be a nonempty list of sources")
        return value

    @property
    def discovered_profile_ids(self) -> tuple[str, ...]:
        return self._discovered_profile_ids

    @property
    def verified_chat_profile_ids(self) -> tuple[str, ...]:
        return self._verified_chat_profile_ids

    @property
    def discovery_sources(self) -> tuple[ModelDiscoverySource, ...]:
        return self.discovery or ()

    def _replace_discovery_source(
        self, source: ModelDiscoverySource
    ) -> tuple[ModelDiscoverySource, ...]:
        return tuple(
            source if item.source_id == source.source_id else item
            for item in self.discovery_sources
        )

    @property
    def discovered_profile_sources(self) -> dict[str, str]:
        return dict(self._discovered_profile_sources)

    @property
    def verified_discovery_source_ids(self) -> frozenset[str]:
        return self._verified_discovery_source_ids

    def discovery_source(
        self, source_id: str | None = None
    ) -> ModelDiscoverySource | None:
        sources = self.discovery_sources
        if source_id is None:
            if len(sources) > 1:
                raise ValueError("source_id is required for multiple discovery sources")
            return sources[0] if sources else None
        return next(
            (source for source in sources if source.source_id == source_id), None
        )

    def with_discovery_source_from(
        self, candidate: "ModelCatalog", source_id: str
    ) -> "ModelCatalog":
        old_owned = {
            profile_id
            for profile_id, owner in self._discovered_profile_sources.items()
            if owner == source_id
        }
        new_owned = {
            profile_id
            for profile_id, owner in candidate._discovered_profile_sources.items()
            if owner == source_id
        }
        source = candidate.discovery_source(source_id)
        if source is None:
            raise ValueError(f"Unknown discovery source {source_id!r}")
        merged = self.model_copy(
            update={
                "profiles": tuple(
                    profile
                    for profile in self.profiles
                    if profile.profile_id not in old_owned
                )
                + tuple(
                    profile
                    for profile in candidate.profiles
                    if profile.profile_id in new_owned
                ),
                "discovery": self._replace_discovery_source(source),
            }
        )
        merged._discovered_profile_sources = {
            **{
                profile_id: owner
                for profile_id, owner in self._discovered_profile_sources.items()
                if owner != source_id
            },
            **{profile_id: source_id for profile_id in new_owned},
        }
        merged._discovered_profile_ids = tuple(merged._discovered_profile_sources)
        merged._verified_chat_profile_ids = tuple(
            profile_id
            for profile_id in self._verified_chat_profile_ids
            if profile_id not in old_owned
        ) + tuple(
            profile_id
            for profile_id in candidate._verified_chat_profile_ids
            if profile_id in new_owned
        )
        merged._verified_discovery_source_ids = (
            self._verified_discovery_source_ids - {source_id}
        ) | (candidate._verified_discovery_source_ids & {source_id})
        return merged

    async def fetch_discovered_model_detail(
        self,
        *,
        source_id: str,
        model_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> dict[str, Any]:
        source = self.discovery_source(source_id)
        if source is None or not any(
            profile.model.name == model_id
            and self._discovered_profile_sources.get(profile.profile_id) == source_id
            for profile in self.profiles
        ):
            raise ValueError("Unknown discovered model")
        credential = os.getenv("OPENAI_API_KEY")
        if not credential:
            raise ValueError("Model discovery credential is unavailable")
        try:
            async with httpx.AsyncClient(
                timeout=5.0, follow_redirects=False, transport=transport
            ) as client:
                async with client.stream(
                    "GET",
                    f"{source.base_url}/models/{quote(model_id, safe='')}",
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
            cause = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            raise ValueError(f"Model detail request failed: {cause}") from None
        if not isinstance(payload, dict):
            raise ValueError("Model detail response must be an object")
        return payload

    @model_validator(mode="after")
    def _validate_discovery_default(self) -> "ModelCatalog":
        sources = self.discovery_sources
        if len({source.source_id for source in sources}) != len(sources):
            raise ValueError("discovery source_ids must be unique")
        return self

    def resolve_discovery(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        models_url: str | None = None,
        source_id: str | None = None,
        allow_missing_default: bool = False,
    ) -> "ModelCatalog":
        if source_id is None and len(self.discovery_sources) > 1:
            if models_url is not None:
                raise ValueError(
                    "source_id is required to override one of several sources"
                )
            resolved = self
            for candidate in self.discovery_sources:
                resolved = resolved.resolve_discovery(
                    transport=transport,
                    source_id=candidate.source_id,
                    allow_missing_default=allow_missing_default,
                )
            return resolved
        source = self.discovery_source(source_id)
        if source is None:
            if source_id is not None:
                raise ValueError(f"Unknown discovery source {source_id!r}")
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
            payload,
            source=source,
            base_url=base_url,
            allow_missing_default=allow_missing_default,
        )

    async def resolve_discovery_async(
        self,
        *,
        models_url: str | None = None,
        source_id: str | None = None,
        allow_missing_default: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "ModelCatalog":
        if source_id is None and len(self.discovery_sources) > 1:
            if models_url is not None:
                raise ValueError(
                    "source_id is required to override one of several sources"
                )
            resolved = self
            for candidate in self.discovery_sources:
                resolved = await resolved.resolve_discovery_async(
                    source_id=candidate.source_id,
                    allow_missing_default=allow_missing_default,
                    transport=transport,
                )
            return resolved
        source = self.discovery_source(source_id)
        if source is None:
            if source_id is not None:
                raise ValueError(f"Unknown discovery source {source_id!r}")
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
            payload,
            source=source,
            base_url=base_url,
            allow_missing_default=allow_missing_default,
        )

    def _resolve_discovery_payload(
        self,
        payload: Any,
        *,
        source: ModelDiscoverySource,
        base_url: str,
        allow_missing_default: bool,
    ) -> "ModelCatalog":
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
            capabilities = item.get("capabilities") if isinstance(item, dict) else None
            if (
                isinstance(capabilities, dict)
                and "completion_chat" in capabilities
                and capabilities["completion_chat"] is not True
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

        old_source_profiles = {
            profile_id
            for profile_id, owner in self._discovered_profile_sources.items()
            if owner == source.source_id
        }
        profiles = [
            profile
            for profile in self.profiles
            if profile.profile_id not in old_source_profiles
        ]
        existing_profile_ids = {profile.profile_id for profile in profiles}
        existing_capability_ids = {profile.capability_id for profile in profiles}
        discovered_profile_sources = {
            profile_id: owner
            for profile_id, owner in self._discovered_profile_sources.items()
            if owner != source.source_id
        }
        verified_chat_profile_ids = [
            profile_id
            for profile_id in self._verified_chat_profile_ids
            if profile_id not in old_source_profiles
        ]
        for item in selected:
            wire_id = item["id"]
            digest = sha256(wire_id.encode("utf-8")).hexdigest()
            profile_id = f"discovered.chat.{source.source_id}.{digest}"
            context = (
                _positive_int(item.get("context_length"))
                or _positive_int(item.get("max_model_len"))
                or _positive_int(item.get("max_context_length"))
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
            discovered_profile_sources[profile_id] = source.source_id
            capabilities = item.get("capabilities")
            if (
                isinstance(capabilities, dict)
                and capabilities.get("completion_chat") is True
            ):
                verified_chat_profile_ids.append(profile_id)
            existing_profile_ids.add(profile_id)
            existing_capability_ids.add(profile.capability_id)
        source_update = source.model_copy(update={"base_url": base_url})
        resolved = self.model_copy(
            update={
                "profiles": tuple(profiles),
                "discovery": self._replace_discovery_source(source_update),
            }
        )
        resolved._discovered_profile_sources = discovered_profile_sources
        resolved._discovered_profile_ids = tuple(discovered_profile_sources)
        resolved._verified_chat_profile_ids = tuple(verified_chat_profile_ids)
        resolved._verified_discovery_source_ids = (
            self._verified_discovery_source_ids | {source.source_id}
        )
        return resolved

    def to_policy(self) -> ModelRoutingPolicy:
        effective_defaults = self.effective_default_profile_by_capability
        if any(
            profile_id in self._discovered_profile_sources
            for profile_id in effective_defaults.values()
        ):
            raise ValueError(
                "default_profile_by_capability must reference a manual profile"
            )
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
            default_profile_by_capability=effective_defaults,
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
