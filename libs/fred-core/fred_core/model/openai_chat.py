# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Preserve the structured Chat Completions refusal omitted by LangChain."""

from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI


class StructuredOpenAIRefusal(Exception):
    """The provider sent a refusal field, with no free text retained here."""

    def __init__(self) -> None:
        super().__init__("The model returned a structured refusal.")


def check_stream_refusal(choices: object) -> None:
    if not isinstance(choices, list):
        return
    for choice in choices[:16]:
        delta = choice.get("delta") if isinstance(choice, dict) else None
        refusal = delta.get("refusal") if isinstance(delta, dict) else None
        if isinstance(refusal, str) and refusal:
            raise StructuredOpenAIRefusal()


class FredChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(
        self, chunk: dict, default_chunk_class: type, base_generation_info: dict | None
    ) -> ChatGenerationChunk | None:
        check_stream_refusal(chunk.get("choices"))
        provider_chunk = chunk.get("chunk")
        if isinstance(provider_chunk, dict):
            check_stream_refusal(provider_chunk.get("choices"))
        return super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
