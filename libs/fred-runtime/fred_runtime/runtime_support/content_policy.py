# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Normalize structured provider content-policy decisions at model boundaries."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import httpx
from fred_core.history.history_schema import ContentCategory, ContentNotice
from fred_core.model.azure_chat import AzureFilteredCompletion
from fred_core.model.openai_chat import StructuredOpenAIRefusal
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from openai import APIStatusError, ContentFilterFinishReasonError

from fred_runtime.execution_errors import UserFacingExecutionError

from .llm_diagnostics import exception_chain

_AZURE = frozenset({"azure-openai", "azure-apim"})
_OPENAI = _AZURE | {"openai"}
_GEMINI = "vertex-ai"
_MAX_ERROR_BYTES = 16 * 1024
_GEMINI_HARM_REASONS = frozenset(
    {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "IMAGE_SAFETY"}
)
_GEMINI_PROMPT_BLOCKS = _GEMINI_HARM_REASONS | {"MODEL_ARMOR", "JAILBREAK"}
_GEMINI_OUTPUT_BLOCKS = _GEMINI_HARM_REASONS | {
    "RECITATION",
    "SPII",
    "IMAGE_PROHIBITED_CONTENT",
    "IMAGE_RECITATION",
}
_AZURE_CATEGORIES: dict[str, ContentCategory] = {
    "hate": "hate",
    "self_harm": "self_harm",
    "sexual": "sexual",
    "violence": "violence",
    "protected_material_code": "protected_material_code",
    "protected_material_text": "protected_material_text",
    "jailbreak": "prompt_attack",
    "custom_blocklists": "blocklist",
}
_GEMINI_CATEGORIES: dict[str, ContentCategory] = {
    "HARM_CATEGORY_HATE_SPEECH": "hate",
    "HARM_CATEGORY_HARASSMENT": "harassment",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "sexual",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "dangerous",
}
_MISTRAL_CATEGORIES: dict[str, ContentCategory] = {
    "sexual": "sexual",
    "selfharm": "self_harm",
    "violence_and_threats": "violence",
    "hate_and_discrimination": "hate",
    "pii": "privacy",
    "jailbreaking": "prompt_attack",
    "criminal": "illicit",
    "dangerous": "dangerous",
    "health": "health",
    "financial": "financial",
    "law": "legal",
}


class ContentPolicyError(UserFacingExecutionError):
    def __init__(self, notice: ContentNotice) -> None:
        if notice.origin == "tool":
            message = "A tool blocked content in this turn."
        elif notice.kind == "model_refusal":
            message = "The model declined to answer."
        else:
            message = "The model provider blocked content in this turn."
        super().__init__(message)
        self.notice = notice


def notice_from_exception(exc: BaseException) -> ContentNotice | None:
    chain, _ = exception_chain(exc)
    return next(
        (item.notice for item in chain if isinstance(item, ContentPolicyError)), None
    )


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _provider(model: BaseChatModel) -> str | None:
    configured = (model.metadata or {}).get("fred_model_provider")
    if isinstance(configured, str):
        return configured
    if isinstance(model, AzureChatOpenAI):
        return "azure-openai"
    if isinstance(model, ChatOpenAI):
        return "openai"
    return None


def _azure_categories(value: object) -> tuple[ContentCategory, ...]:
    fields = _mapping(value)
    return tuple(
        category
        for key, category in _AZURE_CATEGORIES.items()
        if _mapping(fields.get(key)).get("filtered") is True
    )


def _gemini_categories(value: object) -> tuple[ContentCategory, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    categories: dict[ContentCategory, None] = {}
    for item in value[:16]:
        rating = _mapping(item)
        raw = rating.get("category")
        if rating.get("blocked") is True and isinstance(raw, str):
            category = _GEMINI_CATEGORIES.get(raw)
            if category is not None:
                categories[category] = None
    return tuple(categories)


def _http_body(exc: APIStatusError | httpx.HTTPStatusError) -> dict:
    try:
        buffered = exc.response.content
        if len(buffered) > _MAX_ERROR_BYTES:
            return {}
        return _mapping(json.loads(buffered))
    except (httpx.ResponseNotRead, ValueError, RecursionError):
        return {}


def _azure_http(exc: APIStatusError | httpx.HTTPStatusError) -> ContentNotice | None:
    if exc.response.status_code != 400:
        return None
    envelope = _http_body(exc)
    body = _mapping(envelope.get("error", envelope))
    if body.get("code") != "content_filter":
        return None
    # APIM may expose an arbitrary prefix. Check the actual operation suffix.
    responses = exc.request.url.path.rstrip("/").endswith("/responses")
    param = body.get("param")
    if param != "prompt" and (not responses or param not in (None, "input")):
        return None
    inner = _mapping(body.get("innererror"))
    return ContentNotice(
        kind="prompt_blocked",
        categories=_azure_categories(inner.get("content_filter_result")),
    )


def _mistral_http(exc: httpx.HTTPStatusError) -> ContentNotice | None:
    # Only reached for Fred's Mistral Model Garden route. Require the full
    # documented guardrail verdict; a generic 403 or evaluator failure is unrelated.
    if exc.response.status_code != 403:
        return None
    body = _http_body(exc)
    results = _mapping(_mapping(body.get("guardrails")).get("results"))
    moderation = _mapping(results.get("moderation_llm_v2"))
    if moderation.get("action") == "block" and moderation.get("violated") is True:
        decisions = _mapping(moderation.get("decisions"))
        return ContentNotice(
            kind="prompt_blocked",
            categories=tuple(
                category
                for key, category in _MISTRAL_CATEGORIES.items()
                if _mapping(decisions.get(key)).get("violated") is True
            ),
        )
    return None


def _input_origin(
    notice: ContentNotice,
    messages: Sequence[BaseMessage],
    *,
    has_other_inputs: bool,
) -> ContentNotice:
    # A prompt verdict names the entire provider input. Attribution to the
    # user requires a single unadorned text message and no other input.
    if notice.kind == "prompt_blocked" and len(messages) == 1 and not has_other_inputs:
        message = messages[0]
        if (
            isinstance(message, HumanMessage)
            and isinstance(message.content, str)
            and not message.additional_kwargs
            and not message.name
        ):
            return notice.model_copy(update={"origin": "user_message"})
    return notice


@contextmanager
def normalize_model_error(
    model: BaseChatModel,
    messages: Sequence[BaseMessage],
    *,
    has_other_inputs: bool = False,
) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        provider = _provider(model)
        notice = None
        chain, _ = exception_chain(exc)
        for error in chain:
            if isinstance(error, ContentPolicyError):
                raise
            if provider in _AZURE and isinstance(error, AzureFilteredCompletion):
                notice = ContentNotice(
                    kind="output_filtered",
                    categories=_azure_categories(error.filter_results),
                )
            elif provider in _OPENAI and isinstance(
                error, ContentFilterFinishReasonError
            ):
                choices = error.completion.choices[:16] if error.completion else ()
                categories = (
                    tuple(
                        dict.fromkeys(
                            category
                            for choice in choices
                            for category in _azure_categories(
                                getattr(choice, "content_filter_results", None)
                            )
                        )
                    )
                    if provider in _AZURE
                    else ()
                )
                notice = ContentNotice(kind="output_filtered", categories=categories)
            elif provider in _OPENAI and isinstance(error, StructuredOpenAIRefusal):
                notice = ContentNotice(kind="model_refusal")
            elif provider in _AZURE and isinstance(
                error, (APIStatusError, httpx.HTTPStatusError)
            ):
                notice = _azure_http(error)
            elif (
                provider == "vertex-ai-model-garden"
                and model._llm_type == "mistralai-chat"
                and isinstance(error, httpx.HTTPStatusError)
            ):
                notice = _mistral_http(error)
            if notice is not None:
                raise ContentPolicyError(
                    _input_origin(notice, messages, has_other_inputs=has_other_inputs)
                ) from exc
        raise


def check_model_message(
    model: BaseChatModel,
    message: BaseMessage,
    messages: Sequence[BaseMessage],
    *,
    has_other_inputs: bool = False,
) -> None:
    provider = _provider(model)
    metadata = message.response_metadata
    reason = metadata.get("finish_reason")
    if provider in _OPENAI:
        incomplete = _mapping(metadata.get("incomplete_details"))
        if reason == "content_filter" or incomplete.get("reason") == "content_filter":
            raise ContentPolicyError(
                ContentNotice(
                    kind="output_filtered",
                    categories=_azure_categories(metadata.get("content_filter_results"))
                    if provider in _AZURE
                    else (),
                )
            )
        refusal = message.additional_kwargs.get("refusal")
        blocks = message.content
        if (isinstance(refusal, str) and refusal) or (
            isinstance(blocks, list)
            and any(_mapping(block).get("type") == "refusal" for block in blocks)
        ):
            raise ContentPolicyError(ContentNotice(kind="model_refusal"))
    elif provider == _GEMINI:
        feedback = _mapping(metadata.get("prompt_feedback"))
        block_reason = feedback.get("block_reason")
        if isinstance(block_reason, str) and block_reason in _GEMINI_PROMPT_BLOCKS:
            notice = ContentNotice(
                kind="prompt_blocked",
                categories=_gemini_categories(feedback.get("safety_ratings")),
            )
            raise ContentPolicyError(
                _input_origin(notice, messages, has_other_inputs=has_other_inputs)
            )
        if isinstance(reason, str) and reason in _GEMINI_OUTPUT_BLOCKS:
            raise ContentPolicyError(
                ContentNotice(
                    kind="output_filtered",
                    categories=_gemini_categories(metadata.get("safety_ratings")),
                )
            )
