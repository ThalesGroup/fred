# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The real routed factory, ChatOpenAI adapter and guard over a simulated provider."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from fred_core.model import factory as core_factory
from fred_core.model.http_clients import TransportTuning
from fred_runtime.app.config import InferenceCredentialBinding
from fred_runtime.model_routing.contracts import ModelRoutingError
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import BoundRuntimeContext, RuntimeContext
from fred_sdk.contracts.models import AgentDefinition
from fred_sdk.contracts.weaver import WeaverRuntimeBinding
from weaver_fixtures import resolved_binding


def admitted():
    data = resolved_binding(source="source").model_dump(mode="json")
    fixture = (
        Path(__file__).parents[2] / "fred-sdk/tests/fixtures/inference_admission.json"
    )
    data["inference"] = json.loads(fixture.read_text())
    return WeaverRuntimeBinding.model_validate(data)


def provision(**changes):
    return InferenceCredentialBinding.model_validate(
        dict(
            source_id="source",
            source_revision=1,
            api_root="https://source.invalid/v1",
            credential_binding="source-account",
            api_key_env="FRED_TEST_INFERENCE_KEY",
            **changes,
        )
    )


def build(factory, binding):
    context = RuntimeContext(
        user_id=binding.subject_id,
        session_id=binding.conversation_id,
        space_id=str(binding.space.id),
        agent_instance_id=str(binding.agent.instance_id),
    )
    return factory.build_for_chat(
        definition=cast(AgentDefinition, SimpleNamespace(agent_id="template")),
        binding=cast(BoundRuntimeContext, SimpleNamespace(runtime_context=context)),
    )[0]


@pytest.mark.asyncio
async def test_real_python_adapter_uses_shared_decision_for_every_call(
    monkeypatch, caplog
):
    caplog.set_level("INFO")
    calls = []

    def send(request):
        calls.append(request)
        chunk = {
            "id": "fixture",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "simulated answer"},
                    "finish_reason": "stop",
                }
            ],
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n",
        )

    with httpx.Client(transport=httpx.MockTransport(send)) as sync:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(send)
        ) as asynchronous:
            monkeypatch.setattr(
                core_factory,
                "get_shared_stack",
                lambda *a, **k: (
                    TransportTuning(httpx.Limits(), httpx.Timeout(10)),
                    sync,
                    asynchronous,
                ),
            )
            monkeypatch.setenv("FRED_TEST_INFERENCE_KEY", "synthetic-inference-key")
            binding = admitted()
            authority = TurnAuthority(binding, None)
            factory = RoutedChatModelFactory(credentials=(provision(),))
            with RunScope.open() as scope:
                authority.start(scope)
                scope.turn_authority = authority
                model = build(factory, binding)
                assert (
                    await model.ainvoke("fixture question")
                ).content == "simulated answer"
                # Rotation affects future processes/admissions, not the admitted client.
                monkeypatch.setenv("FRED_TEST_INFERENCE_KEY", "rotated-fixture-key")
                assert build(factory, binding) is model
                assert (
                    await model.ainvoke("fixture question")
                ).content == "simulated answer"
                authority.close()
                with pytest.raises(AuthorityLostError):
                    await model.ainvoke("after termination")
            assert len(calls) == 2
            for request in calls:
                assert str(request.url) == "https://source.invalid/v1/chat/completions"
                assert (
                    request.headers["authorization"] == "Bearer synthetic-inference-key"
                )
                body = json.loads(request.content)
                assert body["model"] == "model"
                assert body["temperature"] == 0.2 and body["top_p"] == 0.8
                assert body.get("max_tokens", body.get("max_completion_tokens")) == 50
                assert body["reasoning_effort"] == "high"
            assert "synthetic-inference-key" not in caplog.text
            assert "rotated-fixture-key" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["source_id", "source_revision", "api_root", "credential_binding", "missing"],
)
async def test_provisioning_mismatch_is_refused_before_secret_read(monkeypatch, field):
    def forbidden(*args, **kwargs):
        pytest.fail(
            "No secret read or HTTP client construction before provisioning matches"
        )

    monkeypatch.setattr("fred_runtime.model_routing.provider.os.environ.get", forbidden)
    monkeypatch.setattr("fred_runtime.model_routing.provider.get_model", forbidden)
    local = provision().model_dump()
    if field != "missing":
        local[field] = (
            2
            if field == "source_revision"
            else "https://other.invalid/v1"
            if field == "api_root"
            else "other"
        )
    factory = RoutedChatModelFactory(
        credentials=()
        if field == "missing"
        else (InferenceCredentialBinding.model_validate(local),)
    )
    binding = admitted()
    with RunScope.open() as scope:
        authority = TurnAuthority(binding, None)
        authority.start(scope)
        scope.turn_authority = authority
        with pytest.raises(ModelRoutingError, match="provisioning"):
            build(factory, binding)


@pytest.mark.asyncio
async def test_cancelled_http_cannot_retry_after_turn_closes(monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()
    calls = []

    async def send(request):
        calls.append(request)
        started.set()
        try:
            await asyncio.Event().wait()
            return httpx.Response(200, json={})
        finally:
            cancelled.set()

    with httpx.Client() as sync:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(send)
        ) as asynchronous:
            monkeypatch.setattr(
                core_factory,
                "get_shared_stack",
                lambda *a, **k: (
                    TransportTuning(httpx.Limits(), httpx.Timeout(10)),
                    sync,
                    asynchronous,
                ),
            )
            monkeypatch.setenv("FRED_TEST_INFERENCE_KEY", "synthetic-inference-key")
            binding = admitted()
            with RunScope.open() as scope:
                authority = TurnAuthority(binding, None)
                authority.start(scope)
                scope.turn_authority = authority
                model = build(
                    RoutedChatModelFactory(credentials=(provision(),)), binding
                )
                task = asyncio.create_task(model.ainvoke("question"))
                await asyncio.wait_for(started.wait(), 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert cancelled.is_set()
                authority.close()
                with pytest.raises(AuthorityLostError):
                    await model.ainvoke("retry")
            assert len(calls) == 1


@pytest.mark.asyncio
async def test_missing_source_secret_does_not_use_global_key(monkeypatch):
    monkeypatch.delenv("FRED_TEST_INFERENCE_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-global-fixture")
    monkeypatch.setattr(
        "fred_runtime.model_routing.provider.get_model",
        lambda *a, **k: pytest.fail("must not construct a client"),
    )
    binding = admitted()
    with RunScope.open() as scope:
        authority = TurnAuthority(binding, None)
        authority.start(scope)
        scope.turn_authority = authority
        with pytest.raises(ModelRoutingError, match="credential is unavailable"):
            build(RoutedChatModelFactory(credentials=(provision(),)), binding)
