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
`DocumentLabelSearchCapability` — kept deliberately separate from
`document_access`, see the capability module docstring for why. Covers:
registration, the admin-gated `team_scope` default, tool behavior, and the
real `DocumentTreeAdapter.list_by_label` param forwarding.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

import pytest
from fred_runtime.capabilities import (
    CapabilityRegistry,
    DuplicateCapabilityIdError,
    build_capability_context,
)
from fred_runtime.capabilities.document_label_search import (
    DocumentLabelSearchCapability,
)
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_sdk.contracts.capability import CapabilityContext, CapabilityIdentity
from fred_sdk.contracts.models import TeamScopePolicy
from fred_sdk.contracts.runtime import (
    DocumentLabelPageResult,
    DocumentLabelReference,
    DocumentPortCallError,
    DocumentTreePort,
    DocumentTreeResult,
    RuntimeServices,
)

_ENTRY_POINT_VALUE = (
    "fred_runtime.capabilities.document_label_search:DocumentLabelSearchCapability"
)


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)


class _FakeTreePort(DocumentTreePort):
    """Fake `DocumentTreePort` recording the label-page params it received.
    Only `list_by_label` is exercised by this capability; `tree()` is
    implemented solely to satisfy the ABC."""

    def __init__(
        self,
        result: DocumentLabelPageResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result or DocumentLabelPageResult(
            label="", total=0, offset=0, limit=50, has_more=False
        )
        self._error = error

    async def tree(self, **kwargs: Any) -> DocumentTreeResult:
        raise NotImplementedError("tree() is not used by document_label_search")

    async def list_by_label(
        self,
        *,
        label: str,
        offset: int = 0,
        limit: int = 50,
    ) -> DocumentLabelPageResult:
        self.calls.append({"label": label, "offset": offset, "limit": limit})
        if self._error is not None:
            raise self._error
        return self._result


def _services(tree: _FakeTreePort | None = None) -> RuntimeServices:
    return RuntimeServices(document_tree=tree or _FakeTreePort())


def _capability_tools(
    cap: DocumentLabelSearchCapability, ctx: CapabilityContext[Any, Any]
) -> dict[str, Any]:
    middleware = cap.middleware(ctx)
    assert len(middleware) == 1
    return {t.name: t for t in middleware[0].tools}  # type: ignore[attr-defined]


async def _invoke_named_tool(
    cap: DocumentLabelSearchCapability,
    ctx: CapabilityContext[Any, Any],
    name: str,
    args: dict[str, Any],
):
    the_tool = _capability_tools(cap, ctx)[name]
    return await the_tool.ainvoke(
        {"type": "tool_call", "name": name, "args": args, "id": "call-1"}
    )


# ---------------------------------------------------------------------------
# Registration + boot invariant
# ---------------------------------------------------------------------------


def test_capability_registers_via_entry_point_and_boots() -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name="document_label_search",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )
    registered = registry.discover(entry_points=[entry])

    assert registered == ["document_label_search"]
    assert isinstance(
        registry.capability("document_label_search"), DocumentLabelSearchCapability
    )
    registry.validate(env={})


def test_double_registration_trips_boot_invariant() -> None:
    registry = CapabilityRegistry()
    registry.register(DocumentLabelSearchCapability())
    with pytest.raises(DuplicateCapabilityIdError):
        registry.register(DocumentLabelSearchCapability())


def test_team_scope_defaults_to_admin_gated() -> None:
    """Unlike document_access (opts into DEFAULT_ON), this capability has no
    query-shaped signal to gate invocation on — a team admin must explicitly
    enable it, per team, before any agent can even select it. That is the
    whole point of the split from document_access: zero blast radius on the
    already-shipped baseline tool set."""

    assert DocumentLabelSearchCapability.manifest.team_scope == (
        TeamScopePolicy.ADMIN_GATED
    )


# ---------------------------------------------------------------------------
# Tool behavior
# ---------------------------------------------------------------------------


def test_tool_registered_by_default() -> None:
    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(), config={}
    )
    assert set(_capability_tools(cap, ctx)) == {"list_documents_by_label"}


@pytest.mark.asyncio
async def test_label_tool_forwards_label_offset_and_limit_to_the_port() -> None:
    tree_port = _FakeTreePort(
        result=DocumentLabelPageResult(
            label="DAT",
            documents=(
                DocumentLabelReference(document_uid="doc-1", document_name="a.pdf"),
            ),
            total=1,
            offset=10,
            limit=25,
            has_more=False,
        )
    )
    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(tree_port), config={}
    )

    message = await _invoke_named_tool(
        cap, ctx, "list_documents_by_label", {"label": "DAT", "offset": 10, "limit": 25}
    )

    assert tree_port.calls[0] == {"label": "DAT", "offset": 10, "limit": 25}
    assert "a.pdf [doc-1]" in message.content
    assert message.artifact.tool_ref == "list_documents_by_label"
    assert message.artifact.blocks[0].text == message.content


@pytest.mark.asyncio
async def test_label_tool_clamps_limit_and_floors_a_negative_offset() -> None:
    tree_port = _FakeTreePort(
        result=DocumentLabelPageResult(
            label="DAT", total=0, offset=0, limit=500, has_more=False
        )
    )
    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(tree_port), config={}
    )

    await _invoke_named_tool(
        cap,
        ctx,
        "list_documents_by_label",
        {"label": "DAT", "offset": -5, "limit": 10_000},
    )

    assert tree_port.calls[0] == {"label": "DAT", "offset": 0, "limit": 500}


@pytest.mark.asyncio
async def test_label_tool_tells_the_model_to_continue_when_more_pages_remain() -> None:
    tree_port = _FakeTreePort(
        result=DocumentLabelPageResult(
            label="DAT",
            documents=(
                DocumentLabelReference(document_uid="doc-1", document_name="a.pdf"),
            ),
            total=5,
            offset=0,
            limit=1,
            next_offset=1,
            has_more=True,
        )
    )
    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(tree_port), config={}
    )

    message = await _invoke_named_tool(
        cap, ctx, "list_documents_by_label", {"label": "DAT"}
    )

    assert "offset=1" in message.content
    assert "total=5" in message.content


@pytest.mark.asyncio
async def test_label_tool_reports_no_documents_found_for_an_empty_match() -> None:
    tree_port = _FakeTreePort(
        result=DocumentLabelPageResult(
            label="NOPE", total=0, offset=0, limit=50, has_more=False
        )
    )
    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(tree_port), config={}
    )

    message = await _invoke_named_tool(
        cap, ctx, "list_documents_by_label", {"label": "NOPE"}
    )

    assert "No documents found" in message.content
    assert "NOPE" in message.content


@pytest.mark.asyncio
async def test_label_tool_failure_returns_is_error_result() -> None:
    tree_port = _FakeTreePort(
        error=DocumentPortCallError("upstream boom", status_code=503)
    )
    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(tree_port), config={}
    )

    message = await _invoke_named_tool(
        cap, ctx, "list_documents_by_label", {"label": "DAT"}
    )

    assert message.artifact.is_error is True
    assert "HTTP 503" in message.content
    assert "list documents by label" in message.content


@pytest.mark.asyncio
async def test_missing_document_tree_port_fails_loud() -> None:
    """A missing platform port is a wiring bug, not an empty result."""

    cap = DocumentLabelSearchCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=RuntimeServices(), config={}
    )

    with pytest.raises(RuntimeError, match="document_tree"):
        await _invoke_named_tool(cap, ctx, "list_documents_by_label", {"label": "DAT"})


# ---------------------------------------------------------------------------
# Real adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_label_adapter_forwards_params_and_maps_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The REAL `DocumentTreeAdapter.list_by_label`: unlike `tree()`, no
    session-binding/team narrowing is applied (documented gap — Knowledge
    Flow's label resolution has none to apply to) — this test locks the
    param forwarding and wire-to-SDK-model mapping, not a scoping seam."""

    from types import SimpleNamespace

    from fred_runtime.integrations.v2_runtime import adapters as adapters_module
    from fred_sdk.contracts.context import (
        BoundRuntimeContext,
        PortableContext,
        PortableEnvironment,
        RuntimeContext,
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

    def _settings(team_id: str | None = None) -> Any:
        return SimpleNamespace(
            id="agent.doc",
            team_id=team_id,
            tuning=None,
            active_mcp_servers=(),
        )

    class _FakeDocumentClient:
        def __init__(self, *, agent: Any) -> None:
            self.agent = agent
            self.calls: list[dict[str, Any]] = []
            captured["client"] = self

        async def list_by_label(self, **kwargs: Any):
            self.calls.append(kwargs)
            return SimpleNamespace(
                label="DAT",
                documents=[
                    SimpleNamespace(document_uid="doc-1", document_name="a.pdf")
                ],
                total=1,
                offset=0,
                limit=50,
                next_offset=None,
                has_more=False,
            )

    captured: dict[str, Any] = {}
    monkeypatch.setattr(adapters_module, "KfDocumentClient", _FakeDocumentClient)

    binding = _binding(session_id="s-1", selected_document_libraries_ids=["A"])
    adapter = adapters_module.DocumentTreeAdapter(
        binding=binding, settings=_settings(team_id="team-9")
    )

    result = await adapter.list_by_label(label="DAT", offset=0, limit=50)

    assert captured["client"].calls[0] == {"label": "DAT", "offset": 0, "limit": 50}
    assert result.label == "DAT"
    assert result.documents == (
        DocumentLabelReference(document_uid="doc-1", document_name="a.pdf"),
    )
    assert result.total == 1
    assert result.has_more is False
