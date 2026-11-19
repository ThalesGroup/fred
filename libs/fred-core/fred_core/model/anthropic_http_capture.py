# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Keep LangChain's lazy Anthropic client caches when enabling observation."""

from functools import cached_property

import anthropic
from fred_core.model.http_capture import observe_httpx_client
from langchain_anthropic import ChatAnthropic


class ObservedChatAnthropic(ChatAnthropic):
    @classmethod
    def lc_id(cls) -> list[str]:
        return ChatAnthropic.lc_id()

    @cached_property
    def _client(self) -> anthropic.Client:
        client = super()._client
        observe_httpx_client(client._client)
        return client

    @cached_property
    def _async_client(self) -> anthropic.AsyncClient:
        client = super()._async_client
        observe_httpx_client(client._client)
        return client
