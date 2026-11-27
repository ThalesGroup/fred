# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Preserve Azure's structured finish signal at the LangChain adapter."""

from typing import Any

import openai
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import AzureChatOpenAI

from .openai_chat import check_stream_refusal


class AzureFilteredCompletion(Exception):
    """The SDK would otherwise discard this response and raise a ValueError."""

    def __init__(self, filter_results: object) -> None:
        super().__init__("Azure filtered the completion.")
        self.filter_results = filter_results


def _check_choices(choices: object) -> None:
    if not isinstance(choices, list):
        return
    for choice in choices[:16]:
        if isinstance(choice, dict):
            reason = choice.get("finish_reason")
            filters = choice.get("content_filter_results")
        else:
            reason = getattr(choice, "finish_reason", None)
            filters = getattr(choice, "content_filter_results", None)
        if reason == "content_filter":
            raise AzureFilteredCompletion(filters)


class FredAzureChatOpenAI(AzureChatOpenAI):
    def _create_chat_result(
        self,
        response: dict[str, Any] | openai.BaseModel,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        _check_choices(
            response.get("choices")
            if isinstance(response, dict)
            else getattr(response, "choices", None)
        )
        return super()._create_chat_result(response, generation_info)

    def _convert_chunk_to_generation_chunk(
        self, chunk: dict, default_chunk_class: type, base_generation_info: dict | None
    ) -> ChatGenerationChunk | None:
        _check_choices(chunk.get("choices"))
        check_stream_refusal(chunk.get("choices"))
        provider_chunk = chunk.get("chunk")
        if isinstance(provider_chunk, dict):
            _check_choices(provider_chunk.get("choices"))
            check_stream_refusal(provider_chunk.get("choices"))
        return super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
