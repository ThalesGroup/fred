from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

import httpx
from fred_core import Action, KeycloakUser, Resource, authorize
from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
)

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.features.users.users_structures import UserSummary

logger = logging.getLogger(__name__)

_token_provider: M2MTokenProvider | None = None


def _make_cp_client() -> httpx.AsyncClient | None:
    cfg = get_configuration()
    base_url = cfg.app.control_plane_base_url
    if not base_url:
        return None
    m2m = cfg.security.m2m
    if not m2m.enabled:
        return httpx.AsyncClient(base_url=base_url, timeout=10.0)
    global _token_provider
    if _token_provider is None:
        _token_provider = M2MTokenProvider(
            M2MAuthConfig(
                keycloak_realm_url=str(m2m.realm_url),
                client_id=m2m.client_id,
                secret_env=m2m.secret_env_var,
            )
        )
    return httpx.AsyncClient(
        base_url=base_url,
        auth=M2MBearerAuth(_token_provider),
        timeout=10.0,
    )


def _parse_user(data: dict) -> UserSummary:
    return UserSummary(
        id=data["id"],
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
    )


@authorize(Action.READ, Resource.USER)
async def list_users(_current_user: KeycloakUser) -> list[UserSummary]:
    client = _make_cp_client()
    if client is None:
        logger.info("Control plane not configured; returning empty user list.")
        return []
    async with client:
        response = await client.get("/users")
    response.raise_for_status()
    return [_parse_user(u) for u in response.json()]


async def get_users_by_ids(user_ids: Iterable[str]) -> dict[str, UserSummary]:
    unique_ids = {uid for uid in user_ids if uid}
    if not unique_ids:
        return {}

    client = _make_cp_client()
    if client is None:
        logger.info("Control plane not configured; returning fallback users.")
        return {uid: UserSummary(id=uid) for uid in unique_ids}

    async def _fetch_one(uid: str) -> tuple[str, UserSummary]:
        r = await client.get(f"/users/{uid}")
        if r.status_code == 404:
            return uid, UserSummary(id=uid)
        r.raise_for_status()
        return uid, _parse_user(r.json())

    async with client:
        results = await asyncio.gather(*[_fetch_one(uid) for uid in unique_ids], return_exceptions=True)

    summaries: dict[str, UserSummary] = {}
    for uid, result in zip(unique_ids, results):
        if isinstance(result, BaseException):
            logger.warning("Failed to fetch user %s from control plane: %s", uid, result)
            summaries[uid] = UserSummary(id=uid)
        else:
            k, v = result
            summaries[k] = v
    return summaries
