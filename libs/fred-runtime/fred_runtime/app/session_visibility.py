# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Check managed owner history against authoritative product session metadata."""

import asyncio
from itertools import batched
from typing import TYPE_CHECKING
from urllib.parse import quote

import anyio
import httpx
from fastapi import HTTPException
from fred_core.conversation_trace import (
    TRACE_OWNER_VISIBILITY_BATCH,
    TraceOwnerVisibilityRequest,
)
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
        auth: M2MBearerAuth | None,
    ) -> None:
        self._client = client
        self._auth = auth
        base = str(config.platform.control_plane_url).rstrip("/")
        runtime = quote(config.app.runtime_id, safe="")
        self._url = (
            f"{base}/internal/runtimes/{runtime}/conversation-traces/owner-hidden"
        )

    async def _hidden_batch(
        self, user_id: str, session_ids: tuple[str, ...]
    ) -> list[str]:
        body = TraceOwnerVisibilityRequest(
            user_id=user_id, session_ids=list(session_ids)
        )
        response = await self._client.post(
            self._url,
            json=body.model_dump(mode="json"),
            auth=self._auth if self._auth is not None else httpx.USE_CLIENT_DEFAULT,
        )
        response.raise_for_status()
        return _SESSION_IDS.validate_json(response.content)

    async def hidden(self, user_id: str, session_ids: list[str]) -> set[str]:
        hidden: set[str] = set()
        try:
            with anyio.fail_after(2):
                batches = batched(session_ids, TRACE_OWNER_VISIBILITY_BATCH)
                for window in batched(batches, _PARALLEL_BATCHES):
                    results = await asyncio.gather(
                        *(self._hidden_batch(user_id, batch) for batch in window),
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
    container: "PodApplicationContext", user_id: str, session_ids: list[str]
) -> set[str]:
    if not session_ids:
        return set()
    visibility = container.owner_session_visibility
    if visibility is None:
        raise HTTPException(503, "conversation_visibility_unavailable")
    return await visibility.hidden(user_id, session_ids)


async def owner_hidden_sessions(
    container: "PodApplicationContext", user_id: str | None, session_ids: list[str]
) -> set[str]:
    """Guard owner surfaces without an ordinary history query to reuse."""
    store = container.get_history_store()
    if (
        not isinstance(store, PostgresHistoryStore)
        or user_id is None
        or not session_ids
    ):
        return set()
    managed: list[str] = []
    for batch in batched(session_ids, TRACE_OWNER_VISIBILITY_BATCH):
        managed.extend(await store.managed_sessions(user_id, list(batch)))
    return await hidden_managed_sessions(container, user_id, managed)
