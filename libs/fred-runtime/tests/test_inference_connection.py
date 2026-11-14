# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One connection model, one path: the real factory, ChatOpenAI and guard.

No network: both shared pools answer on a local transport. No real gateway, Ollama
or Entra tenant is involved.
"""

import asyncio
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fred_core.model import factory as core_factory
from fred_core.model.http_clients import TransportTuning
from fred_runtime.app import session_title
from fred_runtime.app.config import InferenceCredentialBinding
from fred_runtime.model_routing import provider as routed_provider
from fred_runtime.model_routing.contracts import ModelRoutingError
from fred_runtime.model_routing.guard import NO_AUTH_BEARER
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message
from fred_runtime.runtime_support.run_scope import RunScope
from fred_runtime.support.reasoning_replay import (
    MistralReasoningReplayChatOpenAI,
    replays_native_reasoning,
)
from fred_runtime.support.thinking import keep_native_reasoning
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from fred_sdk.contracts.weaver import ModelConnection, WeaverRuntimeBinding
from langchain_core.load import dumpd
from langchain_openai import ChatOpenAI
from pydantic import SecretStr, ValidationError
from test_inference_admission import admitted, build
from test_reasoning_replay import _history, _thinking

CASES = {
    case["name"]: case
    for case in json.loads(
        (
            Path(__file__).parents[2]
            / "fred-sdk/tests/fixtures/inference_connections.json"
        ).read_text()
    )["valid"]
}
MISTRAL = "mistral"
MISTRAL_GATEWAY = "Mistral dialect behind a gateway"
OPENAI_GATEWAY = "OpenAI dialect on the same gateway root"
COMPATIBLE = "openai-compatible"
OLLAMA = "ollama"
GATEWAY = "gateway key alone"
APIM_CHAT = "APIM chat"
APIM_RESPONSES = "APIM Responses"
MATRIX = (MISTRAL, COMPATIBLE, OLLAMA, GATEWAY, APIM_CHAT, APIM_RESPONSES)
KEYED = (MISTRAL, COMPATIBLE)
NO_AUTH = (OLLAMA, GATEWAY)
ENTRA = (APIM_CHAT, APIM_RESPONSES)
WITH_GATEWAY = (GATEWAY, APIM_CHAT, APIM_RESPONSES)

API_KEY = "sentinel-api-key"  # pragma: allowlist secret
CLIENT_SECRET = "sentinel-entra-client-secret"  # pragma: allowlist secret
GATEWAY_KEY = "sentinel-gateway-key"  # pragma: allowlist secret
TOKEN = "sentinel-entra-token"
SENTINELS = (API_KEY, CLIENT_SECRET, GATEWAY_KEY, TOKEN)
# Environment variable names, not credentials.
API_KEY_ENV = "FRED_TEST_INFERENCE_API_KEY"  # pragma: allowlist secret
CLIENT_SECRET_ENV = "FRED_TEST_INFERENCE_CLIENT_SECRET"  # pragma: allowlist secret
GATEWAY_KEY_ENV = "FRED_TEST_INFERENCE_GATEWAY_KEY"  # pragma: allowlist secret
# What must never be picked up in place of the bound variables.
FOREIGN_ENV = {
    "AZURE_AD_CLIENT_SECRET": "foreign-client-secret",  # pragma: allowlist secret
    "AZURE_APIM_SUBSCRIPTION_KEY": "foreign-subscription",  # pragma: allowlist secret
    "AZURE_OPENAI_API_KEY": "foreign-azure-key",  # pragma: allowlist secret
    "OPENAI_API_KEY": "foreign-openai",  # pragma: allowlist secret
}
ABSENT = object()


def connection_of(name) -> ModelConnection:
    return ModelConnection.model_validate(CASES[name]["connection"])


def local_binding(name, **changes):
    connection = connection_of(name)
    data = {
        "credential_binding": connection.credential_binding,
        "api_root": connection.api_root,
    }
    if connection.auth.kind == "api_key":
        data["api_key_env"] = API_KEY_ENV
    if connection.auth.kind == "entra":
        data["client_secret_env"] = CLIENT_SECRET_ENV
    if connection.auth.gateway_key_header:
        data["gateway_key_env"] = GATEWAY_KEY_ENV
    data.update(changes)
    return InferenceCredentialBinding.model_validate(
        {key: value for key, value in data.items() if value is not None}
    )


def routed(name, **changes):
    return RoutedChatModelFactory(credentials=(local_binding(name, **changes),))


def admission_of(name, *, title=False, model=None, **options):
    case = CASES[name]
    model = model or case["model"]
    data = admitted().model_dump(mode="json")
    data["inference"]["connection"] = case["connection"]
    data["inference"]["selection"]["key"]["upstream_model_id"] = model
    data["inference"]["selection"]["options"].update(options)
    # The persisted title path requires a real conversation identifier.
    data["conversation_id"] = str(uuid4())
    if title:
        inference = json.loads(json.dumps(data["inference"]))
        inference["selection"]["key"]["upstream_model_id"] = "title-model"
        inference["selection"]["options"] = {"max_tokens": 128}
        data["title"] = {"attempt_id": str(uuid4()), "inference": inference}
    return WeaverRuntimeBinding.model_validate(data)


def url_of(name, model=None):
    return connection_of(name).request_url(model or CASES[name]["model"])


def bearer_of(name):
    kind = connection_of(name).auth.kind
    return {"api_key": API_KEY, "entra": TOKEN, "none": NO_AUTH_BEARER}[kind]


def valid_payload(name, **changes):
    model = CASES[name]["model"]
    if connection_of(name).wire == "openai_responses":
        payload = {
            "model": model,
            "input": [{"role": "user", "content": "q", "type": "message"}],
            "stream": True,
            "max_output_tokens": 50,
            "reasoning": {"effort": "high"},
            "temperature": 0.2,
            "top_p": 0.8,
        }
    else:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "q"}],
            "stream": True,
            "max_completion_tokens": 50,
            "reasoning_effort": "high",
            "temperature": 0.2,
            "top_p": 0.8,
        }
        if connection_of(name).dialect != "openai":
            payload["max_tokens"] = payload.pop("max_completion_tokens")
    payload.update(changes)
    return {key: value for key, value in payload.items() if value is not ABSENT}


def valid_request(name, *, url=None, verb="POST", bearer=None, headers=(), **body):
    return httpx.Request(
        verb,
        url or url_of(name),
        headers={
            "Authorization": f"Bearer {bearer or bearer_of(name)}",
            **dict(headers),
        },
        content=json.dumps(valid_payload(name, **body)).encode(),
    )


def body_of(request):
    return json.loads(request.content)


def _sse(*events):
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events)


def _reply(request):
    if "/responses" in str(request.url):
        response = {
            "id": "fixture",
            "object": "response",
            "created_at": 0,
            "model": "model",
            "output": [],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "status": "completed",
            "usage": {
                "input_tokens": 4,
                "output_tokens": 3,
                "total_tokens": 7,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        text = _sse(
            {
                "type": "response.output_text.delta",
                "content_index": 0,
                "delta": "simulated answer",
                "item_id": "item",
                "logprobs": [],
                "output_index": 0,
                "sequence_number": 1,
            },
            {"type": "response.completed", "response": response, "sequence_number": 2},
        )
    else:
        base = {
            "id": "fixture",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "model",
        }
        text = _sse(
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "simulated answer"},
                        "finish_reason": "stop",
                    }
                ],
            },
            {
                **base,
                "choices": [],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            },
        )
        text += "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=text)


def _mistral_reply(request):
    """Mistral's published request; usage comes unasked on the last chunk, with its choice."""
    body = body_of(request)
    if {"max_completion_tokens", "stream_options"} & body.keys() or not body["stream"]:
        return httpx.Response(422, json={"detail": "request outside the contract"})
    base = {
        "id": "fixture",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "model",
    }
    delta = {"role": "assistant", "content": "simulated answer"}
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=_sse(
            {
                **base,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            },
            {
                **base,
                "choices": [
                    {"index": 0, "delta": {"content": ""}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            },
        )
        + "data: [DONE]\n\n",
    )


def _compatible_reply(request):
    """Such a server ignores max_completion_tokens, and reports usage only when asked."""
    body = body_of(request)
    if "max_completion_tokens" in body or body["stream_options"] != {
        "include_usage": True
    }:
        return httpx.Response(422, json={"detail": "request outside the contract"})
    return _reply(request)


def serve(transport, name):
    """The fake provider checks the contract of this connection's dialect."""
    if connection_of(name).dialect == "mistral":
        transport.reply = _mistral_reply
    elif connection_of(name).dialect == "openai_compatible":
        transport.reply = _compatible_reply


class Credential:
    """Replaces only Entra; each instance is one ClientSecretCredential."""

    created: list["Credential"] = []
    tokens: list[str] = [TOKEN]
    error: Exception | None = None
    constructor_error: Exception | None = None

    def __init__(self, **kwargs):
        if Credential.constructor_error is not None:
            raise Credential.constructor_error
        self.kwargs = kwargs
        self.scopes: list[str] = []
        self.threads: list[int] = []
        self.position = 0
        Credential.created.append(self)

    def get_token(self, scope):
        self.scopes.append(scope)
        self.threads.append(threading.get_ident())
        if Credential.error is not None:
            raise Credential.error
        token = Credential.tokens[min(self.position, len(Credential.tokens) - 1)]
        self.position += 1
        return SimpleNamespace(token=token)


@pytest.fixture
def transport(monkeypatch):
    calls = []
    state = SimpleNamespace(calls=calls, reply=_reply)

    def send(request):
        calls.append(request)
        return state.reply(request)

    sync = httpx.Client(transport=httpx.MockTransport(send))
    asynchronous = httpx.AsyncClient(transport=httpx.MockTransport(send))
    monkeypatch.setattr(
        core_factory,
        "get_shared_stack",
        lambda *a, **k: (
            TransportTuning(httpx.Limits(), httpx.Timeout(10)),
            sync,
            asynchronous,
        ),
    )
    monkeypatch.setattr(Credential, "created", [])
    monkeypatch.setattr(Credential, "tokens", [TOKEN])
    monkeypatch.setattr(Credential, "error", None)
    monkeypatch.setattr(Credential, "constructor_error", None)
    monkeypatch.setattr(routed_provider, "ClientSecretCredential", Credential)
    monkeypatch.setenv(API_KEY_ENV, API_KEY)
    monkeypatch.setenv(CLIENT_SECRET_ENV, CLIENT_SECRET)
    monkeypatch.setenv(GATEWAY_KEY_ENV, GATEWAY_KEY)
    yield state
    sync.close()
    asyncio.run(asynchronous.aclose())


@contextmanager
def turn(binding):
    authority = TurnAuthority(binding, None)
    with RunScope.open() as scope:
        authority.start(scope)
        scope.turn_authority = authority
        yield authority


def checked_client(model) -> httpx.AsyncClient:
    """The admitted model's guarded client, for requests the SDK would not build."""
    return cast(httpx.AsyncClient, cast(ChatOpenAI, model).http_async_client)


async def invoked_model(name, binding, transport):
    """A guarded model that has already sent one request (any Entra token is issued)."""
    model = build(routed(name), binding)
    await model.ainvoke("question")
    transport.calls.clear()
    return model


def exception_chain(error):
    seen = []
    while error is not None and error not in seen:
        seen.append(error)
        error = error.__cause__ or error.__context__
    return seen


def assert_guard_refused(error):
    assert any(isinstance(item, AuthorityLostError) for item in exception_chain(error))


def assert_no_sentinel(text):
    for sentinel in SENTINELS:
        assert sentinel not in text


def forbid_secret_reads(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No secret read or client before provisioning matches")

    monkeypatch.setattr(routed_provider.os.environ, "get", forbidden)
    monkeypatch.setattr(routed_provider, "get_model", forbidden)
    monkeypatch.setattr(routed_provider, "ClientSecretCredential", forbidden)


def assert_authentication_headers(name, call):
    auth = connection_of(name).auth
    if auth.kind == "none":
        assert "authorization" not in call.headers
    else:
        assert call.headers["authorization"] == f"Bearer {bearer_of(name)}"
    if auth.gateway_key_header:
        assert call.headers[auth.gateway_key_header] == GATEWAY_KEY
    assert "api-key" not in call.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_turn_title_and_usage_share_one_path(
    name, transport, monkeypatch, caplog
):
    """URL, headers and body are exact; usage lands on the admitted offers."""
    caplog.set_level("DEBUG")
    serve(transport, name)
    binding = admission_of(name, title=True)
    factory = routed(name)
    persisted = []

    async def lease(**kwargs):
        return SimpleNamespace(token="fixture-workload")

    def persist(request):
        persisted.append(request)
        return httpx.Response(204)

    monkeypatch.setattr(
        session_title,
        "get_delegation_runtime",
        lambda: SimpleNamespace(workload_token_lease=lease),
    )
    context = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            user_id=binding.subject_id,
            session_id=binding.conversation_id,
            space_id=str(binding.space.id),
            agent_instance_id=str(binding.agent.instance_id),
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="r",
            actor="alice",
            tenant="test",
            environment=PortableEnvironment.DEV,
        ),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(persist)) as client:
        monkeypatch.setattr(
            session_title,
            "get_runtime_context",
            lambda: SimpleNamespace(
                config=SimpleNamespace(
                    control_plane_http_client=client,
                    control_plane_url="https://cp.invalid/api",
                )
            ),
        )
        with turn(binding) as authority:
            model = build(factory, binding)
            reply = await model.ainvoke("question")
            assert reply.text == "simulated answer"
            authority.record_usage(runtime_metadata_from_message(reply)[1])
            assert (
                await session_title.generate_session_title(
                    "question",
                    binding=context,
                    services=RuntimeServices(chat_model_factory=factory),
                )
                == binding.conversation_id
            )

    assert len(persisted) == 1
    assert json.loads(persisted[0].content)["title"] == "simulated answer"
    [turn_call, title_call] = transport.calls
    case = CASES[name]
    for call, model_id in ((turn_call, case["model"]), (title_call, "title-model")):
        assert call.method == "POST"
        assert str(call.url) == url_of(name, model_id)
        assert_authentication_headers(name, call)
        assert body_of(call)["model"] == model_id
    assert str(turn_call.url) == case["url"]
    question = {"content": "question", "role": "user"}
    if connection_of(name).wire == "openai_responses":
        assert body_of(turn_call) == {
            "model": case["model"],
            "stream": True,
            "input": [{**question, "type": "message"}],
            "max_output_tokens": 50,
            "reasoning": {"effort": "high"},
            "temperature": 0.2,
            "top_p": 0.8,
        }
        title_body = body_of(title_call)
        assert title_body["max_output_tokens"] == 128
        assert "reasoning" not in title_body
    elif connection_of(name).dialect == "mistral":
        assert body_of(turn_call) == {
            "model": case["model"],
            "stream": True,
            "messages": [question],
            "max_tokens": 50,
            "reasoning_effort": "high",
            "temperature": 0.2,
            "top_p": 0.8,
        }
        title_body = body_of(title_call)
        assert title_body["max_tokens"] == 128
    elif connection_of(name).dialect == "openai_compatible":
        assert body_of(turn_call) == {
            "model": case["model"],
            "stream": True,
            "messages": [question],
            "max_tokens": 50,
            "reasoning_effort": "high",
            "stream_options": {"include_usage": True},
            "temperature": 0.2,
            "top_p": 0.8,
        }
        title_body = body_of(title_call)
        assert title_body["max_tokens"] == 128
        assert "max_completion_tokens" not in title_body
    else:
        assert body_of(turn_call) == {
            "model": case["model"],
            "stream": True,
            "messages": [question],
            "max_completion_tokens": 50,
            "reasoning_effort": "high",
            "stream_options": {"include_usage": True},
            "temperature": 0.2,
            "top_p": 0.8,
        }
        title_body = body_of(title_call)
        assert title_body["max_completion_tokens"] == 128
    assert "reasoning_effort" not in title_body
    assert "temperature" not in title_body and "top_p" not in title_body

    assert binding.title is not None
    usage = authority.model_usage[binding.inference.selection.key]
    assert (usage.input_tokens, usage.output_tokens) == (4, 3)
    title_usage = authority.model_usage[binding.title.inference.selection.key]
    assert title_usage.input_tokens == 4
    assert_no_sentinel(caplog.text)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_every_shared_valid_connection_reaches_its_expected_url(name, transport):
    serve(transport, name)
    binding = admission_of(name)
    with turn(binding):
        await build(routed(name), binding).ainvoke("question")
    [call] = transport.calls
    assert str(call.url) == CASES[name]["url"]
    assert call.method == "POST"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_synchronous_path_uses_the_same_guarded_request(name, transport):
    serve(transport, name)
    binding = admission_of(name)
    with turn(binding):
        model = build(routed(name), binding)
        assert model.invoke("question").text == "simulated answer"
        assert "".join(chunk.text for chunk in model.stream("question")).strip() == (
            "simulated answer"
        )
    assert len(transport.calls) == 2
    for call in transport.calls:
        assert str(call.url) == url_of(name)
        assert_authentication_headers(name, call)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_the_client_is_always_the_plain_chat_openai_path(
    name, transport, monkeypatch
):
    captured = []
    real_get_model = routed_provider.get_model

    def spy(config, **kwargs):
        built = real_get_model(config, **kwargs)
        captured.append((config, type(built)))
        return built

    monkeypatch.setattr(routed_provider, "get_model", spy)
    binding = admission_of(name)
    with turn(binding):
        model = build(routed(name), binding)
    [(config, built_type)] = captured
    assert built_type is ChatOpenAI
    assert config.provider == "openai"
    assert isinstance(model, ChatOpenAI)
    assert model.cache is False
    assert model.max_retries == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,expected", [(COMPATIBLE, False), (APIM_RESPONSES, True), (APIM_CHAT, False)]
)
async def test_use_responses_api_is_never_automatic(name, expected, transport):
    binding = admission_of(name, model="gpt-5.5-pro", temperature=None)
    with turn(binding):
        model = cast(ChatOpenAI, build(routed(name), binding))
        assert model.use_responses_api is expected
        # A built-in tool or `include` would otherwise switch the API by itself.
        for payload in (
            {},
            {"tools": [{"type": "web_search_preview"}]},
            {"include": ["reasoning.encrypted_content"]},
        ):
            assert model._use_responses_api(payload) is expected


@pytest.mark.asyncio
async def test_the_dialect_decides_the_payload_behind_one_gateway_root(transport):
    """Same root and options: only `dialect` differs, and the fake tells them apart."""
    transport.reply = _mistral_reply
    binding = admission_of(MISTRAL_GATEWAY)
    with turn(binding):
        reply = await build(routed(MISTRAL_GATEWAY), binding).ainvoke("question")
    usage = runtime_metadata_from_message(reply)[1]
    assert usage is not None and usage["input_tokens"] == 4
    other = admission_of(OPENAI_GATEWAY)
    with turn(other):
        with pytest.raises(Exception, match="422"):
            await build(routed(OPENAI_GATEWAY), other).ainvoke("question")
    [mistral, openai] = transport.calls
    assert str(mistral.url) == str(openai.url)
    assert body_of(mistral)["max_tokens"] == 50
    assert body_of(openai)["max_completion_tokens"] == 50
    assert body_of(openai)["stream_options"] == {"include_usage": True}


def _with_dialect(name, dialect, **options):
    fields = admission_of(name, **options).model_dump(mode="json")
    fields["inference"]["connection"]["dialect"] = dialect
    return WeaverRuntimeBinding.model_validate(fields)


@pytest.mark.asyncio
async def test_openai_compatible_sends_no_ceiling_without_an_admitted_one(transport):
    serve(transport, COMPATIBLE)
    binding = admission_of(COMPATIBLE, max_tokens=None)
    with turn(binding):
        await build(routed(COMPATIBLE), binding).ainvoke("question")
    body = body_of(transport.calls[0])
    assert "max_tokens" not in body and "max_completion_tokens" not in body
    assert "extra_body" not in body


@pytest.mark.asyncio
async def test_openai_compatible_changes_nothing_on_responses(transport):
    binding = _with_dialect(APIM_RESPONSES, "openai_compatible")
    with turn(binding):
        await build(routed(APIM_RESPONSES), binding).ainvoke("question")
    body = body_of(transport.calls[0])
    assert body["max_output_tokens"] == 50
    assert "max_tokens" not in body and "extra_body" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [COMPATIBLE, APIM_CHAT, APIM_RESPONSES, GATEWAY])
async def test_a_temperature_dropped_by_the_client_refuses_the_model(name, transport):
    """The fixed refusal comes before any request, instead of the guard's."""
    binding = admission_of(name, model="gpt-5", temperature=0.2)
    with turn(binding) as authority:
        with pytest.raises(ModelRoutingError) as caught:
            build(routed(name), binding)
        assert authority.models == {}
    assert caught.value.user_message == routed_provider._TEMPERATURE_REFUSED
    assert not isinstance(caught.value, AuthorityLostError)
    assert transport.calls == []
    assert all(credential.scopes == [] for credential in Credential.created)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_id,temperature",
    [("gpt-5", None), ("gpt-5", 1.0), ("gpt-5-chat-latest", 0.2), ("gpt-4o", 0.2)],
)
async def test_a_temperature_the_client_keeps_reaches_the_request(
    model_id, temperature, transport
):
    serve(transport, COMPATIBLE)
    binding = admission_of(COMPATIBLE, model=model_id, temperature=temperature)
    with turn(binding):
        await build(routed(COMPATIBLE), binding).ainvoke("question")
    assert body_of(transport.calls[0]).get("temperature") == temperature


@pytest.mark.asyncio
async def test_a_temperature_dropped_when_serializing_refuses_the_model(transport):
    """The client keeps it at construction and removes it from the Responses payload."""
    kept = ChatOpenAI(
        model="gpt-5",
        temperature=1,
        use_responses_api=True,
        api_key=SecretStr(API_KEY),
    )
    assert kept.temperature == 1
    binding = admission_of(
        APIM_RESPONSES, model="gpt-5", temperature=1.0, reasoning_effort="high"
    )
    with turn(binding) as authority:
        with pytest.raises(ModelRoutingError) as caught:
            build(routed(APIM_RESPONSES), binding)
        assert authority.models == {}
    assert caught.value.user_message == routed_provider._TEMPERATURE_REFUSED
    assert not isinstance(caught.value, AuthorityLostError)
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_id,temperature,effort",
    [
        ("gpt-5", None, "high"),
        ("gpt-4o", 0.2, None),
        ("gpt-5-chat-latest", 0.2, None),
    ],
)
async def test_responses_sends_exactly_the_admitted_temperature(
    model_id, temperature, effort, transport
):
    binding = admission_of(
        APIM_RESPONSES, model=model_id, temperature=temperature, reasoning_effort=effort
    )
    with turn(binding):
        model = build(routed(APIM_RESPONSES), binding)
        await model.ainvoke("question")
        model.invoke("question")
    assert len(transport.calls) == 2
    for call in transport.calls:
        assert body_of(call).get("temperature") == temperature


@pytest.mark.asyncio
async def test_chat_completions_keeps_the_temperature_responses_would_drop(transport):
    serve(transport, COMPATIBLE)
    binding = admission_of(
        COMPATIBLE, model="gpt-5", temperature=1.0, reasoning_effort="high"
    )
    with turn(binding):
        await build(routed(COMPATIBLE), binding).ainvoke("question")
    assert body_of(transport.calls[0])["temperature"] == 1.0


@pytest.mark.asyncio
async def test_mistral_payload_still_replays_reasoning(transport):
    transport.reply = _mistral_reply
    binding = admission_of(MISTRAL_GATEWAY)
    with turn(binding):
        model = build(routed(MISTRAL_GATEWAY), binding)
        await model.ainvoke(keep_native_reasoning(_history()))
    [call] = transport.calls
    wire = body_of(call)["messages"]
    assert wire[1]["content"] == [
        _thinking("old plan"),
        {"type": "text", "text": "old answer"},
    ]
    assert wire[3]["content"] == [_thinking("read the doc")]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_lost_authority_sends_nothing(name, transport):
    binding = admission_of(name)
    with turn(binding) as authority:
        model = build(routed(name), binding)
        await model.ainvoke("question")
        transport.calls.clear()
        client = checked_client(model)
        authority.close()
        with pytest.raises(AuthorityLostError):
            await model.ainvoke("after termination")
        with pytest.raises(AuthorityLostError):
            await client.send(valid_request(name))
    assert transport.calls == []


def _other_url(name):
    """Every way of being one character away from the single URL of this connection."""
    url = url_of(name)
    connection = connection_of(name)
    host = connection.api_root.split("/")[2]
    path = connection.api_root.split(host, 1)[1]
    scheme = connection.api_root.split(":")[0]
    other_scheme = "https" if scheme == "http" else "http"
    urls = {
        "origin": url.replace(host, "other.invalid"),
        "scheme": url.replace(f"{scheme}://", f"{other_scheme}://"),
        "port": url.replace(host, f"{host.split(':')[0]}:8443"),
        "path": url.replace(path, "/other"),
        "trailing-slash": url.replace(
            "/chat/completions", "/chat/completions/"
        ).replace("/responses", "/responses/"),
        "extra-query": f"{url}{'&' if '?' in url else '?'}extra=1",
        # The former tolerance: the other wire of the same root.
        "other-wire": (
            url.replace("/responses", "/chat/completions")
            if connection.wire == "openai_responses"
            else url.replace("/chat/completions", "/responses")
        ),
    }
    if connection.api_version:
        urls["no-query"] = url.split("?")[0]
        urls["api-version"] = url.replace(connection.api_version, "2099-01-01")
    else:
        urls["api-version"] = f"{url}?api-version=2099-01-01"
    if connection.route == "azure_deployment":
        urls["other-deployment"] = url.replace(CASES[name]["model"], "other")
        urls["without-deployment"] = (
            f"{connection.api_root}/chat/completions?api-version={connection.api_version}"
        )
    else:
        urls["with-deployment"] = url.replace(
            "/chat/completions", "/deployments/model/chat/completions"
        ).replace("/responses", "/deployments/model/responses")
    return urls


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_any_other_destination_is_refused(name, transport):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        client = checked_client(model)
        for label, url in _other_url(name).items():
            assert url != url_of(name), label
            with pytest.raises(AuthorityLostError):
                await client.send(valid_request(name, url=url))
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_only_post_is_allowed(name, transport):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(valid_request(name, verb="GET"))
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_exact_request_passes_the_transport_guard(name, transport):
    """Every refusal below departs from this one by a single element."""
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        await checked_client(model).send(valid_request(name))
    [call] = transport.calls
    assert_authentication_headers(name, call)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
@pytest.mark.parametrize(
    "body",
    [
        {"model": "other"},
        {"model": None},
        {"model": ABSENT},
        {"temperature": 0.9},
        {"temperature": ABSENT},
        {"top_p": 0.1},
    ],
    ids=["other-model", "null-model", "no-model", "temperature", "no-temp", "top_p"],
)
async def test_body_outside_the_admission_is_refused(name, body, transport):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(valid_request(name, **body))
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,body",
    [
        (MISTRAL, {"max_tokens": 51}),
        (MISTRAL, {"max_tokens": ABSENT}),
        (MISTRAL_GATEWAY, {"max_tokens": 51}),
        (OPENAI_GATEWAY, {"max_completion_tokens": 51}),
        (OPENAI_GATEWAY, {"max_completion_tokens": True}),
        (OPENAI_GATEWAY, {"max_completion_tokens": ABSENT}),
        (COMPATIBLE, {"max_tokens": 51}),
        (COMPATIBLE, {"max_tokens": True}),
        (COMPATIBLE, {"max_tokens": ABSENT}),
        (OLLAMA, {"max_tokens": 51}),
        (COMPATIBLE, {"reasoning_effort": "low"}),
        (COMPATIBLE, {"reasoning_effort": None}),
        (COMPATIBLE, {"reasoning_effort": ABSENT}),
        (COMPATIBLE, {"reasoning": {"effort": "high"}}),
        (APIM_RESPONSES, {"max_output_tokens": 51}),
        (APIM_RESPONSES, {"max_output_tokens": ABSENT}),
        (APIM_RESPONSES, {"reasoning_effort": "high"}),
        (APIM_RESPONSES, {"reasoning": None}),
        (APIM_RESPONSES, {"reasoning": ABSENT}),
        (APIM_RESPONSES, {"reasoning": {"effort": "low"}}),
        (APIM_RESPONSES, {"reasoning": {"effort": "high", "summary": "auto"}}),
    ],
)
async def test_tokens_and_reasoning_outside_the_admission_are_refused(
    name, body, transport
):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(valid_request(name, **body))
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,body",
    [
        (COMPATIBLE, {"reasoning_effort": "high"}),
        (COMPATIBLE, {"reasoning": {"effort": "high"}}),
        (APIM_RESPONSES, {"reasoning": {"effort": "high"}}),
        (APIM_RESPONSES, {"reasoning": None}),
        (APIM_RESPONSES, {"reasoning_effort": "high"}),
    ],
)
async def test_reasoning_stays_absent_without_an_admitted_effort(name, body, transport):
    binding = admission_of(name, reasoning_effort=None)
    with turn(binding):
        model = build(routed(name), binding)
        await model.ainvoke("question")
        [sent] = transport.calls
        assert "reasoning" not in body_of(sent)
        assert "reasoning_effort" not in body_of(sent)
        transport.calls.clear()
        clean: dict[str, Any] = {"reasoning": ABSENT, "reasoning_effort": ABSENT}
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(valid_request(name, **{**clean, **body}))
        await checked_client(model).send(valid_request(name, **clean))
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
@pytest.mark.parametrize(
    "authorization",
    ["Basic Zm9yZWlnbg==", "Bearer never-issued", "Bearer", ""],
    ids=["basic", "unissued", "no-token", "empty"],
)
async def test_foreign_authorization_is_refused(name, authorization, transport):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        request = valid_request(name, headers={"Authorization": authorization})
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(request)
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_altered_bearer_syntax_is_refused(name, transport):
    binding = admission_of(name)
    bearer = bearer_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        for value in (f"bearer {bearer}", f"Bearer  {bearer}"):
            with pytest.raises(AuthorityLostError):
                await checked_client(model).send(
                    valid_request(name, headers={"Authorization": value})
                )
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NO_AUTH)
async def test_no_auth_requires_the_constant_then_removes_it(name, transport):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
        request = valid_request(name)
        del request.headers["authorization"]
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(request)
        assert transport.calls == []
        await checked_client(model).send(valid_request(name))
    [call] = transport.calls
    assert "authorization" not in call.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
@pytest.mark.parametrize("header", ["api-key", "API-Key"])
async def test_preexisting_api_key_is_refused_from_the_real_client(
    name, header, transport
):
    binding = admission_of(name)
    with turn(binding):
        model = build(routed(name), binding)
        with pytest.raises(Exception) as caught:
            await model.ainvoke("question", extra_headers={header: "preexisting"})
    assert transport.calls == []
    assert_guard_refused(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", WITH_GATEWAY)
async def test_preexisting_gateway_header_is_refused_from_the_real_client(
    name, transport
):
    header = connection_of(name).auth.gateway_key_header
    assert header
    binding = admission_of(name)
    with turn(binding):
        model = build(routed(name), binding)
        for variant in (header, header.lower(), header.upper()):
            with pytest.raises(Exception) as caught:
                await model.ainvoke("question", extra_headers={variant: "preexisting"})
            assert_guard_refused(caught.value)
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", WITH_GATEWAY)
async def test_gateway_key_is_set_by_the_guard_only(name, transport):
    binding = admission_of(name)
    with turn(binding):
        model = await invoked_model(name, binding, transport)
    chat = cast(ChatOpenAI, model)
    assert GATEWAY_KEY not in json.dumps(chat.default_headers or {})
    for client in (chat.root_client, chat.root_async_client):
        assert GATEWAY_KEY not in repr(dict(client.default_headers))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
@pytest.mark.parametrize(
    "changes",
    [{"api_root": "https://other.invalid/v1"}, {"credential_binding": "other"}],
    ids=["api_root", "credential_binding"],
)
async def test_other_destination_or_binding_is_refused_before_secret_read(
    name, changes, monkeypatch
):
    factory = routed(name, **changes)
    forbid_secret_reads(monkeypatch)
    binding = admission_of(name)
    with turn(binding), pytest.raises(ModelRoutingError, match="provisioning"):
        build(factory, binding)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,changes",
    [
        # Too many variables for the admitted authentication.
        (OLLAMA, {"api_key_env": API_KEY_ENV}),
        (OLLAMA, {"client_secret_env": CLIENT_SECRET_ENV}),
        (OLLAMA, {"gateway_key_env": GATEWAY_KEY_ENV}),
        (COMPATIBLE, {"client_secret_env": CLIENT_SECRET_ENV}),
        (COMPATIBLE, {"gateway_key_env": GATEWAY_KEY_ENV}),
        (GATEWAY, {"api_key_env": API_KEY_ENV}),
        (APIM_CHAT, {"api_key_env": API_KEY_ENV}),
        # Too few.
        (COMPATIBLE, {"api_key_env": None}),
        (GATEWAY, {"gateway_key_env": None}),
        (APIM_CHAT, {"client_secret_env": None}),
        (APIM_CHAT, {"gateway_key_env": None}),
    ],
)
async def test_binding_variables_must_exactly_match_auth(name, changes, monkeypatch):
    factory = routed(name, **changes)
    forbid_secret_reads(monkeypatch)
    binding = admission_of(name)
    with turn(binding), pytest.raises(ModelRoutingError, match="provisioning"):
        build(factory, binding)


def test_duplicate_credential_binding_is_refused():
    with pytest.raises(ModelRoutingError, match="Duplicate"):
        RoutedChatModelFactory(
            credentials=(local_binding(COMPATIBLE), local_binding(COMPATIBLE))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_id", ["a/b", "a b", "a?x=1", "a%2fb", "a#b", "é", "a\nb", "a:b", ".", ".."]
)
async def test_invalid_deployment_identifier_is_refused_before_secret_read(
    model_id, monkeypatch
):
    factory = routed(APIM_CHAT)
    forbid_secret_reads(monkeypatch)
    binding = admission_of(APIM_CHAT, model=model_id)
    with turn(binding), pytest.raises(ModelRoutingError, match="identifier"):
        build(factory, binding)


@pytest.mark.asyncio
async def test_deployment_rule_does_not_restrict_a_model_in_the_body(transport):
    binding = admission_of(OLLAMA, model="org/model:tag")
    with turn(binding):
        await build(routed(OLLAMA), binding).ainvoke("question")
    assert body_of(transport.calls[0])["model"] == "org/model:tag"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,missing",
    [
        (COMPATIBLE, API_KEY_ENV),
        (GATEWAY, GATEWAY_KEY_ENV),
        (APIM_CHAT, CLIENT_SECRET_ENV),
        (APIM_CHAT, GATEWAY_KEY_ENV),
    ],
)
async def test_missing_bound_secret_has_no_fallback(
    name, missing, transport, monkeypatch
):
    monkeypatch.delenv(missing)
    for variable, value in FOREIGN_ENV.items():
        monkeypatch.setenv(variable, value)
    monkeypatch.setattr(
        routed_provider,
        "get_model",
        lambda *a, **k: pytest.fail("must not construct a client"),
    )
    binding = admission_of(name)
    with (
        turn(binding),
        pytest.raises(ModelRoutingError, match="credential is unavailable"),
    ):
        build(routed(name), binding)
    assert Credential.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_foreign_environment_never_reaches_the_destination(
    name, transport, monkeypatch
):
    for variable, value in FOREIGN_ENV.items():
        monkeypatch.setenv(variable, value)
    binding = admission_of(name)
    with turn(binding):
        await build(routed(name), binding).ainvoke("question")
    [call] = transport.calls
    assert_authentication_headers(name, call)
    for value in FOREIGN_ENV.values():
        assert value not in str(dict(call.headers))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_redirect_is_never_followed(name, transport):
    transport.reply = lambda request: httpx.Response(
        302, headers={"location": "https://elsewhere.invalid/stolen"}
    )
    binding = admission_of(name)
    with turn(binding):
        model = build(routed(name), binding)
        with pytest.raises(Exception, match="302|[Rr]edirect|Error code"):
            await model.ainvoke("question")
        assert len(transport.calls) == 1
        response = await checked_client(model).send(
            valid_request(name), follow_redirects=True
        )
    assert response.status_code == 302
    assert len(transport.calls) == 2
    assert all("elsewhere" not in str(call.url) for call in transport.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ENTRA)
async def test_two_tokens_in_one_turn_pass(name, transport, monkeypatch):
    monkeypatch.setattr(Credential, "tokens", ["token-one", "token-two"])
    binding = admission_of(name)
    with turn(binding):
        model = build(routed(name), binding)
        await model.ainvoke("first")
        await model.ainvoke("second")
    assert [call.headers["authorization"] for call in transport.calls] == [
        "Bearer token-one",
        "Bearer token-two",
    ]


@pytest.mark.asyncio
async def test_token_issued_to_another_model_is_refused(transport, monkeypatch):
    monkeypatch.setattr(Credential, "tokens", ["first-turn", "second-turn"])
    factory = routed(APIM_CHAT)
    first = admission_of(APIM_CHAT)
    with turn(first):
        await build(factory, first).ainvoke("question")
    transport.calls.clear()
    second = admission_of(APIM_CHAT)
    with turn(second):
        model = build(factory, second)
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(
                valid_request(APIM_CHAT, bearer="first-turn")
            )
    assert transport.calls == []


@pytest.mark.asyncio
async def test_token_not_yet_issued_is_refused(transport):
    binding = admission_of(APIM_CHAT)
    with turn(binding):
        model = build(routed(APIM_CHAT), binding)
        # Nothing asked Entra yet: even the token it would return is not accepted.
        with pytest.raises(AuthorityLostError):
            await checked_client(model).send(valid_request(APIM_CHAT))
    assert transport.calls == []


@pytest.mark.asyncio
async def test_one_credential_for_two_turns(transport):
    factory = routed(APIM_CHAT)
    for _ in range(2):
        binding = admission_of(APIM_CHAT)
        with turn(binding):
            await build(factory, binding).ainvoke("question")
    [credential] = Credential.created
    assert credential.kwargs["client_secret"] == CLIENT_SECRET
    assert credential.kwargs["tenant_id"] == "tenant"
    assert credential.kwargs["client_id"] == "client"
    assert credential.scopes == ["api://gateway/.default"] * 2


@pytest.mark.asyncio
async def test_a_credential_belongs_to_binding_tenant_and_client(transport):
    data = json.loads(json.dumps(CASES[APIM_CHAT]["connection"]))
    data["auth"]["tenant_id"] = "other-tenant"
    factory = routed(APIM_CHAT)
    for connection in (CASES[APIM_CHAT]["connection"], data):
        fields = admission_of(APIM_CHAT).model_dump(mode="json")
        fields["inference"]["connection"] = connection
        binding = WeaverRuntimeBinding.model_validate(fields)
        with turn(binding):
            await build(factory, binding).ainvoke("question")
    assert [item.kwargs["tenant_id"] for item in Credential.created] == [
        "tenant",
        "other-tenant",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ENTRA)
async def test_token_provider_leaves_the_event_loop(name, transport):
    binding = admission_of(name)
    with turn(binding):
        await build(routed(name), binding).ainvoke("question")
    [thread] = Credential.created[0].threads
    assert thread != threading.get_ident()


def test_real_credential_uses_fixed_authority_and_timeouts(monkeypatch):
    """The real class, without any request: nothing here is configurable."""
    monkeypatch.setenv("AZURE_AUTHORITY_HOST", "https://attacker.invalid")
    monkeypatch.setenv(CLIENT_SECRET_ENV, CLIENT_SECRET)
    factory = routed(APIM_CHAT)
    connection = connection_of(APIM_CHAT)
    credential = factory._entra_credential(local_binding(APIM_CHAT), connection.auth)
    assert credential._client is not None
    assert credential._authority == "https://login.microsoftonline.com"
    transport = cast(Any, credential._client._pipeline._transport)
    config = transport.connection_config
    assert (config.timeout, config.read_timeout) == (5, 15)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MATRIX)
async def test_secrets_stay_out_of_every_surface(name, transport, caplog):
    caplog.set_level("DEBUG")
    binding = admission_of(name)
    factory = routed(name)
    with turn(binding) as authority:
        model, selection = factory._build_admitted(authority, binding.inference)
        await model.ainvoke("question")
        with pytest.raises(Exception) as refused:
            await model.ainvoke("question", extra_headers={"api-key": "x"})
    assert transport.calls, "the sentinels were really used"
    surfaces = [
        repr(model),
        str(model),
        json.dumps(dumpd(model), default=str),
        json.dumps(model._serialized, default=str),
        selection.model_dump_json(),
        repr(selection),
        caplog.text,
    ]
    for item in exception_chain(refused.value):
        surfaces.extend((str(item), repr(item)))
    for surface in surfaces:
        assert_no_sentinel(surface)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ENTRA)
@pytest.mark.parametrize("failure", ["get_token", "constructor"])
async def test_entra_failure_is_fixed_and_carries_nothing(
    name, failure, transport, monkeypatch, caplog
):
    caplog.set_level("DEBUG")
    leaky = RuntimeError(f"AADSTS failure {CLIENT_SECRET} {GATEWAY_KEY} {TOKEN}")
    binding = admission_of(name)
    if failure == "constructor":
        monkeypatch.setattr(Credential, "constructor_error", leaky)
        with turn(binding), pytest.raises(ModelRoutingError) as caught:
            build(routed(name), binding)
    else:
        monkeypatch.setattr(Credential, "error", leaky)
        with turn(binding):
            model = build(routed(name), binding)
            with pytest.raises(ModelRoutingError) as caught:
                await model.ainvoke("question")
    error = caught.value
    assert error.__cause__ is None and error.__context__ is None
    assert error.__suppress_context__ is True
    assert transport.calls == []
    assert error.user_message == routed_provider._ENTRA_UNAVAILABLE
    for item in exception_chain(error):
        assert_no_sentinel(str(item))
        assert_no_sentinel(repr(item))
    assert_no_sentinel(caplog.text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dialect,model_id,replayed",
    [
        ("mistral", "any-model", True),
        ("openai", "mistral-small-latest", False),
        ("mistral", "mistral-small-latest", True),
    ],
)
@pytest.mark.parametrize("name", [COMPATIBLE, GATEWAY, MISTRAL])
async def test_only_the_dialect_activates_the_replay(
    name, dialect, model_id, replayed, transport
):
    binding = _with_dialect(name, dialect, model=model_id)
    with turn(binding):
        model = build(routed(name), binding)
    assert isinstance(model, MistralReasoningReplayChatOpenAI) is replayed
    assert replays_native_reasoning(model) is replayed


@pytest.mark.parametrize(
    "changes",
    [
        {"api_root": "https://gateway.invalid/v1/"},
        {"api_root": "https://Gateway.invalid/v1"},
        {"api_root": "https://user:pw@gateway.invalid/v1"},  # pragma: allowlist secret
        {"api_root": "https://gateway.invalid/v1?a=b"},
        {"api_key_env": "not-a-name"},  # pragma: allowlist secret
        {"client_secret_env": "1NOPE"},  # pragma: allowlist secret
        {"gateway_key_env": "A B"},
        {"credential_binding": ""},
        {"source_id": "source"},
        {"source_revision": 1},
        {"unknown": "field"},
    ],
)
def test_binding_refuses_an_invalid_form(changes):
    with pytest.raises(ValidationError):
        InferenceCredentialBinding.model_validate(
            {
                "credential_binding": "binding",
                "api_root": "https://gateway.invalid/v1",
                **changes,
            }
        )


@pytest.mark.asyncio
async def test_binding_is_required_even_without_a_secret(monkeypatch):
    """Authentication none still attests its destination; every variable is optional."""
    local = local_binding(OLLAMA)
    assert (local.api_key_env, local.client_secret_env, local.gateway_key_env) == (
        None,
        None,
        None,
    )
    binding = admission_of(OLLAMA)
    forbid_secret_reads(monkeypatch)
    with turn(binding), pytest.raises(ModelRoutingError, match="provisioning"):
        build(RoutedChatModelFactory(credentials=()), binding)
