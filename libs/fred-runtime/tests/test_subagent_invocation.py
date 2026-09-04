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
Sub-agent invocation: what a same-agent child inherits, and what it cannot be told.

The whole security posture of the feature is that the parent turn's resolved
state reaches its children on a PRIVATE attribute of the invoker, so a crafted
`AgentInvocationRequest` can neither read it nor set it — in particular it can
never reset the recursion depth. These tests pin that seam, plus the
checkpointer-free child run and the `execution_error` mapping a failing child
depends on.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from types import SimpleNamespace

import pytest
from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_runtime import model_routing
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app import create_agent_app
from fred_runtime.react import react_tool_loop
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    BoundRuntimeContext,
    LinkPart,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    GraphAgentDefinition,
    GraphDefinition,
    GraphNodeDefinition,
    MCPServerRef,
    ReActAgentDefinition,
)
from fred_sdk.graph.runtime import GraphNodeResult
from langchain_core.messages import AIMessage
from pydantic import BaseModel
from test_agent_app import _build_test_config, _EchoAgent

OTHER_AGENT_ID = "rags.sample.other"


GRAPH_AGENT_ID = "rags.sample.graph"


class _OtherAgent(_EchoAgent):
    agent_id: str = OTHER_AGENT_ID


class _GraphIO(BaseModel):
    message: str = ""


class _GraphCallee(GraphAgentDefinition):
    """Smallest valid Graph callee — it composes no system prompt to override."""

    agent_id: str = GRAPH_AGENT_ID
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="GraphIO",
            entry_node="n",
            nodes=(GraphNodeDefinition(node_id="n", title="N"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphIO

    def state_model(self) -> type[BaseModel]:
        return _GraphIO

    def output_model(self) -> type[BaseModel]:
        return _GraphIO

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        return input_model

    def node_handlers(self) -> Mapping[str, object]:
        async def _n(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult()

        return {"n": _n}

    def build_output(self, state: BaseModel) -> BaseModel:
        return state


def _binding(*, session_id: str = "session-1") -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="alice",
            team_id="fredlab",
            trace_id="trace-1",
            correlation_id="corr-1",
            language="fr",
            access_token="parent-token",
            selected_document_uids=["doc-a"],
            search_policy="strict",
            context_prompt_text="the user's selected prompt",
            attachments_markdown="the user's attachment",
            checkpoint_id="ckpt-1",
        ),
        portable_context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="tenant-a",
            environment=PortableEnvironment.DEV,
            trace_id="trace-1",
            session_id=session_id,
            user_id="alice",
            team_id="fredlab",
        ),
    )


def _parent_turn(
    *,
    agent_id: str,
    depth: int = 0,
    tuning: AgentTuning | None = None,
    definition: ReActAgentDefinition | None = None,
) -> agent_app_module._ParentTurn:
    return agent_app_module._ParentTurn(
        agent_id=agent_id,
        definition=definition if definition is not None else _EchoAgent(),
        tuning=tuning
        or AgentTuning(role="r", description="d", selected_capability_ids=["subagent"]),
        capability_registry="registry-sentinel",  # type: ignore[arg-type]
        team_settings={"subagent": {}},
        agent_instance_id="instance-1",
        exchange_id="exchange-1",
        reasoning_enabled_model_ids=("openai-gpt-4o",),
        turn_options={"document_access": {"library_tag_ids": ["lib-1"]}},
        binding=_binding(),
        invocation_depth=depth,
    )


def _child_request(agent_id: str, **overrides) -> AgentInvocationRequest:
    context = PortableContext(
        request_id="forged",
        correlation_id="forged",
        actor="alice",
        tenant="forged-tenant",
        environment=PortableEnvironment.DEV,
        session_id=overrides.pop("session_id", "session-1"),
        user_id=overrides.pop("user_id", "alice"),
        team_id=overrides.pop("team_id", "fredlab"),
    )
    return AgentInvocationRequest(
        agent_id=agent_id, message="do the thing", context=context, **overrides
    )


def _record_turn(monkeypatch, payloads: list[dict] | None = None) -> dict:
    """Capture what the invoker hands the turn path, and replay `payloads`."""

    seen: dict = {}

    # Mirrors the real signature's defaults, so `seen` always holds the
    # EFFECTIVE value a child runs with, not just what was passed explicitly.
    async def _fake(
        definition,
        request,
        access_token=None,
        *,
        exchange_id=None,
        tuning=None,
        capability_registry=None,
        team_settings=None,
        reasoning_enabled_model_ids=None,
        use_checkpointer=True,
        usable_model_ids=agent_app_module._Unresolved.TOKEN,
        **kwargs,
    ):
        seen["definition"] = definition
        seen["request"] = request
        seen["access_token"] = access_token
        seen["exchange_id"] = exchange_id
        seen["tuning"] = tuning
        seen["capability_registry"] = capability_registry
        seen["team_settings"] = team_settings
        seen["reasoning_enabled_model_ids"] = reasoning_enabled_model_ids
        seen["use_checkpointer"] = use_checkpointer
        seen["usable_model_ids"] = usable_model_ids
        seen.update(kwargs)
        for payload in payloads or [{"kind": "final", "sequence": 0, "content": "ok"}]:
            yield payload

    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", _fake)
    return seen


def _invoker(parent: agent_app_module._ParentTurn | None):
    definitions = [_EchoAgent(), _OtherAgent(), _GraphCallee()]
    return agent_app_module.LocalRegistryAgentInvoker(
        registry={d.agent_id: d for d in definitions},
        access_token="token-1",
        parent_turn=parent,
    )


def test_same_agent_child_inherits_the_parent_turn(monkeypatch) -> None:
    seen = _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id
    invoker = _invoker(_parent_turn(agent_id=parent_agent_id))

    result = asyncio.run(invoker.invoke(_child_request(parent_agent_id)))

    assert result.content == "ok"
    assert seen["tuning"].selected_capability_ids == ["subagent"]
    assert seen["capability_registry"] == "registry-sentinel"
    assert seen["team_settings"] == {"subagent": {}}
    assert seen["exchange_id"] == "exchange-1"
    assert seen["reasoning_enabled_model_ids"] == ("openai-gpt-4o",)
    assert seen["request"].agent_instance_id == "instance-1"
    # Turn options narrow, never widen: a child without them would search
    # wider than the user's own turn was allowed to.
    assert seen["request"].turn_options == {
        "document_access": {"library_tag_ids": ["lib-1"]}
    }
    context = seen["request"].context
    # The parent's RuntimeContext selections reach the child; the caller's own
    # PortableContext (which carries none of them) does not decide any of this.
    assert context["selected_document_uids"] == ["doc-a"]
    assert context["search_policy"] == "strict"
    assert context["language"] == "fr"
    assert context["session_id"] == "session-1"
    assert context["tenant"] == "tenant-a"
    assert context["trace_id"] == "trace-1"
    # The user's own conversation context, the resume fields and the token do
    # not travel with it.
    assert "context_prompt_text" not in context
    assert "attachments_markdown" not in context
    assert "checkpoint_id" not in context
    assert "access_token" not in context
    assert context["execution_action"] == "execute"


def test_cross_agent_child_inherits_nothing_of_the_parent_turn(monkeypatch) -> None:
    seen = _record_turn(monkeypatch)
    invoker = _invoker(_parent_turn(agent_id=_EchoAgent().agent_id))

    asyncio.run(invoker.invoke(_child_request(OTHER_AGENT_ID)))

    assert seen["tuning"] is None
    assert seen["capability_registry"] is None
    assert seen["team_settings"] is None
    assert seen["exchange_id"] is None
    assert seen["reasoning_enabled_model_ids"] is None
    assert seen["request"].agent_instance_id is None
    assert seen["request"].turn_options == {}
    # Today's behaviour, byte for byte: the request's own context is the
    # callee's context.
    assert seen["request"].context["tenant"] == "forged-tenant"


def test_system_prompt_override_reaches_the_child_turn(monkeypatch) -> None:
    seen = _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id

    asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id, system_prompt="SUBAGENT-FRAMING")
        )
    )
    assert seen["system_prompt_override"] == "SUBAGENT-FRAMING"
    # It is a per-call parameter, not part of the child's context: nothing a
    # later turn could read back off the request it was built from.
    assert "system_prompt" not in seen["request"].context

    # Absent by default, so every caller that never sets it is unchanged.
    asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )
    assert seen["system_prompt_override"] is None


def test_system_prompt_override_is_refused_for_a_graph_callee(monkeypatch) -> None:
    seen = _record_turn(monkeypatch)
    invoker = _invoker(_parent_turn(agent_id=_EchoAgent().agent_id))

    result = asyncio.run(
        invoker.invoke(_child_request(GRAPH_AGENT_ID, system_prompt="FRAMING"))
    )

    # Loud, never a silently dropped field: a Graph agent composes no system
    # prompt, so there is no layer to replace.
    assert result.is_error is True
    assert "no system prompt to override" in result.content
    assert seen == {}


def test_depth_rises_on_every_re_entry_and_a_request_cannot_lower_it(
    monkeypatch,
) -> None:
    seen = _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id

    # There is no depth field on the request to forge: the only source is the
    # invoker's own private counter. A child of a depth-2 turn runs at 3.
    asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id, depth=2)).invoke(
            _child_request(parent_agent_id)
        )
    )
    assert seen["invocation_depth"] == 3
    assert not any("depth" in field for field in AgentInvocationRequest.model_fields)

    # Cross-agent too — depth bounds the call stack, not one agent's identity,
    # so an A -> B -> A cycle is bounded as well.
    asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id, depth=2)).invoke(
            _child_request(OTHER_AGENT_ID)
        )
    )
    assert seen["invocation_depth"] == 3


def test_same_agent_child_runs_without_a_checkpointer(monkeypatch) -> None:
    seen = _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id

    asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )
    # Otherwise the child maps the parent's session_id to LangGraph's
    # thread_id and loads — then overwrites — the parent's own state.
    assert seen["use_checkpointer"] is False

    asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(OTHER_AGENT_ID)
        )
    )
    assert seen["use_checkpointer"] is True


def test_same_agent_child_cannot_claim_another_identity(monkeypatch) -> None:
    _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id
    invoker = _invoker(_parent_turn(agent_id=parent_agent_id))

    result = asyncio.run(
        invoker.invoke(_child_request(parent_agent_id, user_id="mallory"))
    )
    assert result.is_error is True
    assert "user, session and team" in result.content


def test_child_sources_and_ui_parts_reach_the_caller(monkeypatch) -> None:
    _record_turn(
        monkeypatch,
        payloads=[
            {
                "kind": "final",
                "sequence": 0,
                "content": "Two documents mention it.",
                # As they arrive: a JSON dump of the child's `final` event.
                "sources": [
                    {
                        "content": "the cited chunk",
                        "uid": "doc-a",
                        "title": "Handbook",
                        "score": 0.42,
                    }
                ],
                "ui_parts": [
                    {"type": "link", "href": "/documents/doc-a", "kind": "citation"}
                ],
            }
        ],
    )
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )

    assert result.content == "Two documents mention it."
    assert [hit.uid for hit in result.sources] == ["doc-a"]
    (part,) = result.ui_parts
    assert isinstance(part, LinkPart)
    assert part.href == "/documents/doc-a"


def test_a_part_this_process_cannot_rebuild_is_an_error_not_a_crash(
    monkeypatch,
) -> None:
    _record_turn(
        monkeypatch,
        payloads=[
            {
                "kind": "final",
                "sequence": 0,
                "content": "here it is",
                # A part kind no capability registered in this process.
                "ui_parts": [{"type": "from_the_future", "payload": {}}],
            }
        ],
    )
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )

    # Every other branch of this port returns an error result; so does this one.
    assert result.is_error is True
    assert "could not be read" in result.content


def test_a_child_that_cites_nothing_carries_nothing(monkeypatch) -> None:
    _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )

    assert result.content == "ok"
    assert result.sources == ()
    assert result.ui_parts == ()


def test_a_same_agent_child_carries_the_parent_s_model_authorization(
    monkeypatch,
) -> None:
    parent_agent_id = _EchoAgent().agent_id
    # Fail-closed and possibly empty: an empty tuple is "nothing allowed", the
    # opposite of the None that means "ReBAC is off" — so it must survive the
    # carry as itself.
    parent = replace(
        _parent_turn(agent_id=parent_agent_id),
        binding=_binding().model_copy(update={"usable_model_ids": ()}),
    )

    seen = _record_turn(monkeypatch)
    asyncio.run(_invoker(parent).invoke(_child_request(parent_agent_id)))
    assert seen["usable_model_ids"] == ()

    # A cross-agent child resolves its own: different agent, possibly a
    # different team.
    seen = _record_turn(monkeypatch)
    asyncio.run(_invoker(parent).invoke(_child_request(OTHER_AGENT_ID)))
    assert seen["usable_model_ids"] is agent_app_module._Unresolved.TOKEN


def test_a_carried_authorization_snapshot_skips_the_rebac_query(monkeypatch) -> None:
    """What the carry buys: one ReBAC round trip fewer per child, on the path
    to its first model call."""

    calls: list[str] = []

    async def _counting_query(rebac, team_id):
        calls.append(team_id)
        return frozenset({"model__openai__gpt-5.1"})

    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(rebac_engine=None)),
    )
    monkeypatch.setattr(
        model_routing, "usable_model_capability_ids", _counting_query, raising=False
    )

    class _Stop(Exception):
        pass

    bindings: list[BoundRuntimeContext] = []

    def _capture(definition, binding, **kwargs):
        # Everything under test happens before the turn is assembled.
        bindings.append(binding)
        raise _Stop

    monkeypatch.setattr(agent_app_module, "_build_runtime_services", _capture)

    async def _drive(**kwargs) -> None:
        stream = agent_app_module._iterate_runtime_event_payloads(
            _EchoAgent(),
            agent_app_module._AgentExecuteRequest(
                agent_id=_EchoAgent().agent_id,
                message="hi",
                context={"user_id": "alice", "session_id": "session-1"},
            ),
            team_id="fredlab",
            **kwargs,
        )
        with pytest.raises(_Stop):
            await anext(stream)

    asyncio.run(_drive(usable_model_ids=("model__mistral__large",)))
    assert calls == []
    assert bindings[-1].usable_model_ids == ("model__mistral__large",)

    # Absent — a top-level turn — it still resolves its own.
    asyncio.run(_drive())
    assert calls == ["fredlab"]
    assert bindings[-1].usable_model_ids == ("model__openai__gpt-5.1",)


def test_execution_error_reaches_the_caller_with_its_message(monkeypatch) -> None:
    _record_turn(
        monkeypatch,
        payloads=[
            {"kind": "execution_error", "sequence": 0, "message": "provider timed out"}
        ],
    )
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )
    # Before this branch existed the caller got is_error=True and an empty
    # string, which the model reads as "the sub-agent answered nothing".
    assert result.is_error is True
    assert result.content == "provider timed out"


def test_child_services_drop_the_pod_checkpointer(monkeypatch, tmp_path) -> None:
    definition = _EchoAgent()
    registry = {definition.agent_id: definition}
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
    )
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app):
        parent = agent_app_module._build_runtime_services(
            definition, _binding(), team_id="fredlab", registry=registry
        )
        child = agent_app_module._build_runtime_services(
            definition,
            _binding(),
            team_id="fredlab",
            registry=registry,
            use_checkpointer=False,
        )
        # A per-run substitution, not a change to the pod's own checkpointer.
        assert parent.checkpointer is not None
        assert child.checkpointer is None


def test_child_capability_block_is_built_from_the_forwarded_tuning(
    monkeypatch, tmp_path
) -> None:
    """
    The outcome, not the seam: a REAL nested turn through the invoker, with
    `_build_capability_block` captured where it is actually called, proving the
    child's tools are assembled from the parent's tuning at depth+1.
    """
    seen: dict = {}

    def _capture_capability_block(capability_registry, tuning, **kwargs):
        seen["capability_registry"] = capability_registry
        seen["tuning"] = tuning
        seen.update(kwargs)
        return None

    monkeypatch.setattr(
        agent_app_module, "_build_capability_block", _capture_capability_block
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="Done.")])
        ),
    )

    definition = _EchoAgent()
    registry = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app):
        services = agent_app_module._build_runtime_services(
            definition,
            _binding(),
            team_id="fredlab",
            registry=registry,
            parent_turn=_parent_turn(agent_id=definition.agent_id, depth=1),
        )
        assert services.agent_invoker is not None
        result = asyncio.run(
            services.agent_invoker.invoke(_child_request(definition.agent_id))
        )

    assert result.is_error is False
    assert seen["tuning"].selected_capability_ids == ["subagent"]
    assert seen["capability_registry"] == "registry-sentinel"
    assert seen["team_settings"] == {"subagent": {}}
    assert seen["agent_instance_id"] == "instance-1"
    assert seen["turn_options"] == {"document_access": {"library_tag_ids": ["lib-1"]}}
    assert seen["invocation_depth"] == 2


def test_same_agent_child_runs_the_definition_its_parent_runs(monkeypatch) -> None:
    """
    The registry holds raw templates. Only `_apply_runtime_tuning` turns an
    instance's selected capability id into an `MCPServerRef`, so a child
    resolved off the registry ran with NO MCP tools at all while its parent
    kept them — and nothing in the stream said why.
    """
    seen = _record_turn(monkeypatch)
    # What the parent's own turn runs: the template overlaid with its
    # instance's tuning.
    tuned = _EchoAgent().model_copy(
        update={
            "default_mcp_servers": (MCPServerRef(id="mcp-tabular"),),
            "system_prompt_template": "the operator's own prompt",
        }
    )

    asyncio.run(
        _invoker(_parent_turn(agent_id=tuned.agent_id, definition=tuned)).invoke(
            _child_request(tuned.agent_id)
        )
    )

    child = seen["definition"]
    assert child.system_prompt_template == "the operator's own prompt"
    # The tool surface itself, not just the definition field it comes from.
    settings = agent_app_module._build_agent_settings(child, team_id="fredlab")
    assert [ref.id for ref in settings.active_mcp_servers] == ["mcp-tabular"]


def test_cross_agent_child_runs_the_registry_template(monkeypatch) -> None:
    """The parent instance's tuning describes the parent, not some other agent."""
    seen = _record_turn(monkeypatch)
    tuned = _EchoAgent().model_copy(
        update={"default_mcp_servers": (MCPServerRef(id="mcp-tabular"),)}
    )

    asyncio.run(
        _invoker(_parent_turn(agent_id=tuned.agent_id, definition=tuned)).invoke(
            _child_request(OTHER_AGENT_ID)
        )
    )

    assert seen["definition"].agent_id == OTHER_AGENT_ID
    assert seen["definition"].default_mcp_servers == ()


def test_child_hitl_gate_is_built_at_the_same_depth_as_its_capabilities(
    monkeypatch, tmp_path
) -> None:
    """
    Same trusted depth, both halves of the child's turn: the capability block
    (which tools exist) and the middleware frame (which of them a human would
    have to approve, and so cannot be offered — the child has no human).
    """
    seen: dict = {}
    real_frame = react_tool_loop.build_react_platform_middleware_frame

    def _capture_capability_block(capability_registry, tuning, **kwargs):
        seen["block_depth"] = kwargs["invocation_depth"]
        return None

    def _capture_frame(**kwargs):
        seen["frame_depth"] = kwargs["invocation_depth"]
        return real_frame(**kwargs)

    monkeypatch.setattr(
        agent_app_module, "_build_capability_block", _capture_capability_block
    )
    monkeypatch.setattr(
        react_tool_loop, "build_react_platform_middleware_frame", _capture_frame
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="Done.")])
        ),
    )

    definition = _EchoAgent()
    registry = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app):
        services = agent_app_module._build_runtime_services(
            definition,
            _binding(),
            team_id="fredlab",
            registry=registry,
            parent_turn=_parent_turn(agent_id=definition.agent_id, depth=1),
        )
        assert services.agent_invoker is not None
        result = asyncio.run(
            services.agent_invoker.invoke(_child_request(definition.agent_id))
        )

    assert result.is_error is False
    assert seen["frame_depth"] == seen["block_depth"] == 2


# --- Per-child token accounting -------------------------------------------
# A child turn emits no `agent.turn_completed` (only `_stream` does), so the
# `final` event's `token_usage` is the only place its spend survives.


def test_token_usage_from_the_final_event_reaches_the_caller(monkeypatch) -> None:
    _record_turn(
        monkeypatch,
        payloads=[
            {
                "kind": "final",
                "sequence": 0,
                "content": "ok",
                "token_usage": {"input_tokens": 1200, "output_tokens": 300},
            }
        ],
    )
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )

    assert result.token_usage == {"input_tokens": 1200, "output_tokens": 300}


def test_token_usage_is_none_when_the_child_reports_none(monkeypatch) -> None:
    _record_turn(monkeypatch)
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )

    assert result.is_error is False
    assert result.token_usage is None


def test_a_failed_child_carries_no_token_usage(monkeypatch) -> None:
    # No `final` event, so there is nothing to read: the metric records the
    # failed child with no counters rather than inventing zeros.
    _record_turn(
        monkeypatch,
        payloads=[
            {"kind": "execution_error", "sequence": 0, "message": "provider timed out"}
        ],
    )
    parent_agent_id = _EchoAgent().agent_id

    result = asyncio.run(
        _invoker(_parent_turn(agent_id=parent_agent_id)).invoke(
            _child_request(parent_agent_id)
        )
    )

    assert result.is_error is True
    assert result.token_usage is None


def test_capability_identity_carries_the_turns_exchange_id(
    monkeypatch, tmp_path
) -> None:
    """`CapabilityIdentity.exchange_id` is what lets a capability's KPI event
    name the turn that produced it — the `subagent` capability's per-child
    metric is its first consumer."""
    seen: dict = {}

    def _capture_capability_block(capability_registry, tuning, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(
        agent_app_module, "_build_capability_block", _capture_capability_block
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="Done.")])
        ),
    )

    definition = _EchoAgent()
    registry = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app):
        services = agent_app_module._build_runtime_services(
            definition,
            _binding(),
            team_id="fredlab",
            registry=registry,
            parent_turn=_parent_turn(agent_id=definition.agent_id),
        )
        assert services.agent_invoker is not None
        asyncio.run(services.agent_invoker.invoke(_child_request(definition.agent_id)))

    # The parent turn's exchange id, inherited by the same-agent child.
    assert seen["exchange_id"] == "exchange-1"
