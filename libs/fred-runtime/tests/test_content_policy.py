# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

import asyncio
import json

import httpx
import pytest
from fred_core.model.azure_chat import FredAzureChatOpenAI
from fred_core.model.openai_chat import FredChatOpenAI
from fred_runtime.app.execution_diagnostics import classify_terminal_failure
from fred_runtime.runtime_support.content_policy import (
    ContentPolicyError,
    check_model_message,
    normalize_model_error,
)
from google.genai.types import GenerateContentResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai.chat_models import _response_to_result
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

APIM_FILTER = {
    "error": {
        "code": "content_filter",
        "param": "prompt",
        "message": "raw provider message omitted from Fred's notice",
        "innererror": {
            "code": "ResponsibleAIPolicyViolation",
            "content_filter_result": {
                "self_harm": {"filtered": True, "severity": "medium"},
                "violence": {"filtered": False, "severity": "safe"},
            },
        },
    }
}
INPUT = [HumanMessage(content="synthetic input")]


class _Decision(BaseModel):
    decision: str


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [FredChatOpenAI, FredAzureChatOpenAI])
@pytest.mark.parametrize("outcome", ["ok", "filter", "refusal"])
async def test_structured_chat_preserves_parsed_output_and_policy_markers(
    provider, outcome
):
    message = {"role": "assistant", "content": '{"decision":"ok"}'}
    if outcome == "refusal":
        message = {"role": "assistant", "content": None, "refusal": "synthetic refusal"}
    finish = "content_filter" if outcome == "filter" else "stop"
    packet = {
        "id": "synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": "synthetic",
        "choices": [{"index": 0, "finish_reason": finish, "message": message}],
    }
    azure_kwargs = (
        {"azure_endpoint": "https://azure.example.test", "api_version": "2024-06-01"}
        if provider is FredAzureChatOpenAI
        else {}
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=packet))
    ) as client:
        model = provider(
            api_key="synthetic",
            model="synthetic",
            http_async_client=client,
            **azure_kwargs,
        )
        structured = model.with_structured_output(
            _Decision, include_raw=True, method="json_schema"
        )
        if outcome == "filter":
            with (
                pytest.raises(ContentPolicyError) as caught,
                normalize_model_error(model, INPUT),
            ):
                await structured.ainvoke(INPUT)
            assert caught.value.notice.kind == "output_filtered"
        else:
            result = await structured.ainvoke(INPUT)
            if outcome == "ok":
                assert result["parsed"] == _Decision(decision="ok")
            else:
                with pytest.raises(ContentPolicyError) as caught:
                    check_model_message(model, result["raw"], INPUT)
                assert caught.value.notice.kind == "model_refusal"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [FredChatOpenAI, FredAzureChatOpenAI])
async def test_chat_stream_preserves_structured_refusal(provider):
    packet = {
        "id": "synthetic",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "synthetic",
        "choices": [
            {
                "index": 0,
                "finish_reason": None,
                "delta": {"refusal": "synthetic refusal"},
            }
        ],
    }
    response = httpx.Response(
        200,
        text=f"data: {json.dumps(packet)}\n\ndata: [DONE]\n\n",
        headers={"content-type": "text/event-stream"},
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response)
    ) as client:
        kwargs = (
            {
                "azure_endpoint": "https://azure.example.test",
                "api_version": "2024-06-01",
            }
            if provider is FredAzureChatOpenAI
            else {}
        )
        model = provider(
            api_key="synthetic", model="synthetic", http_async_client=client, **kwargs
        )
        with (
            pytest.raises(ContentPolicyError) as caught,
            normalize_model_error(model, INPUT),
        ):
            async for _ in model.astream(INPUT):
                pytest.fail(
                    "Structured refusal text must not be returned as ordinary output"
                )
        assert caught.value.notice.kind == "model_refusal"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "responses", "body", "categories"),
    [
        ("azure-apim", False, APIM_FILTER, ("self_harm",)),
        ("azure-openai", True, {"error": {"code": "content_filter"}}, ()),
        (
            "azure-apim",
            False,
            {"error": {"code": "invalid_parameter", "param": "prompt"}},
            None,
        ),
        ("azure-apim", False, {"error": {"code": "content_filter"}}, None),
    ],
)
async def test_azure_http_400_via_pinned_sdk(provider, responses, body, categories):
    attempts = []

    def reply(request):
        attempts.append(request.url.path)
        return httpx.Response(400, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        model = FredAzureChatOpenAI(
            api_key="synthetic",
            base_url="https://example.test/openai/v1/",
            api_version="2024-06-01",
            model="synthetic",
            use_responses_api=responses,
            http_async_client=client,
            metadata={"fred_model_provider": provider},
        )
        from openai import BadRequestError

        expected = BadRequestError if categories is None else ContentPolicyError
        with pytest.raises(expected) as raised, normalize_model_error(model, INPUT):
            await model.ainvoke(INPUT)
    assert len(attempts) == 1
    assert attempts[0].endswith("/responses" if responses else "/chat/completions")
    assert classify_terminal_failure(raised.value, "execution") == "http_400"
    if isinstance(raised.value, ContentPolicyError):
        assert raised.value.notice.kind == "prompt_blocked"
        assert raised.value.notice.categories == categories
        assert raised.value.notice.origin == "user_message"
        assert "raw provider" not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_azure_terminal_output_via_pinned_sdk(stream):
    choice = {
        "index": 0,
        "finish_reason": "content_filter",
        "content_filter_results": {"violence": {"filtered": True, "severity": "high"}},
    }
    body = {"id": "fixture", "model": "fixture", "created": 0}
    if stream:
        terminal = {
            **body,
            "choices": [{**choice, "delta": {}}],
            "object": "chat.completion.chunk",
        }
        response = httpx.Response(
            200,
            text=f"data: {json.dumps(terminal)}\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )
    else:
        response = httpx.Response(
            200,
            json={
                **body,
                "object": "chat.completion",
                "choices": [
                    {**choice, "message": {"role": "assistant", "content": None}}
                ],
            },
        )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response)
    ) as client:
        model = FredAzureChatOpenAI(
            api_key="synthetic",
            azure_endpoint="https://example.test",
            api_version="2024-06-01",
            model="synthetic",
            http_async_client=client,
        )
        with (
            pytest.raises(ContentPolicyError) as caught,
            normalize_model_error(model, INPUT),
        ):
            if stream:
                async for _ in model.astream(INPUT):
                    pytest.fail("The filtered terminal chunk must not be returned")
            else:
                await model.ainvoke(INPUT)
    assert caught.value.notice.kind == "output_filtered"
    assert caught.value.notice.categories == ("violence",)
    assert caught.value.notice.origin is None


@pytest.mark.parametrize(
    ("feedback", "candidate", "kind", "categories"),
    [
        (
            {
                "blockReason": "SAFETY",
                "safetyRatings": [
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "blocked": True}
                ],
            },
            None,
            "prompt_blocked",
            ("hate",),
        ),
        (None, {"finishReason": "RECITATION"}, "output_filtered", ()),
        (None, {"finishReason": "MAX_TOKENS"}, None, ()),
    ],
)
def test_gemini_uses_structured_sdk_signals(feedback, candidate, kind, categories):
    response = GenerateContentResponse.model_validate(
        {"promptFeedback": feedback, "candidates": [candidate] if candidate else []}
    )
    result = _response_to_result(response, stream=True)
    generation = result.generations[0]
    message = generation.message.model_copy(
        update={
            "response_metadata": {
                **generation.message.response_metadata,
                **(generation.generation_info or {}),
            }
        }
    )
    model = FakeListChatModel(
        responses=["unused"], metadata={"fred_model_provider": "vertex-ai"}
    )
    if kind is None:
        check_model_message(model, message, INPUT)
    else:
        with pytest.raises(ContentPolicyError) as caught:
            check_model_message(
                model, message, [SystemMessage(content="instructions"), *INPUT]
            )
        assert caught.value.notice.kind == kind
        assert caught.value.notice.categories == categories
        assert caught.value.notice.origin is None


@pytest.mark.asyncio
async def test_mistral_confirmed_guardrail_and_evaluation_failure_are_distinct():
    packets = [
        {
            "guardrails": {
                "results": {
                    "moderation_llm_v2": {
                        "action": "block",
                        "violated": True,
                        "decisions": {
                            "selfharm": {"violated": True},
                            "sexual": {"violated": False},
                        },
                    }
                }
            }
        },
        {
            "code": 3201,
            "guardrails": [{"moderation_llm_v2": {"action": "block", "error": {}}}],
        },
    ]
    async with httpx.AsyncClient(
        base_url="https://mistral.example.test/v1",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, json=packets.pop(0))
        ),
    ) as client:
        model = ChatMistralAI(
            api_key="synthetic",
            async_client=client,
            model="synthetic",
            metadata={"fred_model_provider": "vertex-ai-model-garden"},
        )
        with (
            pytest.raises(ContentPolicyError) as caught,
            normalize_model_error(model, INPUT),
        ):
            await model.ainvoke(INPUT)
        assert caught.value.notice.categories == ("self_harm",)
        with pytest.raises(httpx.HTTPStatusError), normalize_model_error(model, INPUT):
            await model.ainvoke(INPUT)


@pytest.mark.asyncio
async def test_concurrent_model_calls_keep_provider_and_results_separate():
    openai = ChatOpenAI(api_key="synthetic", model="synthetic")
    azure = FredAzureChatOpenAI(
        api_key="synthetic",
        azure_endpoint="https://example.test",
        api_version="2024-06-01",
    )
    ollama = FakeListChatModel(
        responses=["unused"], metadata={"fred_model_provider": "ollama"}
    )
    messages = [
        (
            openai,
            AIMessage(
                content="",
                response_metadata={"incomplete_details": {"reason": "content_filter"}},
            ),
            "output_filtered",
        ),
        (
            openai,
            AIMessage(content=[{"type": "refusal", "refusal": "synthetic"}]),
            "model_refusal",
        ),
        (openai, AIMessage(content="I refuse in prose"), None),
        (
            azure,
            AIMessage(
                content="ok",
                response_metadata={
                    "content_filter_results": {"sexual": {"filtered": False}}
                },
            ),
            None,
        ),
        (
            ollama,
            AIMessage(
                content="ok", response_metadata={"finish_reason": "content_filter"}
            ),
            None,
        ),
    ]

    async def check(entry):
        model, message, expected = entry
        await asyncio.sleep(0)
        if expected is None:
            check_model_message(model, message, INPUT)
        else:
            with pytest.raises(ContentPolicyError) as caught:
                check_model_message(model, message, INPUT)
            assert caught.value.notice.kind == expected

    await asyncio.gather(*(check(entry) for entry in messages * 20))
