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
Document-reading pair (DOCREAD-01): `DocumentVerbatimCapability` (verbatim
paginated read) and `DocumentExtractCapability` (exhaustive extraction), both on
the shared `DocumentMarkdownPort`. Covers: registration + boot invariant, the
admin-gated `team_scope` default, the pure pagination contract, the per-page
continuation footer that structurally prevents the summarize "half answer"
failure, the config page cap (default + hard bound), a missing-port loud failure,
and transport-error shaping.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

import pytest
from fred_runtime.capabilities import (
    CapabilityRegistry,
    build_capability_context,
)
from fred_runtime.capabilities.document_extract import DocumentExtractCapability
from fred_runtime.capabilities.document_read_common import (
    DEFAULT_PAGE_MAX_CHARS,
    DocumentReadConfig,
    resolve_page_max_chars,
)
from fred_runtime.capabilities.document_verbatim import DocumentVerbatimCapability
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_runtime.integrations.v2_runtime.adapters import paginate_markdown
from fred_sdk.contracts.capability import CapabilityContext, CapabilityIdentity
from fred_sdk.contracts.models import TeamScopePolicy
from fred_sdk.contracts.runtime import (
    DocumentMarkdownPort,
    DocumentMarkdownResult,
    DocumentPortCallError,
    RuntimeServices,
)

_VERBATIM_EP = "fred_runtime.capabilities.document_verbatim:DocumentVerbatimCapability"
_EXTRACT_EP = "fred_runtime.capabilities.document_extract:DocumentExtractCapability"


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)


class _FakeMarkdownPort(DocumentMarkdownPort):
    """Fake port slicing a fixed document via the real pagination helper, so the
    tool's footer formatting is exercised against realistic `next_offset`s."""

    def __init__(self, full: str = "", error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._full = full
        self._error = error

    async def fetch_markdown(
        self, document_uid: str, *, offset: int = 0, max_chars: int = 8000
    ) -> DocumentMarkdownResult:
        self.calls.append(
            {"document_uid": document_uid, "offset": offset, "max_chars": max_chars}
        )
        if self._error is not None:
            raise self._error
        return paginate_markdown(
            document_uid=document_uid,
            full=self._full,
            offset=offset,
            max_chars=max_chars,
        )


def _services(port: _FakeMarkdownPort | None = None) -> RuntimeServices:
    return RuntimeServices(document_markdown=port or _FakeMarkdownPort())


def _tools(cap: Any, ctx: CapabilityContext[Any, Any]) -> dict[str, Any]:
    middleware = cap.middleware(ctx)
    assert len(middleware) == 1
    return {t.name: t for t in middleware[0].tools}  # type: ignore[attr-defined]


async def _invoke(cap: Any, ctx: Any, name: str, args: dict[str, Any]):
    the_tool = _tools(cap, ctx)[name]
    return await the_tool.ainvoke(
        {"type": "tool_call", "name": name, "args": args, "id": "call-1"}
    )


# ---------------------------------------------------------------------------
# Pure pagination contract
# ---------------------------------------------------------------------------


def test_paginate_markdown_pages_and_signals_end() -> None:
    first = paginate_markdown(document_uid="d", full="abcdef", offset=0, max_chars=4)
    assert (first.text, first.offset, first.next_offset, first.total_chars) == (
        "abcd",
        0,
        4,
        6,
    )
    last = paginate_markdown(document_uid="d", full="abcdef", offset=4, max_chars=4)
    assert (last.text, last.next_offset) == ("ef", None)


def test_paginate_markdown_clamps_bounds() -> None:
    # Negative offset starts at 0.
    assert (
        paginate_markdown(document_uid="d", full="abc", offset=-5, max_chars=2).offset
        == 0
    )
    # Offset past the end yields an empty final page, never an exception.
    past = paginate_markdown(document_uid="d", full="abc", offset=99, max_chars=2)
    assert (past.text, past.offset, past.next_offset) == ("", 3, None)
    # Non-positive max_chars falls back to the default (whole short doc fits).
    dflt = paginate_markdown(document_uid="d", full="abc", offset=0, max_chars=0)
    assert dflt.text == "abc" and dflt.next_offset is None


# ---------------------------------------------------------------------------
# Registration + boot invariant + team scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cap_id", "ep_value", "cap_cls"),
    [
        ("document_verbatim", _VERBATIM_EP, DocumentVerbatimCapability),
        ("document_extract", _EXTRACT_EP, DocumentExtractCapability),
    ],
)
def test_registers_via_entry_point_and_boots(cap_id, ep_value, cap_cls) -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name=cap_id, value=ep_value, group=FRED_CAPABILITIES_ENTRY_POINT_GROUP
    )
    assert registry.discover(entry_points=[entry]) == [cap_id]
    assert isinstance(registry.capability(cap_id), cap_cls)
    registry.validate(env={})


def test_both_register_together_and_validate() -> None:
    registry = CapabilityRegistry()
    registry.register(DocumentVerbatimCapability())
    registry.register(DocumentExtractCapability())
    registry.validate(env={})


def test_team_scope_defaults_to_admin_gated() -> None:
    assert DocumentVerbatimCapability.manifest.team_scope == TeamScopePolicy.ADMIN_GATED
    assert DocumentExtractCapability.manifest.team_scope == TeamScopePolicy.ADMIN_GATED


# ---------------------------------------------------------------------------
# read_document (verbatim) — tool behaviour + continuation footer
# ---------------------------------------------------------------------------


def test_verbatim_tool_registered() -> None:
    cap = DocumentVerbatimCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(), config={}
    )
    assert set(_tools(cap, ctx)) == {"read_document"}


@pytest.mark.asyncio
async def test_read_document_returns_page_and_continuation() -> None:
    # Page size 200 is the wire minimum resolve_page_max_chars clamps to, so the
    # document must exceed it to page. full=500 → first page 0..200, more remains.
    port = _FakeMarkdownPort(full="A" * 500)
    cap = DocumentVerbatimCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(port), config={}
    )

    msg = await _invoke(
        cap, ctx, "read_document", {"document_uid": "u1", "max_chars": 200}
    )

    assert port.calls[0] == {"document_uid": "u1", "offset": 0, "max_chars": 200}
    assert msg.content.startswith("AAAA")
    # The verbatim footer offers (not commands) continuation with the next offset.
    assert "More text remains" in msg.content
    assert "offset=200" in msg.content
    # content_and_artifact: the same text must ride the artifact blocks too.
    assert msg.artifact.blocks[0].text == msg.content
    assert msg.artifact.is_error is False


@pytest.mark.asyncio
async def test_read_document_signals_end_of_document() -> None:
    port = _FakeMarkdownPort(full="A" * 500)
    cap = DocumentVerbatimCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(port), config={}
    )

    msg = await _invoke(
        cap,
        ctx,
        "read_document",
        {"document_uid": "u1", "offset": 400, "max_chars": 200},
    )
    assert "End of document" in msg.content


# ---------------------------------------------------------------------------
# extract_from_document — exhaustive continuation directive
# ---------------------------------------------------------------------------


def test_extract_tool_registered() -> None:
    cap = DocumentExtractCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(), config={}
    )
    assert set(_tools(cap, ctx)) == {"extract_from_document"}


@pytest.mark.asyncio
async def test_extract_directs_the_agent_to_keep_paging() -> None:
    port = _FakeMarkdownPort(full="A" * 500)
    cap = DocumentExtractCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(port), config={}
    )

    mid = await _invoke(
        cap,
        ctx,
        "extract_from_document",
        {"document_uid": "u1", "what_to_extract": "requirements", "max_chars": 200},
    )
    # Imperative directive, unlike the verbatim tool's softer wording.
    assert "MORE TEXT REMAINS" in mid.content
    assert "do not conclude" in mid.content
    assert "offset=200" in mid.content

    end = await _invoke(
        cap,
        ctx,
        "extract_from_document",
        {
            "document_uid": "u1",
            "what_to_extract": "requirements",
            "offset": 400,
            "max_chars": 200,
        },
    )
    assert "END OF DOCUMENT reached" in end.content


# ---------------------------------------------------------------------------
# Config page cap, missing port, error shaping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_page_cap_is_default_and_hard_bound() -> None:
    port = _FakeMarkdownPort(full="A" * 2000)
    cap = DocumentVerbatimCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=_services(port),
        config={"page_max_chars": 300},
    )

    # Caller asks for more than the cap → clamped down.
    await _invoke(cap, ctx, "read_document", {"document_uid": "u1", "max_chars": 4000})
    assert port.calls[0]["max_chars"] == 300
    # Caller asks for nothing → the cap is the default.
    await _invoke(cap, ctx, "read_document", {"document_uid": "u1"})
    assert port.calls[1]["max_chars"] == 300
    # Caller asks under the cap → honored.
    await _invoke(cap, ctx, "read_document", {"document_uid": "u1", "max_chars": 250})
    assert port.calls[2]["max_chars"] == 250


def test_resolve_page_max_chars_bounds() -> None:
    assert resolve_page_max_chars(None, None) == DEFAULT_PAGE_MAX_CHARS
    assert resolve_page_max_chars(None, 50) == 200
    assert resolve_page_max_chars(None, 999_999) == 50_000


@pytest.mark.asyncio
async def test_missing_markdown_port_fails_loud() -> None:
    cap = DocumentVerbatimCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=RuntimeServices(), config={}
    )
    with pytest.raises(RuntimeError, match="document_markdown"):
        await _invoke(cap, ctx, "read_document", {"document_uid": "u"})


@pytest.mark.asyncio
async def test_403_failure_teaches_uid_recovery() -> None:
    port = _FakeMarkdownPort(
        error=DocumentPortCallError("403 Forbidden", status_code=403)
    )
    cap = DocumentExtractCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(port), config={}
    )

    msg = await _invoke(
        cap,
        ctx,
        "extract_from_document",
        {"document_uid": "cahier.pdf", "what_to_extract": "x"},
    )
    assert msg.artifact.is_error is True
    assert "opaque uid" in msg.content
    assert "document_uid=cahier.pdf" in msg.content
    # The recovery hint must also land in the artifact blocks (Graph agent path).
    assert msg.artifact.blocks[0].text == msg.content


@pytest.mark.asyncio
async def test_timeout_failure_names_the_document() -> None:
    port = _FakeMarkdownPort(
        error=DocumentPortCallError("read timeout", timed_out=True)
    )
    cap = DocumentVerbatimCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(port), config={}
    )

    msg = await _invoke(cap, ctx, "read_document", {"document_uid": "u-42"})
    assert msg.artifact.is_error is True
    assert "timed out" in msg.content
    assert "document_uid=u-42" in msg.content


def test_config_model_accepts_empty() -> None:
    assert DocumentReadConfig().page_max_chars is None
