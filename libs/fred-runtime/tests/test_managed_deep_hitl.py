# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Managed HTTP + real Deep graph + SQL claims/history, without a live Wiki or LLM."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, cast

import pytest
from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_runtime.app import agent_app
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.runtime_support.tool_approval import CapabilityHitlBinding
from fred_sdk.contracts.capability import HitlSpec, ToolCarrierMiddleware
from fred_sdk.contracts.models import DeepAgentDefinition, ReActPolicy
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from test_agent_app import _build_test_config, _EchoAgent
from test_graph_executor_storage import _Agent as StorageGraph
from weaver_fixtures import create_managed_app, managed_payload

pytestmark = pytest.mark.usefixtures("offline_pod_infrastructure")


class Deep(DeepAgentDefinition):
    agent_id: str = "test.managed.deep"
    role: str = "Deep"
    description: str = "Managed approval test"

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template="Publish only after approval.")


@pytest.mark.parametrize("definition", [Deep(), _EchoAgent(), StorageGraph()])
def test_native_templates_advertise_durable_hitl(monkeypatch, tmp_path, definition):
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )
    with TestClient(
        app, headers={"Authorization": "Bearer test-person-token"}
    ) as client:
        assert client.get("/pod/v1/agents/templates").json()[0]["supports_hitl"]
        # A pod without durable claims must not promise resumable HITL.
        context = agent_app.get_runtime_context()
        with monkeypatch.context() as patch:
            patch.setattr(
                context, "_config", replace(context.config, checkpointer=None)
            )
            assert not client.get("/pod/v1/agents/templates").json()[0]["supports_hitl"]


@pytest.mark.parametrize("choice", ["proceed", "cancel"])
@pytest.mark.parametrize("concurrent", [False, True])
def test_deep_approval_survives_history_and_is_single_use(
    monkeypatch, tmp_path, choice, concurrent
):
    effects = []

    @tool
    def wiki_publish_proposal(proposal_id: str) -> str:
        """Publish the previously prepared proposal."""
        effects.append(proposal_id)
        return "Published"

    block = CapabilityAgentBlock(
        middleware=(
            ToolCarrierMiddleware([wiki_publish_proposal], capability_id="wiki"),
        ),
        tools=(wiki_publish_proposal,),
        hitl={
            "wiki_publish_proposal": CapabilityHitlBinding(
                context=cast(Any, None),
                spec=HitlSpec(tool="wiki_publish_proposal", require=True),
            )
        },
    )
    monkeypatch.setattr(agent_app, "_build_capability_block", lambda *a, **kw: block)
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "wiki_publish_proposal",
                        "args": {"proposal_id": "isolated-proposal"},
                        "id": "publish-call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Done"),
        ]
    )
    monkeypatch.setattr(
        agent_app,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = Deep()
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )
    payload = managed_payload({"input": "Publish", "session_id": "isolated-hitl"})
    with TestClient(
        app, headers={"Authorization": "Bearer test-person-token"}
    ) as client:
        paused = client.post("/pod/v1/agents/execute", json=payload)
        assert paused.status_code == 200, paused.text
        assert paused.json()["kind"] == "awaiting_human", paused.text
        assert effects == []
        history = client.get("/pod/v1/agents/sessions/isolated-hitl/messages")
        assert history.status_code == 200, history.text
        prompt = next(
            p for m in history.json() for p in m["parts"] if p["type"] == "hitl_request"
        )
        assert prompt["resume_status"] == "pending"
        assert prompt["stage"] == "tool_approval"
        assert not prompt.get("occurrence_id")
        assert prompt["pending_calls"][0]["tool_name"] == "wiki_publish_proposal"
        resume = {
            **payload,
            "input": "",
            "interrupt_id": prompt["interrupt_id"],
            "resume_payload": {"choice_id": choice},
        }
        stale = client.post(
            "/pod/v1/agents/execute", json={**resume, "interrupt_id": "forged"}
        )
        assert stale.status_code == 409
        assert effects == []
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [
                pool.submit(client.post, "/pod/v1/agents/execute", json=resume)
                for _ in range(2 if concurrent else 1)
            ]
            results = [attempt.result() for attempt in attempts]
        assert sum(r.json().get("kind") == "final" for r in results) == 1
        for result in results:
            assert result.status_code == 409 or result.json().get("kind") in (
                "final",
                "execution_error",
            ), result.text
        assert effects == (["isolated-proposal"] if choice == "proceed" else [])
        replay = client.post("/pod/v1/agents/execute", json=resume)
        assert replay.status_code == 409, replay.text
        assert effects == (["isolated-proposal"] if choice == "proceed" else [])
        restored = client.get("/pod/v1/agents/sessions/isolated-hitl/messages").json()
        responses = [
            p for m in restored for p in m["parts"] if p["type"] == "hitl_response"
        ]
        assert len(responses) == 1
        assert responses[0]["choice_id"] == choice
