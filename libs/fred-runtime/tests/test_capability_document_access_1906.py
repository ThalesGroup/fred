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
from fred_core.store.vector_search import DATASET_POINTER_CHUNK_KIND, VectorSearchHit
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


def _hit(uid: str, score: float = 1.0) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid, title=f"Doc {uid}", content="body", score=score, type="document"
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
        attachments_only: bool = False,
    ) -> DocumentSearchResult:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "library_tag_ids": library_tag_ids,
                "document_uids": document_uids,
                "search_policy": search_policy,
                "attachments_only": attachments_only,
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
# Computed chat controls (RFC §3.3) — legacy-parity stock set
# ---------------------------------------------------------------------------


def _widgets(controls) -> list[str]:
    return [c.widget for c in controls]


def test_chat_controls_default_to_the_full_legacy_parity_set() -> None:
    cap = DocumentAccessCapability()
    controls = cap.chat_controls(DocumentAccessConfig())
    assert _widgets(controls) == [
        "attach_files",
        "document_scope",
        "search_policy",
        "rag_scope",
    ]


def test_chat_control_document_scope_bound_to_config_libraries() -> None:
    # A pre-0.3 slice with a library scope and no bind flag stays binding
    # (upgrade validator), and binding pins the picker read-only.
    cap = DocumentAccessCapability()
    controls = cap.chat_controls(
        DocumentAccessConfig.model_validate({"library_tag_ids": ["A", "B"]})
    )
    scope = next(c for c in controls if c.widget == "document_scope")
    assert scope.params is not None
    params = scope.params.model_dump()
    assert params["bound_library_ids"] == ["A", "B"]
    # Bound → the libraries row shows (pinned) even without free selection.
    assert params["libraries"] is True


def test_bound_libraries_inert_while_binding_is_off() -> None:
    # The tree's value is kept but ignored when "Bind to specific libraries"
    # is off — same semantics as the legacy tool.
    cap = DocumentAccessCapability()
    config = DocumentAccessConfig.model_validate(
        {"bind_libraries": False, "library_tag_ids": ["A", "B"]}
    )
    scope = next(c for c in cap.chat_controls(config) if c.widget == "document_scope")
    assert scope.params is not None
    assert scope.params.model_dump()["bound_library_ids"] is None


def test_chat_controls_each_toggle_hides_its_widget() -> None:
    cap = DocumentAccessCapability()
    # Legacy single-toggle slices map onto the split library/document toggles.
    config = DocumentAccessConfig.model_validate({"show_document_scope_control": False})
    assert "document_scope" not in _widgets(cap.chat_controls(config))
    all_off = DocumentAccessConfig.model_validate(
        {
            "show_library_selection": False,
            "show_document_selection": False,
            "show_attach_files_control": False,
            "show_search_policy_control": False,
            "show_rag_scope_control": False,
        }
    )
    assert cap.chat_controls(all_off) == []


def test_chat_controls_config_values_become_picker_defaults() -> None:
    cap = DocumentAccessCapability()
    config = DocumentAccessConfig.model_validate(
        {"search_policy": "strict", "default_rag_scope": "corpus_only"}
    )
    controls = {c.widget: c for c in cap.chat_controls(config)}
    assert controls["search_policy"].params is not None
    assert controls["search_policy"].params.model_dump()["default"] == "strict"
    assert controls["rag_scope"].params is not None
    assert controls["rag_scope"].params.model_dump()["default"] == "corpus_only"


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


@pytest.mark.asyncio
async def test_search_policy_enforced_only_when_picker_hidden() -> None:
    """With the search-policy picker shown, the configured policy is only the
    picker's default (the port gets None and the per-turn RuntimeContext value
    wins in the adapter); with the picker hidden, it is enforced as-is."""

    cap = DocumentAccessCapability()

    port = _FakePort(hits=(_hit("d1"),))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={"search_policy": "strict", "show_search_policy_control": True},
    )
    await _invoke_tool(cap, ctx)
    assert port.calls[0]["search_policy"] is None

    port = _FakePort(hits=(_hit("d1"),))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={"search_policy": "strict", "show_search_policy_control": False},
    )
    await _invoke_tool(cap, ctx)
    assert port.calls[0]["search_policy"] == "strict"


@pytest.mark.asyncio
async def test_unbound_library_scope_not_applied_at_search_time() -> None:
    """With `bind_libraries` off, the stored tree selection is inert — the
    port must not receive it as a scope (legacy-tool semantics)."""

    cap = DocumentAccessCapability()
    port = _FakePort(hits=(_hit("d1"),))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={"bind_libraries": False, "library_tag_ids": ["A", "B"]},
    )
    await _invoke_tool(cap, ctx)
    assert port.calls[0]["library_tag_ids"] is None


@pytest.mark.asyncio
async def test_dataset_pointer_hit_excluded_from_sources_but_kept_for_the_model() -> (
    None
):
    """
    A dataset-pointer chunk (RAG-DATASET-DISCOVERY-RFC.md) carries no real
    content — the model must still see it to know to pivot to the tabular
    tool, but it must never be shown to the user as a citable source. Found
    live (2026-07-19): a SQL-derived answer was "citing" the pointer's raw
    anti-injection template text in the chat Sources panel.
    """
    pointer_hit = VectorSearchHit(
        uid="dataset-1",
        title="Some dataset",
        content="[DATASET POINTER — descriptive data ...]",
        score=0.5,
        type="csv",
        chunk_kind=DATASET_POINTER_CHUNK_KIND,
    )
    real_hit = _hit("d1")
    cap = DocumentAccessCapability()
    port = _FakePort(hits=(pointer_hit, real_hit))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={},
        turn_options={},
    )

    message = await _invoke_tool(cap, ctx)

    # The model still sees both hits — it needs the pointer to pivot.
    assert "DATASET POINTER" in message.content
    # Only the real content hit is citable as a source.
    assert [hit.uid for hit in message.artifact.sources] == ["d1"]


@pytest.mark.asyncio
async def test_low_relevance_hit_excluded_from_sources_by_default_score_ratio() -> None:
    """
    A real (non-pointer) hit that scores far below the best hit in the same
    call is noise relative to the strongest match, not a citable basis for
    the answer. Found live (2026-07-19): near-zero-relevance paragraphs from
    an unrelated document were cited as "sources" for a SQL-derived answer.
    """
    strong = _hit("d1", score=0.5)
    noise = _hit("d2", score=0.05)  # 10% of the top score — well under default 50%
    cap = DocumentAccessCapability()
    port = _FakePort(hits=(strong, noise))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={},
        turn_options={},
    )

    message = await _invoke_tool(cap, ctx)

    # The model still sees both hits.
    assert "d1" in message.content and "d2" in message.content
    # Only the strong hit clears the default 0.5 ratio.
    assert [hit.uid for hit in message.artifact.sources] == ["d1"]


@pytest.mark.asyncio
async def test_min_source_score_ratio_is_configurable_per_instance() -> None:
    """
    `min_source_score_ratio` is agent-creation config (a real `FieldSpec`), not
    a hardcoded constant — an operator who wants a more permissive Sources
    panel can lower it per instance.
    """
    strong = _hit("d1", score=0.5)
    noise = _hit("d2", score=0.05)
    cap = DocumentAccessCapability()
    port = _FakePort(hits=(strong, noise))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={"min_source_score_ratio": 0.01},
        turn_options={},
    )

    message = await _invoke_tool(cap, ctx)

    # A permissive ratio lets the previously-excluded hit through.
    assert {hit.uid for hit in message.artifact.sources} == {"d1", "d2"}


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
async def test_attachments_only_pins_search_to_the_session_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`search_attachments_only`: the capability forwards the flag through the
    port, and the adapter searches the session scope only (attached files),
    never the corpus — regardless of the turn's RAG scope default."""

    captured: dict[str, Any] = {}

    def _factory(*, agent: Any) -> _FakeVectorSearchClient:
        client = _FakeVectorSearchClient(agent=agent)
        captured["client"] = client
        return client

    monkeypatch.setattr(adapters_module, "VectorSearchClient", _factory)
    binding = _binding(session_id="s-1", search_rag_scope="hybrid")
    adapter = DocumentSearchAdapter(binding=binding, settings=_settings())

    cap = DocumentAccessCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=adapter),
        config={"search_attachments_only": True},
    )
    await _invoke_tool(cap, ctx)

    call = captured["client"].calls[0]
    assert call["include_session_scope"] is True
    assert call["include_corpus_scope"] is False

    # And the scope-picker chat control is dropped (scope is pinned).
    widgets = [
        c.widget
        for c in cap.chat_controls(DocumentAccessConfig(search_attachments_only=True))
    ]
    assert "document_scope" not in widgets
    assert "attach_files" in widgets

    # Inert without attachments: the flag must not strand an agent whose
    # attach button is disabled — the picker returns and the search is normal.
    no_attach = DocumentAccessConfig(
        search_attachments_only=True, show_attach_files_control=False
    )
    assert "document_scope" in [c.widget for c in cap.chat_controls(no_attach)]
    port = _FakePort(hits=(_hit("d1"),))
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=port),
        config={"search_attachments_only": True, "show_attach_files_control": False},
    )
    await _invoke_tool(cap, ctx)
    assert port.calls[0]["attachments_only"] is False


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
