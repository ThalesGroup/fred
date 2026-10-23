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

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx
from fred_core import KeycloakUser

from control_plane_backend.capabilities.catalog import (
    model_display_name_overrides,
)
from control_plane_backend.model_discovery.schemas import (
    DiscoveredModel,
    DiscoverySourceStatus,
    ModelDiscoveryStatus,
    PodChatDefaults,
    PodChatDefaultStatus,
    PodChatModelOption,
    UnverifiedRuntime,
)
from control_plane_backend.model_discovery.store import StoredDiscoverySourceState
from control_plane_backend.organization_authz import (
    require_manage_capabilities,
    require_manage_model_discovery_urls,
    require_manage_platform_model_binding,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies


class DiscoveryRefreshError(Exception):
    pass


def _preparation_failure(
    responses: list[httpx.Response | BaseException], source_id: str
) -> str:
    for response in responses:
        if isinstance(response, BaseException) or response.status_code != 502:
            continue
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            continue
        if (
            isinstance(detail, str)
            and detail.startswith(f"Model discovery source {source_id!r} ")
            and len(detail) <= 300
        ):
            return detail
    return "Discovery refresh failed"


def validate_models_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        url != url.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in url)
        or parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "?" in url
        or "#" in url
        or not parts.path.endswith("/models")
        or parts.path.endswith("//models")
        or len(url) > 2048
    ):
        raise ValueError(
            "URL must be an HTTP(S) /models URL without credentials, query or fragment"
        )
    return url


def _status(
    row: StoredDiscoverySourceState, display_names: dict[str, str] | None = None
) -> DiscoverySourceStatus:
    def models(items: list[dict]) -> list[DiscoveredModel]:
        return [
            DiscoveredModel.model_validate(
                {
                    **item,
                    "display_name": (display_names or {}).get(
                        item["id"], item.get("display_name")
                    ),
                }
            )
            for item in items
        ]

    return DiscoverySourceStatus(
        source_id=row.source_id,
        yaml_url=row.yaml_url,
        override_url=row.override_url,
        effective_url=row.effective_url,
        available_models=models(row.inventory),
        removed_models=models(
            [item for item in row.removed if not item.get("dismissed")]
        ),
        new_ids=row.new_ids,
        last_success_at=row.last_success_at,
        last_attempt_at=row.last_attempt_at,
        last_error=row.last_error,
    )


async def get_status(
    user: KeycloakUser, deps: ProductServiceDependencies
) -> ModelDiscoveryStatus:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    rows = await deps.get_model_discovery_state_store().list_all()
    names = await model_display_name_overrides(deps)
    return ModelDiscoveryStatus(sources=[_status(row, names) for row in rows])


async def get_pod_chat_defaults(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    authorization: str | None,
) -> PodChatDefaults:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    sources = [
        source
        for source in deps.configuration.platform.runtime_catalog_sources
        if source.enabled
    ]
    overrides = await deps.get_pod_chat_default_store().list_all()
    fallback_overrides = await deps.get_pod_chat_default_store().list_fallbacks()
    states = await deps.get_model_discovery_state_store().list_all()
    known_available_models = {
        state.source_id: {
            item["id"]
            for item in state.inventory
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for state in states
        if state.last_success_at is not None
    }
    removed_profiles = {
        profile_id
        for state in states
        for item in state.removed
        for profile_id in item.get("chat_profile_ids", [])
    }
    client = deps.get_runtime_http_client()
    headers = {"Authorization": authorization} if authorization else None

    async def inspect(source) -> dict:
        response = await client.get(
            f"{source.base_url.rstrip('/')}/agents/models-catalog",
            headers=headers,
            timeout=5.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("Invalid pod catalog response")
        return payload

    inspected = await asyncio.gather(
        *(inspect(source) for source in sources), return_exceptions=True
    )
    pods: list[PodChatDefaultStatus] = []
    for source, result in zip(sources, inspected, strict=True):
        override = overrides.get(source.runtime_id)
        fallback_override = fallback_overrides.get(source.runtime_id)
        if isinstance(result, BaseException):
            pods.append(
                PodChatDefaultStatus(
                    runtime_id=source.runtime_id,
                    base_url=source.base_url,
                    reachable=False,
                    override_profile_id=override,
                    effective_profile_id=override,
                    fallback_override_profile_id=fallback_override,
                    effective_fallback_profile_id=fallback_override,
                )
            )
            continue
        options = [
            PodChatModelOption(
                profile_id=profile_id,
                model_id=item["id"],
                name=item["name"],
                display_name=item.get("display_name"),
                discovery_source_id=(
                    next(
                        (
                            entry.get("source_id")
                            for entry in result.get("discovery_sources", [])
                            if isinstance(entry, dict)
                            and isinstance(entry.get("source_id"), str)
                            and profile_id.startswith(
                                f"discovered.chat.{entry.get('source_id')}."
                            )
                        ),
                        None,
                    )
                ),
            )
            for item in result["models"]
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
            for profile_id in item.get("chat_profile_ids", [])
            if isinstance(profile_id, str)
        ]
        options = [
            option
            for option in options
            if option.discovery_source_id not in known_available_models
            or option.model_id in known_available_models[option.discovery_source_id]
        ]
        available = {option.profile_id for option in options}
        manual = {
            option.profile_id
            for option in options
            if option.discovery_source_id is None
        }
        yaml_default = result.get("default_chat_profile_id")
        if not isinstance(yaml_default, str):
            yaml_default = None
        unavailable = override is not None and override not in available
        fallback_unavailable = (
            fallback_override is not None and fallback_override not in manual
        )
        effective_fallback = (
            fallback_override
            if fallback_override is not None and not fallback_unavailable
            else yaml_default
            if yaml_default in manual
            else None
        )
        pods.append(
            PodChatDefaultStatus(
                runtime_id=source.runtime_id,
                base_url=source.base_url,
                reachable=True,
                yaml_profile_id=yaml_default,
                override_profile_id=override,
                effective_profile_id=(
                    override
                    if override is not None and not unavailable
                    else effective_fallback
                    if override in removed_profiles
                    else yaml_default
                ),
                override_unavailable=unavailable,
                fallback_override_profile_id=fallback_override,
                effective_fallback_profile_id=effective_fallback,
                fallback_unavailable=fallback_unavailable,
                models=options,
            )
        )
    return PodChatDefaults(pods=pods)


async def set_pod_chat_default(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    runtime_id: str,
    profile_id: str,
    authorization: str | None,
) -> PodChatDefaultStatus:
    await require_manage_platform_model_binding(deps.team_dependencies.rebac, user)
    status = await get_pod_chat_defaults(user, deps, authorization=authorization)
    pod = next((item for item in status.pods if item.runtime_id == runtime_id), None)
    if pod is None:
        raise KeyError(runtime_id)
    if not pod.reachable:
        raise DiscoveryRefreshError("Agent pod catalog is unavailable")
    if profile_id not in {option.profile_id for option in pod.models}:
        raise ValueError("Chat profile is not advertised by this agent pod")
    await deps.get_pod_chat_default_store().set(
        runtime_id, profile_id, updated_by=user.uid
    )
    return pod.model_copy(
        update={
            "override_profile_id": profile_id,
            "effective_profile_id": profile_id,
            "override_unavailable": False,
        }
    )


async def delete_pod_chat_default(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    runtime_id: str,
    authorization: str | None,
) -> PodChatDefaultStatus:
    await require_manage_platform_model_binding(deps.team_dependencies.rebac, user)
    status = await get_pod_chat_defaults(user, deps, authorization=authorization)
    pod = next((item for item in status.pods if item.runtime_id == runtime_id), None)
    if pod is None:
        raise KeyError(runtime_id)
    await deps.get_pod_chat_default_store().delete(runtime_id)
    return pod.model_copy(
        update={
            "override_profile_id": None,
            "effective_profile_id": pod.yaml_profile_id,
            "override_unavailable": False,
        }
    )


async def set_pod_chat_fallback(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    runtime_id: str,
    profile_id: str,
    authorization: str | None,
) -> PodChatDefaultStatus:
    await require_manage_platform_model_binding(deps.team_dependencies.rebac, user)
    status = await get_pod_chat_defaults(user, deps, authorization=authorization)
    pod = next((item for item in status.pods if item.runtime_id == runtime_id), None)
    if pod is None:
        raise KeyError(runtime_id)
    if not pod.reachable:
        raise DiscoveryRefreshError("Agent pod catalog is unavailable")
    manual = {
        option.profile_id for option in pod.models if option.discovery_source_id is None
    }
    if profile_id not in manual:
        raise ValueError("Fallback must be a manual chat profile from this agent pod")
    await deps.get_pod_chat_default_store().set_fallback(
        runtime_id, profile_id, updated_by=user.uid
    )
    return pod.model_copy(
        update={
            "fallback_override_profile_id": profile_id,
            "effective_fallback_profile_id": profile_id,
            "fallback_unavailable": False,
        }
    )


async def delete_pod_chat_fallback(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    runtime_id: str,
    authorization: str | None,
) -> PodChatDefaultStatus:
    await require_manage_platform_model_binding(deps.team_dependencies.rebac, user)
    status = await get_pod_chat_defaults(user, deps, authorization=authorization)
    pod = next((item for item in status.pods if item.runtime_id == runtime_id), None)
    if pod is None:
        raise KeyError(runtime_id)
    await deps.get_pod_chat_default_store().delete_fallback(runtime_id)
    manual = {
        option.profile_id for option in pod.models if option.discovery_source_id is None
    }
    return pod.model_copy(
        update={
            "fallback_override_profile_id": None,
            "effective_fallback_profile_id": (
                pod.yaml_profile_id if pod.yaml_profile_id in manual else None
            ),
            "fallback_unavailable": False,
        }
    )


async def set_url(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    source_id: str,
    url: str | None,
    authorization: str | None,
) -> DiscoverySourceStatus:
    await require_manage_model_discovery_urls(deps.team_dependencies.rebac, user)
    store = deps.get_model_discovery_state_store()
    existing = await store.get(source_id)
    if existing is None:
        raise KeyError(source_id)
    override = validate_models_url(url) if url is not None else None
    result = await refresh(
        user,
        deps,
        authorization=authorization,
        proposed_urls={source_id: override},
    )
    updated = next(
        (source for source in result.sources if source.source_id == source_id), None
    )
    if (
        updated is None
        or updated.last_error is not None
        or result.refresh_error is not None
        or result.unverified_runtimes
    ):
        raise DiscoveryRefreshError(
            "Discovery URL could not be applied to every runtime pod"
        )
    return updated


async def dismiss_removed_model(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    source_id: str,
    model_id: str,
) -> DiscoverySourceStatus:
    await require_manage_model_discovery_urls(deps.team_dependencies.rebac, user)
    row = await deps.get_model_discovery_state_store().dismiss_removed_model(
        source_id=source_id, model_id=model_id
    )
    return _status(row, await model_display_name_overrides(deps))


async def refresh(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    authorization: str | None,
    proposed_urls: dict[str, str | None] | None = None,
) -> ModelDiscoveryStatus:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    store = deps.get_model_discovery_state_store()
    client = deps.get_runtime_http_client()
    sources = [
        source
        for source in deps.configuration.platform.runtime_catalog_sources
        if source.enabled
    ]
    headers = {"Authorization": authorization} if authorization else None

    async def inspect(source):
        response = await client.get(
            f"{source.base_url.rstrip('/')}/agents/models-catalog",
            headers=headers,
            timeout=5.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("Invalid pod catalog response")
        return source, payload

    inspected = await asyncio.gather(
        *(inspect(source) for source in sources), return_exceptions=True
    )
    unverified = [
        UnverifiedRuntime(
            runtime_id=source.runtime_id,
            base_url=source.base_url,
        )
        for source, result in zip(sources, inspected, strict=True)
        if isinstance(result, BaseException)
    ]
    pod_chat_default_available: bool | None = None
    if (
        inspected
        and not unverified
        and all(
            "default_chat_profile_id" in item[1]
            for item in inspected
            if not isinstance(item, BaseException)
        )
    ):
        pod_chat_default_available = all(
            isinstance(item[1]["default_chat_profile_id"], str)
            and bool(item[1]["default_chat_profile_id"].strip())
            for item in inspected
            if not isinstance(item, BaseException)
        )
    if unverified:
        result = await get_status(user, deps)
        result.unverified_runtimes = unverified
        result.pod_chat_default_available = pod_chat_default_available
        verified_source_ids: set[str] = set()
        for item in inspected:
            if isinstance(item, BaseException):
                continue
            payload = item[1]
            advertised = payload.get("discovery_sources")
            if not isinstance(advertised, list):
                advertised = [{"source_id": payload.get("discovery_source_id")}]
            for entry in advertised:
                if isinstance(entry, dict):
                    source_id = entry.get("source_id")
                    if isinstance(source_id, str):
                        verified_source_ids.add(source_id)
        result.verified_source_ids = sorted(verified_source_ids)
        return result

    grouped: dict[str, list[tuple[str, dict]]] = {}
    for item in inspected:
        if isinstance(item, BaseException):
            continue
        source, payload = item
        advertised = payload.get("discovery_sources")
        if not isinstance(advertised, list):
            advertised = [
                {
                    "source_id": payload.get("discovery_source_id"),
                    "yaml_url": payload.get("discovery_yaml_url"),
                }
            ]
        for source_entry in advertised:
            if not isinstance(source_entry, dict):
                continue
            source_id = source_entry.get("source_id")
            yaml_url = source_entry.get("yaml_url")
            if isinstance(source_id, str) and isinstance(yaml_url, str):
                grouped.setdefault(source_id, []).append(
                    (source.base_url, {**payload, "discovery_yaml_url": yaml_url})
                )

    for source_id in (proposed_urls or {}).keys() - grouped.keys():
        existing = await store.get(source_id)
        if existing is not None:
            await store.record_failure(
                source_id=source_id,
                yaml_url=existing.yaml_url,
                error="Discovery source is not advertised by an enabled runtime pod",
            )

    for source_id, pods in grouped.items():
        yaml_url = pods[0][1]["discovery_yaml_url"]
        if any(payload.get("discovery_yaml_url") != yaml_url for _, payload in pods):
            await store.record_failure(
                source_id=source_id, yaml_url=yaml_url, error="Pod YAML URLs disagree"
            )
            continue
        existing = await store.get(source_id)
        current_revision = existing.revision if existing else 0
        changing_url = proposed_urls is not None and source_id in proposed_urls
        proposed_override = proposed_urls.get(source_id) if proposed_urls else None
        effective_url = (
            (proposed_override or yaml_url)
            if changing_url
            else (
                existing.override_url
                if existing and existing.override_url
                else yaml_url
            )
        )
        responses = await asyncio.gather(
            *(
                client.post(
                    f"{base_url.rstrip('/')}/agents/models-catalog/refresh",
                    json={
                        "source_id": source_id,
                        "models_url": effective_url,
                        "prepare": True,
                    },
                    headers=headers,
                    timeout=10.0,
                    follow_redirects=False,
                )
                for base_url, _ in pods
            ),
            return_exceptions=True,
        )
        if any(
            isinstance(response, BaseException) or response.status_code != 200
            for response in responses
        ):
            await store.record_failure(
                source_id=source_id,
                yaml_url=yaml_url,
                error=_preparation_failure(responses, source_id),
            )
            continue
        inventories: list[dict[str, dict]] = []
        preparation_tokens: list[str] = []
        pod_revisions: list[int] = []
        try:
            for response in responses:
                if isinstance(response, BaseException):
                    raise ValueError("Discovery refresh failed")
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or payload.get("discovery_source_id") != source_id
                    or payload.get("discovery_effective_url") != effective_url
                ):
                    raise ValueError("Pod returned an unexpected discovery source")
                token = payload.get("preparation_token")
                if not isinstance(token, str) or not token:
                    raise ValueError("Pod did not prepare a catalog")
                preparation_tokens.append(token)
                pod_revision = payload.get("active_revision")
                if type(pod_revision) is not int or pod_revision < 0:
                    raise ValueError("Pod did not report its catalog revision")
                pod_revisions.append(pod_revision)
                ids = payload.get("discovered_model_ids")
                items = payload.get("models")
                if not isinstance(ids, list) or not isinstance(items, list):
                    raise ValueError("Invalid pod discovery response")
                known = {
                    item["id"]: item
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                }
                if any(
                    not isinstance(model_id, str) or model_id not in known
                    for model_id in ids
                ):
                    raise ValueError("Pod discovery IDs do not match its catalog")
                inventories.append(
                    {
                        model_id: DiscoveredModel.model_validate(
                            known[model_id]
                        ).model_dump()
                        for model_id in ids
                    }
                )
        except (ValueError, TypeError, KeyError):
            await store.record_failure(
                source_id=source_id,
                yaml_url=yaml_url,
                error="Invalid pod discovery response",
            )
            continue

        async def rollback() -> None:
            await asyncio.gather(
                *(
                    client.post(
                        f"{base_url.rstrip('/')}/agents/models-catalog/refresh",
                        json={"source_id": source_id, "rollback_token": token},
                        headers=headers,
                        timeout=5.0,
                        follow_redirects=False,
                    )
                    for (base_url, _), token in zip(pods, preparation_tokens)
                ),
                return_exceptions=True,
            )

        next_revision = max(current_revision, *pod_revisions) + 1
        activated = await asyncio.gather(
            *(
                client.post(
                    f"{base_url.rstrip('/')}/agents/models-catalog/refresh",
                    json={
                        "source_id": source_id,
                        "preparation_token": token,
                        "revision": next_revision,
                    },
                    headers=headers,
                    timeout=5.0,
                    follow_redirects=False,
                )
                for (base_url, _), token in zip(pods, preparation_tokens)
            ),
            return_exceptions=True,
        )
        if any(
            isinstance(response, BaseException) or response.status_code != 200
            for response in activated
        ):
            await rollback()
            await store.record_failure(
                source_id=source_id,
                yaml_url=yaml_url,
                error="Discovery activation failed on a runtime pod",
            )
            continue
        try:
            for response, prepared_inventory in zip(activated, inventories):
                if isinstance(response, BaseException):
                    raise ValueError("Discovery activation failed")
                payload = response.json()
                if not isinstance(payload, dict) or set(
                    payload.get("discovered_model_ids", [])
                ) != set(prepared_inventory):
                    raise ValueError(
                        "Activated inventory differs from its prepared version"
                    )
        except (ValueError, TypeError):
            await rollback()
            await store.record_failure(
                source_id=source_id,
                yaml_url=yaml_url,
                error="Discovery activation returned a different inventory",
            )
            continue
        # A model is available only when every serving pod advertises it.
        common_ids = (
            set.intersection(*(set(inventory) for inventory in inventories))
            if inventories
            else set()
        )
        inventory = (
            [inventories[0][model_id] for model_id in sorted(common_ids)]
            if inventories
            else []
        )
        saved = await store.save_success(
            source_id=source_id,
            yaml_url=yaml_url,
            effective_url=effective_url,
            inventory=inventory,
            override_update=changing_url,
            override_url=proposed_override,
            expected_override_url=existing.override_url if existing else None,
            updated_by=user.uid if changing_url else None,
            expected_revision=current_revision,
            applied_revision=next_revision,
        )
        if saved is None:
            await rollback()
            await store.record_failure(
                source_id=source_id,
                yaml_url=yaml_url,
                error="Discovery URL changed during refresh",
            )
    result = await get_status(user, deps)
    result.pod_chat_default_available = pod_chat_default_available
    return result


async def get_model_detail(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    *,
    source_id: str,
    model_id: str,
    runtime_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    sources = [
        source
        for source in deps.configuration.platform.runtime_catalog_sources
        if source.enabled
    ]
    if runtime_id is not None:
        sources.sort(key=lambda source: source.runtime_id != runtime_id)
    if not sources:
        raise KeyError("Unknown runtime pod")
    headers = {"Authorization": authorization} if authorization else None
    client = deps.get_runtime_http_client()
    for source in sources:
        try:
            response = await client.get(
                f"{source.base_url.rstrip('/')}/agents/models-catalog/detail",
                params={"source_id": source_id, "model_id": model_id},
                headers=headers,
                timeout=5.0,
                follow_redirects=False,
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        except (httpx.HTTPError, ValueError):
            continue
    raise KeyError("Model detail is unavailable")
