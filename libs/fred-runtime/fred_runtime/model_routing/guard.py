# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Local invocation and transport guards; the shared pools retain their owner."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
from fred_sdk.contracts.weaver import RuntimeModelOffer
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

from .turn import TurnAuthority


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


def guarded_model(model: ChatOpenAI, check: Callable[[], None]) -> ChatOpenAI:
    # Preserve the existing OpenAI clients and pool, as the reasoning replay adapter does.
    object.__setattr__(model, "__class__", GuardedChatOpenAI)
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


def checked_clients(authority: TurnAuthority, offer: RuntimeModelOffer, api_key: str):
    connection = offer.connection
    if connection is None:
        raise AuthorityLostError()
    allowed_urls = {
        connection.api_root.rstrip("/") + suffix
        for suffix in ("/chat/completions", "/responses")
    }
    options = authority.binding.models.options

    def check(request: httpx.Request) -> None:
        authority.check()
        if (
            not offer.permitted
            or not offer.candidate
            or request.method != "POST"
            or str(request.url) not in allowed_urls
            or request.headers.get("authorization") != f"Bearer {api_key}"
        ):
            raise AuthorityLostError()
        try:
            payload = json.loads(request.content)
        except (ValueError, httpx.RequestNotRead):
            raise AuthorityLostError() from None
        if (
            not isinstance(payload, dict)
            or payload.get("model") != offer.key.upstream_model_id
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
        if offer.metadata is not None:
            limits.extend(
                [offer.metadata.max_output_tokens, offer.metadata.context_window_tokens]
            )
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
        if "reasoning_effort" in payload or "reasoning" in payload:
            raise AuthorityLostError()

    def wrap(
        sync: httpx.Client, asynchronous: httpx.AsyncClient
    ) -> tuple[httpx.Client, httpx.AsyncClient]:
        return _CheckedClient(sync, check), _CheckedAsyncClient(asynchronous, check)

    return wrap
