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
`DocumentSummarizeCapability` (RFC §10.1) — split out of the #1906
`document_access` pilot (2026-07-31, #2180) so `summarize_document` is an
explicit, admin-gated per-agent opt-in. Its #2177 HITL gate pauses for
approval by default, configurable per instance via `require_confirmation`
(#2179's ReAct V2 HITL resume dead-end blocked this until it was fixed).
Covers: registration, the admin-gated `team_scope` default, the HITL
declaration and its per-instance toggle, and the tool behavior moved
verbatim from `test_capability_document_access_1906.py`.
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
from fred_runtime.capabilities.document_summarize import (
    DEFAULT_SUMMARIZE_MAX_CHARS,
    DocumentSummarizeCapability,
    DocumentSummarizeConfig,
    resolve_summarize_max_chars,
)
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    HitlGateRequest,
)
from fred_sdk.contracts.models import TeamScopePolicy
from fred_sdk.contracts.runtime import (
    DocumentPortCallError,
    DocumentSummarizePort,
    DocumentSummaryResult,
    RuntimeServices,
)

_ENTRY_POINT_VALUE = (
    "fred_runtime.capabilities.document_summarize:DocumentSummarizeCapability"
)


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)


class _FakeSummarizePort(DocumentSummarizePort):
    """Fake `DocumentSummarizePort` recording the params it received."""

    def __init__(
        self,
        result: DocumentSummaryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result or DocumentSummaryResult(
            document_uid="u1", summary="the summary"
        )
        self._error = error

    async def summarize(
        self,
        document_uid: str,
        *,
        instruction: str | None = None,
        max_chars: int = 2000,
    ) -> DocumentSummaryResult:
        self.calls.append(
            {
                "document_uid": document_uid,
                "instruction": instruction,
                "max_chars": max_chars,
            }
        )
        if self._error is not None:
            raise self._error
        return self._result


def _services(summarize: _FakeSummarizePort | None = None) -> RuntimeServices:
    return RuntimeServices(document_summarize=summarize or _FakeSummarizePort())


def _capability_tools(
    cap: DocumentSummarizeCapability, ctx: CapabilityContext[Any, Any]
) -> dict[str, Any]:
    middleware = cap.middleware(ctx)
    assert len(middleware) == 1
    return {t.name: t for t in middleware[0].tools}  # type: ignore[attr-defined]


async def _invoke_named_tool(
    cap: DocumentSummarizeCapability,
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
        name="document_summarize",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )
    registered = registry.discover(entry_points=[entry])

    assert registered == ["document_summarize"]
    assert isinstance(
        registry.capability("document_summarize"), DocumentSummarizeCapability
    )
    registry.validate(env={})


def test_double_registration_trips_boot_invariant() -> None:
    registry = CapabilityRegistry()
    registry.register(DocumentSummarizeCapability())
    with pytest.raises(DuplicateCapabilityIdError):
        registry.register(DocumentSummarizeCapability())


def test_team_scope_defaults_to_admin_gated() -> None:
    """Unlike document_access (opts into DEFAULT_ON), this capability has no
    query-shaped signal to gate invocation on — a team admin must explicitly
    enable it before any agent in that team can even select it (RFC §10.1)."""

    assert DocumentSummarizeCapability.manifest.team_scope == (
        TeamScopePolicy.ADMIN_GATED
    )


# ---------------------------------------------------------------------------
# HITL declaration (RFC §5.4) — gated by default, per-instance configurable
# ---------------------------------------------------------------------------


def _hitl_gate_request(config: DocumentSummarizeConfig) -> HitlGateRequest:
    ctx = build_capability_context(
        DocumentSummarizeCapability(),
        identity=_identity(),
        services=_services(),
        config=config,
    )
    return HitlGateRequest(
        tool_call={"name": "summarize_document", "args": {}, "id": "call-1"},
        tool=None,
        context=ctx,
    )


def test_summarize_document_declares_a_configurable_hitl_gate() -> None:
    """#2177: `require=False` + a `when` predicate, not a hardcoded
    `require=True` — the gate is decided from the resolved instance config at
    gate time (`_confirmation_required`), not fixed at declaration time."""

    specs = list(DocumentSummarizeCapability().hitl_specs())
    assert len(specs) == 1
    assert specs[0].tool == "summarize_document"
    assert specs[0].require is False
    assert specs[0].when is not None


def test_summarize_document_is_hitl_gated_by_default() -> None:
    spec = list(DocumentSummarizeCapability().hitl_specs())[0]
    assert spec.when is not None
    assert spec.when(_hitl_gate_request(DocumentSummarizeConfig())) is True


def test_summarize_document_confirmation_can_be_disabled_per_instance() -> None:
    """An admin who already trusts this agent's usage can turn the gate off —
    admission control (ADMIN_GATED) remains the outer layer regardless."""

    spec = list(DocumentSummarizeCapability().hitl_specs())[0]
    assert spec.when is not None
    request = _hitl_gate_request(DocumentSummarizeConfig(require_confirmation=False))
    assert spec.when(request) is False


# ---------------------------------------------------------------------------
# Tool behavior (moved verbatim from test_capability_document_access_1906.py)
# ---------------------------------------------------------------------------


def test_tool_registered_by_default() -> None:
    cap = DocumentSummarizeCapability()
    ctx = build_capability_context(
        cap, identity=_identity(), services=_services(), config={}
    )
    assert set(_capability_tools(cap, ctx)) == {"summarize_document"}


@pytest.mark.asyncio
async def test_summarize_tool_passes_instruction_and_returns_summary() -> None:
    summarize_port = _FakeSummarizePort()
    cap = DocumentSummarizeCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=_services(summarize=summarize_port),
        config={},
    )

    message = await _invoke_named_tool(
        cap,
        ctx,
        "summarize_document",
        {"document_uid": "u1", "instruction": "focus on risks"},
    )

    call = summarize_port.calls[0]
    assert call["document_uid"] == "u1"
    assert call["instruction"] == "focus on risks"
    # No caller request, no config cap → built-in default.
    assert call["max_chars"] == DEFAULT_SUMMARIZE_MAX_CHARS
    assert message.content == "the summary"
    assert message.artifact.tool_ref == "summarize_document"
    assert message.artifact.is_error is False
    # CAPAB-02: the summary text must also live in `blocks`, not only in
    # `content` — a Graph agent's plain-dict invocation keeps only the
    # artifact half of a `content_and_artifact` return.
    assert message.artifact.blocks[0].text == "the summary"


@pytest.mark.asyncio
async def test_summarize_config_cap_is_default_and_hard_bound() -> None:
    summarize_port = _FakeSummarizePort()
    cap = DocumentSummarizeCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=_services(summarize=summarize_port),
        config={"summarize_max_chars": 1000},
    )

    # Caller asks for more than the cap → clamped down to it.
    await _invoke_named_tool(
        cap, ctx, "summarize_document", {"document_uid": "u1", "max_chars": 4000}
    )
    assert summarize_port.calls[0]["max_chars"] == 1000

    # Caller asks for nothing → the cap is the default.
    await _invoke_named_tool(cap, ctx, "summarize_document", {"document_uid": "u1"})
    assert summarize_port.calls[1]["max_chars"] == 1000

    # Caller asks under the cap → honored verbatim.
    await _invoke_named_tool(
        cap, ctx, "summarize_document", {"document_uid": "u1", "max_chars": 600}
    )
    assert summarize_port.calls[2]["max_chars"] == 600


def test_resolve_summarize_max_chars_bounds() -> None:
    # No cap: request honored, but clamped into the endpoint's wire bounds.
    assert resolve_summarize_max_chars(None, None) == DEFAULT_SUMMARIZE_MAX_CHARS
    assert resolve_summarize_max_chars(None, 50) == 200
    assert resolve_summarize_max_chars(None, 50_000) == 20_000


@pytest.mark.asyncio
async def test_summarize_403_failure_teaches_uid_recovery() -> None:
    """A 403/404 usually means the model passed a file NAME as the uid (seen
    live 2026-07-21) — the error message must teach the recovery path so the
    model retries with the real uid instead of echoing the failure."""

    summarize_port = _FakeSummarizePort(
        error=DocumentPortCallError("403 Forbidden", status_code=403)
    )
    cap = DocumentSummarizeCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=_services(summarize=summarize_port),
        config={},
    )

    message = await _invoke_named_tool(
        cap, ctx, "summarize_document", {"document_uid": "diff_main_swift.md"}
    )

    assert message.artifact.is_error is True
    assert "opaque uid" in message.content
    assert "list_document_tree" in message.content
    # Issue #2244: the other live-observed 403 cause is a FOLDER tag id taken
    # from a tree folder line — the hint must cover it so the model summarizes
    # the folder's documents instead of retrying the same bad id.
    assert "[folder:...]" in message.content
    assert "summarize each document" in message.content
    # CAPAB-02: the recovery hint is appended to `message` AFTER
    # `_document_tool_failure` already built the artifact — it must also
    # land in `blocks`, or a Graph agent (which keeps only the artifact)
    # loses exactly the guidance a model needs to self-correct.
    assert message.artifact.blocks[0].text == message.content


@pytest.mark.asyncio
async def test_summarize_timeout_failure_names_the_document() -> None:
    summarize_port = _FakeSummarizePort(
        error=DocumentPortCallError("read timeout", timed_out=True)
    )
    cap = DocumentSummarizeCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=_services(summarize=summarize_port),
        config={},
    )

    message = await _invoke_named_tool(
        cap, ctx, "summarize_document", {"document_uid": "u-42"}
    )

    assert message.artifact.is_error is True
    assert "timed out" in message.content
    assert "document_uid=u-42" in message.content


@pytest.mark.asyncio
async def test_missing_document_summarize_port_fails_loud() -> None:
    """A missing platform port is a wiring bug, not an empty result."""

    cap = DocumentSummarizeCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(),
        config={},
    )

    with pytest.raises(RuntimeError, match="document_summarize"):
        await _invoke_named_tool(cap, ctx, "summarize_document", {"document_uid": "u"})


def test_config_model_accepts_empty() -> None:
    assert DocumentSummarizeConfig().summarize_max_chars is None
