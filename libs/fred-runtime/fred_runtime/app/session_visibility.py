# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Check managed owner history against authoritative product session metadata."""

import asyncio
from itertools import batched
from typing import TYPE_CHECKING

import anyio
import httpx
from fastapi import HTTPException
from fred_core import AssertedUser
from fred_core.history.history_schema import OWNER_VISIBILITY_BATCH
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
)
from fred_pod.security.oidc_endpoints import resolve_endpoints
from pydantic import TypeAdapter, ValidationError

if TYPE_CHECKING:
    from fred_runtime.app.config import AgentPodConfig
    from fred_runtime.app.context import PodApplicationContext

_SESSION_IDS = TypeAdapter(list[str])
_PARALLEL_BATCHES = 4


def runtime_workload_auth(config: "AgentPodConfig") -> M2MBearerAuth | None:
    m2m = config.security.m2m
    if not m2m.enabled:
        return None
    realm = str(m2m.realm_url).rstrip("/")
    endpoint = resolve_endpoints(
        provider=m2m.provider,
        realm_url=realm,
        token_url=str(m2m.token_url) if m2m.token_url else None,
    ).token_endpoint
    return M2MBearerAuth(
        M2MTokenProvider(
            M2MAuthConfig(
                keycloak_realm_url=realm,
                client_id=m2m.client_id,
                scope=m2m.scope,
                token_url_override=endpoint,
                secret_env=m2m.secret_env_var,
            )
        )
    )


class OwnerSessionVisibility:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: "AgentPodConfig",
    ) -> None:
        self._client = client
        self._runtime_id = config.app.runtime_id
        base = str(config.platform.control_plane_url).rstrip("/")
        self._url = f"{base}/internal/sessions/owner-hidden"

    async def _hidden_batch(
        self,
        authorization: str | None,
        session_ids: tuple[str, ...],
        subject: AssertedUser | None,
        *,
        erasing_only: bool,
    ) -> list[str]:
        params = (
            {"person": subject.uid, "run": subject.run_id, "agent": subject.agent_id}
            if subject is not None
            else {}
        )
        if erasing_only:
            params["erasing_only"] = "true"
            params["runtime_id"] = self._runtime_id
        response = await self._client.post(
            self._url,
            json=list(session_ids),
            headers={"Authorization": authorization} if authorization else None,
            params=params,
            follow_redirects=False,
        )
        response.raise_for_status()
        return _SESSION_IDS.validate_json(response.content)

    async def hidden(
        self,
        authorization: str | None,
        session_ids: list[str],
        subject: AssertedUser | None = None,
        *,
        erasing_only: bool = False,
    ) -> set[str]:
        hidden: set[str] = set()
        try:
            with anyio.fail_after(2):
                batches = batched(session_ids, OWNER_VISIBILITY_BATCH)
                for window in batched(batches, _PARALLEL_BATCHES):
                    results = await asyncio.gather(
                        *(
                            self._hidden_batch(
                                authorization, batch, subject, erasing_only=erasing_only
                            )
                            for batch in window
                        ),
                        return_exceptions=True,
                    )
                    for result in results:
                        if isinstance(result, BaseException):
                            raise result
                        hidden.update(result)
        except (httpx.HTTPError, TimeoutError, ValidationError) as exc:
            raise HTTPException(503, "conversation_visibility_unavailable") from exc
        return hidden


async def hidden_managed_sessions(
    container: "PodApplicationContext",
    authorization: str | None,
    session_ids: list[str],
    *,
    subject: AssertedUser | None = None,
    erasing_only: bool = False,
) -> set[str]:
    if not session_ids:
        return set()
    visibility = container.owner_session_visibility
    if visibility is None:
        raise HTTPException(503, "conversation_visibility_unavailable")
    if erasing_only:
        return await visibility.hidden(
            authorization, session_ids, subject, erasing_only=True
        )
    return await visibility.hidden(authorization, session_ids, subject)


async def owner_hidden_sessions(
    container: "PodApplicationContext",
    user_id: str | None,
    authorization: str | None,
    session_ids: list[str],
    *,
    subject: AssertedUser | None = None,
) -> set[str]:
    """Guard owner surfaces without an ordinary history query to reuse."""
    store = container.get_history_store()
    if not isinstance(store, PostgresHistoryStore) or not session_ids:
        return set()
    managed: list[str] = []
    for batch in batched(session_ids, OWNER_VISIBILITY_BATCH):
        managed.extend(await store.managed_sessions(user_id, list(batch)))
    return await hidden_managed_sessions(
        container, authorization, managed, subject=subject
    )
