# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Local invocation and transport guards; the shared pools retain their owner."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Collection, Iterator
from typing import Any

import httpx
from fred_sdk.contracts.weaver import InferenceAdmission
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.support.reasoning_replay import MistralReasoningReplayChatOpenAI

from .turn import TurnAuthority

# Not a secret. The client requires a key; the guard removes this one before sending.
NO_AUTH_BEARER = "fred-no-inference-auth"


class GuardedChatOpenAI(ChatOpenAI):
    # Installed only by guarded_model, never serialized/checkpointed.
    _turn_check: Callable[[], None]

    def _generate_with_cache(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._turn_check()
        return super()._generate_with_cache(messages, stop, run_manager, **kwargs)

    async def _agenerate_with_cache(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._turn_check()
        return await super()._agenerate_with_cache(
            messages, stop, run_manager, **kwargs
        )

    def stream(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterator[AIMessageChunk]:
        self._turn_check()
        for chunk in super().stream(input, config, stop=stop, **kwargs):
            yield chunk

    async def astream(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        self._turn_check()
        async for chunk in super().astream(input, config, stop=stop, **kwargs):
            yield chunk


class GuardedMistralChatOpenAI(GuardedChatOpenAI, MistralReasoningReplayChatOpenAI):
    """Keep native reasoning replay alongside the invocation and transport guards."""


def guarded_model(model: ChatOpenAI, check: Callable[[], None]) -> ChatOpenAI:
    # Preserve the existing OpenAI clients and pool, as the reasoning replay adapter does.
    guarded_class = (
        GuardedMistralChatOpenAI
        if isinstance(model, MistralReasoningReplayChatOpenAI)
        else GuardedChatOpenAI
    )
    object.__setattr__(model, "__class__", guarded_class)
    object.__setattr__(model, "_turn_check", check)
    model.cache = False
    return model


class _NoPoolTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise RuntimeError("Guarded client must delegate to the shared pool")

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise RuntimeError("Guarded client must delegate to the shared pool")


class _CheckedClient(httpx.Client):
    def __init__(self, shared: httpx.Client, check: Callable[[httpx.Request], None]):
        super().__init__(transport=_NoPoolTransport())
        self._shared = shared
        self._check = check

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        self._check(request)
        kwargs["follow_redirects"] = False
        return self._shared.send(request, **kwargs)


class _CheckedAsyncClient(httpx.AsyncClient):
    def __init__(
        self, shared: httpx.AsyncClient, check: Callable[[httpx.Request], None]
    ):
        super().__init__(transport=_NoPoolTransport())
        self._shared = shared
        self._check = check

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        self._check(request)
        kwargs["follow_redirects"] = False
        return await self._shared.send(request, **kwargs)


def checked_clients(
    authority: TurnAuthority,
    admission: InferenceAdmission,
    bearers: Collection[str],
    gateway: tuple[str, str] | None,
):
    """`bearers` may grow with the model's own Entra tokens; `gateway` is (header, key)."""
    if admission != authority.binding.inference and (
        authority.binding.title is None
        or admission != authority.binding.title.inference
    ):
        raise AuthorityLostError()
    selection = admission.selection
    connection = admission.connection
    url = connection.request_url(selection.key.upstream_model_id)
    options = selection.options

    def check(request: httpx.Request) -> None:
        authority.check()
        scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
        if (
            request.method != "POST"
            or str(request.url) != url
            or scheme != "Bearer"
            or bearer not in bearers
            or "api-key" in request.headers
            or (gateway is not None and gateway[0] in request.headers)
        ):
            raise AuthorityLostError()
        try:
            payload = json.loads(request.content)
        except (ValueError, httpx.RequestNotRead):
            raise AuthorityLostError() from None
        if (
            not isinstance(payload, dict)
            or payload.get("model") != selection.key.upstream_model_id
        ):
            raise AuthorityLostError()
        # Transformations may narrow a token ceiling, never change the resolved knobs.
        for name in ("temperature", "top_p"):
            expected = getattr(options, name)
            if payload.get(name) != expected:
                raise AuthorityLostError()
        tokens = [
            payload[k]
            for k in ("max_tokens", "max_completion_tokens", "max_output_tokens")
            if k in payload
        ]
        limits = [options.max_tokens]
        if any(
            not isinstance(v, int)
            or isinstance(v, bool)
            or v <= 0
            or any(limit is not None and v > limit for limit in limits)
            for v in tokens
        ):
            raise AuthorityLostError()
        if options.max_tokens is not None and not tokens:
            raise AuthorityLostError()
        effort = options.reasoning_effort
        if connection.wire == "openai_responses":
            sent, other, expected = "reasoning", "reasoning_effort", {"effort": effort}
        else:
            sent, other, expected = "reasoning_effort", "reasoning", effort
        if (
            other in payload
            or (effort is None and sent in payload)
            or (effort is not None and payload.get(sent) != expected)
        ):
            raise AuthorityLostError()
        # After every control, immediately before the send.
        if connection.auth.kind == "none":
            del request.headers["authorization"]
        if gateway is not None:
            request.headers[gateway[0]] = gateway[1]

    def wrap(
        sync: httpx.Client, asynchronous: httpx.AsyncClient
    ) -> tuple[httpx.Client, httpx.AsyncClient]:
        return _CheckedClient(sync, check), _CheckedAsyncClient(asynchronous, check)

    return wrap
