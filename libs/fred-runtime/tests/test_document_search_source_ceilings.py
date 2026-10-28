# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Corpus search sends the turn's space to Knowledge Flow and refuses unsupported sources."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from fred_runtime.integrations.v2_runtime import adapters as adapters_module
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import DocumentPortCallError, DocumentScopeRefusedError
from weaver_fixtures import resolved_binding


class _Settings:
    id: str = "agent-1"
    team_id: str | None = None
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    async def search(self, **kwargs: Any) -> list[Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return []


def _adapter(
    client: _Client, monkeypatch: pytest.MonkeyPatch, **fields: Any
) -> tuple[adapters_module.DocumentSearchAdapter, TurnAuthority]:
    monkeypatch.setattr(adapters_module, "VectorSearchClient", lambda **_kw: client)
    binding = resolved_binding()
    authority = TurnAuthority(binding, None)
    context = RuntimeContext(
        user_id=binding.subject_id,
        session_id=binding.conversation_id,
        space_id=str(binding.space.id),
        agent_instance_id=str(binding.agent.instance_id),
        **fields,
    )
    bound = BoundRuntimeContext(
        runtime_context=context,
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor=binding.subject_id,
            tenant=str(binding.space.id),
            environment=PortableEnvironment.DEV,
        ),
    )
    return adapters_module.DocumentSearchAdapter(
        binding=bound, settings=_Settings()
    ), authority


@pytest.mark.asyncio
@pytest.mark.parametrize("rag_scope", ["hybrid", "corpus_only", "general_only"])
@pytest.mark.parametrize("corpus_enabled", [True, False])
async def test_sources_bound_the_turn_scope(
    rag_scope: str, corpus_enabled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _Client()
    adapter, authority = _adapter(client, monkeypatch, search_rag_scope=rag_scope)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        result = await adapter.search(
            "q", include_attachments=False, include_team_documents=corpus_enabled
        )
    assert result.hits == ()
    if rag_scope == "general_only" or not corpus_enabled:
        assert client.calls == []
    else:
        assert client.calls[0]["space_id"] == str(authority.binding.space.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "restriction",
    [
        {"include_attachments": True},
        {"library_tag_ids": ["library"]},
        {"document_uids": ["document"]},
    ],
)
async def test_unsupported_scope_is_refused(
    restriction: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _Client()
    adapter, authority = _adapter(client, monkeypatch)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        with pytest.raises(DocumentScopeRefusedError):
            await adapter.search("q", **{"include_attachments": False, **restriction})
    assert client.calls == []


@pytest.mark.asyncio
async def test_empty_scope_does_not_search(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    adapter, authority = _adapter(client, monkeypatch)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        assert (
            await adapter.search("q", include_attachments=False, document_uids=[])
        ).hits == ()
    assert client.calls == []


@pytest.mark.asyncio
async def test_closed_or_missing_turn_cannot_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client()
    adapter, authority = _adapter(client, monkeypatch)
    with pytest.raises(AuthorityLostError):
        await adapter.search("q", include_attachments=False)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        authority.close()
        with pytest.raises(AuthorityLostError):
            await adapter.search("q", include_attachments=False)
    assert client.calls == []


@pytest.mark.asyncio
async def test_failure_is_not_an_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, authority = _adapter(_Client(httpx.ReadTimeout("timed out")), monkeypatch)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        with pytest.raises(DocumentPortCallError) as exc:
            await adapter.search("q", include_attachments=False)
    assert exc.value.timed_out
