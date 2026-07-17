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
`DocumentAccessCapability` — the #1906 pilot (CAPAB-01, RFC §3, §10).

Covers the runtime half of the pilot:
- registration through the `fred.capabilities` entry point + boot validation,
  and the double-registration boot invariant;
- the computed `document_scope` chat control;
- scoping precedence `turn_option ⊆ capability_config ⊆ session_binding`, split
  across the two seams and proven end-to-end through the REAL
  `DocumentSearchAdapter`;
- the port/adapter privacy contract (token + binding stay private, scope params
  only);
- "multiple tools from one capability" via assembly (a fake capability — no
  mock tools shipped by the pilot).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from importlib.metadata import EntryPoint
from types import SimpleNamespace
from typing import Any

import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.capabilities import (
    CapabilityRegistry,
    DuplicateCapabilityIdError,
    build_capability_agent_block,
    build_capability_context,
)
from fred_runtime.capabilities.document_access import (
    DOCUMENT_ACCESS_TOOL_REF,
    DocumentAccessCapability,
    DocumentAccessConfig,
    narrow_scope_ids,
)
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_runtime.integrations.v2_runtime import adapters as adapters_module
from fred_runtime.integrations.v2_runtime.adapters import DocumentSearchAdapter
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    DocumentSearchPort,
    DocumentSearchResult,
    RuntimeServices,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import tool
from pydantic import BaseModel

_ENTRY_POINT_VALUE = (
    "fred_runtime.capabilities.document_access:DocumentAccessCapability"
)


def _hit(uid: str) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid, title=f"Doc {uid}", content="body", score=1.0, type="document"
    )


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakePort(DocumentSearchPort):
    """Fake `DocumentSearchPort` recording the scope params it received."""

    def __init__(self, hits: Sequence[VectorSearchHit] = ()) -> None:
        self.calls: list[dict[str, Any]] = []
        self._hits = tuple(hits)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        library_tag_ids=None,
        document_uids=None,
        search_policy=None,
    ) -> DocumentSearchResult:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "library_tag_ids": library_tag_ids,
                "document_uids": document_uids,
                "search_policy": search_policy,
            }
        )
        return DocumentSearchResult(hits=self._hits)


class _FakeVectorSearchClient:
    """Stand-in for `VectorSearchClient`, capturing the private shim + call."""

    def __init__(self, *, agent: Any) -> None:
        self.agent = agent
        self.calls: list[dict[str, Any]] = []

    async def search(self, **kwargs: Any) -> list[VectorSearchHit]:
        self.calls.append(kwargs)
        return [_hit("d1")]


def _settings(team_id: str | None = None) -> Any:
    return SimpleNamespace(
        id="agent.doc",
        team_id=team_id,
        tuning=None,
        active_mcp_servers=(),
    )


def _binding(**runtime_fields: Any) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(**runtime_fields),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


async def _invoke_tool(cap: DocumentAccessCapability, ctx: CapabilityContext[Any, Any]):
    middleware = cap.middleware(ctx)
    assert len(middleware) == 1
    tools = list(middleware[0].tools)  # type: ignore[attr-defined]
    assert len(tools) == 1
    the_tool = tools[0]
    assert the_tool.name == "search_documents_using_vectorization"
    return await the_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_documents_using_vectorization",
            "args": {"question": "what is fred?"},
            "id": "call-1",
        }
    )


# ---------------------------------------------------------------------------
# Registration + boot invariant
# ---------------------------------------------------------------------------


def test_capability_registers_via_entry_point_and_boots() -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name="document_access",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )
    registered = registry.discover(entry_points=[entry])

    assert registered == ["document_access"]
    assert isinstance(registry.capability("document_access"), DocumentAccessCapability)
    # Boot validation must pass (default_on with no required team settings, no
    # owned tables, no chat-part collisions) — the boot invariant.
    registry.validate(env={})


def test_double_registration_trips_boot_invariant() -> None:
    registry = CapabilityRegistry()
    registry.register(DocumentAccessCapability())
    with pytest.raises(DuplicateCapabilityIdError):
        registry.register(DocumentAccessCapability())


# ---------------------------------------------------------------------------
# Computed chat control (RFC §3.3)
# ---------------------------------------------------------------------------


def test_chat_control_document_scope_bound_to_config_libraries() -> None:
    cap = DocumentAccessCapability()
    controls = cap.chat_controls(
        DocumentAccessConfig.model_validate({"library_tag_ids": ["A", "B"]})
    )
    assert len(controls) == 1
    assert controls[0].widget == "document_scope"
    params = controls[0].params
    assert params is not None
    assert params.model_dump()["bound_library_ids"] == ["A", "B"]


def test_chat_control_hidden_when_disabled() -> None:
    cap = DocumentAccessCapability()
    config = DocumentAccessConfig.model_validate({"show_document_scope_control": False})
    assert cap.chat_controls(config) == []


# ---------------------------------------------------------------------------
# Scope precedence — capability seam (turn_option ⊆ capability_config)
# ---------------------------------------------------------------------------


def test_narrow_scope_ids_primitive() -> None:
    # inner empty → inherit outer
    assert narrow_scope_ids(["A", "B"], None) == ["A", "B"]
    # outer empty (unbounded) → keep inner
    assert narrow_scope_ids(None, ["A"]) == ["A"]
    # both present → intersection, order of inner preserved
    assert narrow_scope_ids(["A", "B", "C"], ["C", "A", "Z"]) == ["C", "A"]


@pytest.mark.asyncio
async def test_turn_option_bounded_by_capability_config() -> None:
    cap = DocumentAccessCapability()
    port = _FakePort(hits=(_hit("d1"),))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={"library_tag_ids": ["A", "B", "X"], "document_uids": ["u1", "u2"]},
        turn_options={"library_tag_ids": ["A", "X", "Z"]},
    )

    message = await _invoke_tool(cap, ctx)

    # turn ∩ config: Z dropped (not in config); order follows the turn list.
    assert port.calls[0]["library_tag_ids"] == ["A", "X"]
    # turn omits document_uids → inherit the config scope unchanged.
    assert port.calls[0]["document_uids"] == ["u1", "u2"]
    # sources ride the tool artifact for the chat Sources panel.
    assert message.artifact.tool_ref == DOCUMENT_ACCESS_TOOL_REF
    assert message.artifact.sources[0].uid == "d1"


# ---------------------------------------------------------------------------
# Scope precedence — full chain through the REAL adapter
# (turn_option ⊆ capability_config ⊆ session_binding)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoping_precedence_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, _FakeVectorSearchClient] = {}

    def _factory(*, agent: Any) -> _FakeVectorSearchClient:
        client = _FakeVectorSearchClient(agent=agent)
        captured["client"] = client
        return client

    monkeypatch.setattr(adapters_module, "VectorSearchClient", _factory)

    binding = _binding(
        session_id="s-1",
        access_token="secret-token",  # nosec B106 - test fixture
        selected_document_libraries_ids=["A", "B", "C"],
        selected_document_uids=["u1", "u2"],
        search_rag_scope="hybrid",
    )
    adapter = DocumentSearchAdapter(binding=binding, settings=_settings())

    cap = DocumentAccessCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=adapter),
        config={
            "library_tag_ids": ["A", "B", "X"],
            "document_uids": ["u1", "u2", "u3"],
        },
        turn_options={"library_tag_ids": ["A", "X"]},
    )

    await _invoke_tool(cap, ctx)

    call = captured["client"].calls[0]
    # libraries: turn∩config = [A,X]; then ∩session[A,B,C] = [A].
    assert call["document_library_tags_ids"] == ["A"]
    # documents: turn omits → config[u1,u2,u3]; then ∩session[u1,u2] = [u1,u2].
    assert call["document_uids"] == ["u1", "u2"]


@pytest.mark.asyncio
async def test_general_only_scope_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def _factory(*, agent: Any) -> _FakeVectorSearchClient:
        client = _FakeVectorSearchClient(agent=agent)
        calls.append(client)
        return client

    monkeypatch.setattr(adapters_module, "VectorSearchClient", _factory)
    binding = _binding(search_rag_scope="general_only")
    adapter = DocumentSearchAdapter(binding=binding, settings=_settings())

    result = await adapter.search("q", library_tag_ids=["A"])
    assert result.hits == ()
    assert calls[0].calls == []  # no backend call in general-only mode


# ---------------------------------------------------------------------------
# Privacy contract — token + binding never reach the capability
# ---------------------------------------------------------------------------


def test_adapter_keeps_binding_and_token_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _factory(*, agent: Any) -> _FakeVectorSearchClient:
        return _FakeVectorSearchClient(agent=agent)

    monkeypatch.setattr(adapters_module, "VectorSearchClient", _factory)
    binding = _binding(access_token="secret-token")  # nosec B106 - test fixture
    adapter = DocumentSearchAdapter(binding=binding, settings=_settings())

    # No PUBLIC attribute exposes the binding/token/client — all private.
    public = [name for name in vars(adapter) if not name.startswith("_")]
    assert public == []

    # The token reaches Knowledge Flow ONLY through the private shim, never a
    # port parameter (the shim carries the runtime_context that holds it).
    services = RuntimeServices(document_search=adapter)
    ctx = build_capability_context(
        DocumentAccessCapability(),
        identity=_identity(),
        services=services,
        config={},
    )
    field_names = {f.name for f in dataclasses.fields(ctx)}
    assert "token" not in field_names and "binding" not in field_names
    assert not hasattr(ctx.services, "access_token")
    assert "secret-token" not in repr(ctx.services)


# ---------------------------------------------------------------------------
# Multiple tools from one capability — proven via assembly (RFC §10)
# ---------------------------------------------------------------------------


class _TwoToolConfig(BaseModel):
    pass


class _TwoToolMiddleware(AgentMiddleware):
    def __init__(self) -> None:
        super().__init__()

        @tool
        def alpha_tool(x: str) -> str:
            """First tool."""
            return x

        @tool
        def beta_tool(y: str) -> str:
            """Second tool."""
            return y

        self.tools = [alpha_tool, beta_tool]


class _TwoToolCapability(AgentCapability[_TwoToolConfig, _TwoToolConfig, EmptyModel]):
    manifest = CapabilityManifest(
        id="two_tool_probe",
        version="1.0.0",
        name="cap.two_tool.name",
        description="cap.two_tool.description",
        icon="extension",
    )
    ConfigModel = _TwoToolConfig

    def middleware(
        self, ctx: CapabilityContext[_TwoToolConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_TwoToolMiddleware()]


def test_multiple_tools_from_one_capability_assemble() -> None:
    registry = CapabilityRegistry()
    registry.register(_TwoToolCapability())
    ctx = build_capability_context(
        registry.capability("two_tool_probe"),
        identity=_identity(),
        services=RuntimeServices(),
        config={},
    )
    block = build_capability_agent_block(registry, {"two_tool_probe": ctx})

    tool_names = {
        getattr(t, "name", None)
        for mw in block.middleware
        for t in (getattr(mw, "tools", None) or [])
    }
    assert {"alpha_tool", "beta_tool"} <= tool_names
