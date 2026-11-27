# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Build diagnostic JSON from captured evidence inside the runtime."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum

from fred_core.conversation_trace import TraceMaskedDocument, TraceMaskedField
from pydantic import JsonValue

_REDACTED = "<redacted>"
_MAX_NODES = 8_192
_MAX_ANNOTATIONS = 512
type JsonPath = tuple[str | int, ...]


class Leaf(Enum):
    OMIT = "omit"
    TEXT = "text"
    NUMBER = "number"
    COUNT = "count"
    BOOL = "bool"
    CALL_ID = "call_id"


@dataclass(frozen=True)
class ObjectShape:
    fields: dict[str, Rule]


@dataclass(frozen=True)
class ArrayShape:
    item: Rule


type Rule = ObjectShape | ArrayShape | Leaf | frozenset[str]


def _enum(values: str) -> frozenset[str]:
    return frozenset(values.split())


def _fields(rule: Rule, names: str) -> dict[str, Rule]:
    return dict.fromkeys(names.split(), rule)


_ROLES = _enum("system developer user assistant tool function human ai")
_TYPES = _enum(
    "text thinking reasoning summary_text refusal image image_url input_text output_text "
    "input_image input_file audio input_audio output_audio file tool_use tool_result "
    "message function function_call function_call_output tool_call code hitl_request "
    "hitl_response web_search web_search_preview "
    "web_search_call computer_call image_generation_call json_schema json_object"
)
_REASONS = _enum(
    "stop length tool_calls function_call content_filter eos_token model_length "
    "stop_sequence end_turn max_tokens error"
)
_STATUS = _enum(
    "queued in_progress completed incomplete failed cancelled success error"
)
_EFFORT = _enum("none minimal low medium high xhigh")
_REASONING = ObjectShape(
    {"effort": _EFFORT, "summary": _enum("auto concise detailed"), "context": Leaf.TEXT}
)
_OPTIONS = {
    **_fields(
        Leaf.NUMBER,
        "temperature top_p min_p presence_penalty frequency_penalty repetition_penalty",
    ),
    **_fields(
        Leaf.COUNT,
        "max_tokens max_completion_tokens max_output_tokens max_tool_calls "
        "top_logprobs n seed random_seed",
    ),
    **_fields(
        Leaf.BOOL,
        "stream store parallel_tool_calls safe_prompt logprobs echo background",
    ),
    "reasoning_effort": _EFFORT,
    "reasoning": _REASONING,
    "stream_options": ObjectShape({"include_usage": Leaf.BOOL}),
}
_USAGE = ObjectShape(
    {
        "service_tier": _enum("auto default standard priority flex scale"),
        **_fields(
            Leaf.COUNT,
            "prompt_tokens completion_tokens total_tokens input_tokens output_tokens "
            "cached_tokens reasoning_tokens",
        ),
        **_fields(
            ObjectShape(
                _fields(
                    Leaf.COUNT,
                    "cached_tokens created_cache_tokens reasoning_tokens audio_tokens "
                    "accepted_prediction_tokens rejected_prediction_tokens",
                )
            ),
            "prompt_tokens_details completion_tokens_details input_tokens_details "
            "output_tokens_details",
        ),
    }
)
_METRICS = ObjectShape(
    _fields(
        Leaf.NUMBER,
        "time_to_first_token_ms generation_time_ms queue_time_ms mean_itl_ms "
        "tokens_per_second",
    )
)
_FILTER_RESULT = ObjectShape(
    {
        "detected": Leaf.BOOL,
        "filtered": Leaf.BOOL,
        "severity": _enum("safe low medium high"),
    }
)
_FILTER_CATEGORIES = ObjectShape(
    _fields(
        _FILTER_RESULT,
        "hate sexual violence self_harm jailbreak protected_material_text "
        "protected_material_code profanity",
    )
)
_CONTENT_FILTER = ObjectShape(
    {
        "blocked": Leaf.BOOL,
        "source_type": _enum("prompt completion input output"),
        "content_filter_results": _FILTER_CATEGORIES,
        "content_filter_offsets": ObjectShape(
            _fields(Leaf.COUNT, "start_offset end_offset check_offset")
        ),
        "content_filter_raw": Leaf.OMIT,
    }
)
_PART_FIELDS: dict[str, Rule] = {
    "type": _TYPES,
    "closed": Leaf.BOOL,
    "call_id": Leaf.CALL_ID,
    "ok": Leaf.BOOL,
    "latency_ms": Leaf.COUNT,
    **_fields(
        Leaf.TEXT, "text code name refusal url signature id data file_id filename"
    ),
    **_fields(Leaf.OMIT, "annotations args image_url logprobs"),
}
_PART = ObjectShape(_PART_FIELDS)
# Mistral native thinking blocks contain an array of typed text blocks.
_PART_FIELDS["thinking"] = ArrayShape(_PART)
_PART_FIELDS["content"] = ArrayShape(_PART)

_FUNCTION = ObjectShape(
    {
        "name": Leaf.TEXT,
        "description": Leaf.TEXT,
        "arguments": Leaf.TEXT,
        "parameters": Leaf.OMIT,
        "strict": Leaf.BOOL,
    }
)
_TOOL = ObjectShape(
    {
        **_FUNCTION.fields,
        "type": _TYPES,
        "function": _FUNCTION,
    }
)
_CALL = ObjectShape(
    {
        "type": _TYPES,
        "id": Leaf.CALL_ID,
        "index": Leaf.COUNT,
        "function": _FUNCTION,
        "name": Leaf.TEXT,
        "args": Leaf.OMIT,
        "error": Leaf.OMIT,
    }
)
_MESSAGE = ObjectShape(
    {
        "type": _TYPES,
        "role": _ROLES,
        "phase": _enum("commentary final_answer"),
        "status": _STATUS,
        "content": ArrayShape(_PART),
        **_fields(Leaf.CALL_ID, "id call_id tool_call_id"),
        **_fields(
            Leaf.TEXT,
            "name output arguments reasoning reasoning_content encrypted_content refusal",
        ),
        "tool_calls": ArrayShape(_CALL),
        "invalid_tool_calls": ArrayShape(_CALL),
        "tool_call_chunks": ArrayShape(_CALL),
        "function_call": _FUNCTION,
        "summary": ArrayShape(_PART),
        "usage_metadata": _USAGE,
        **_fields(Leaf.OMIT, "additional_kwargs response_metadata"),
    }
)
_TOOL_CHOICE = _enum("auto none required any")
# Provider SDKs merge configurable extra_body keys into the request, so the
# request root does not grant permission to disclose unknown key names.
_REQUEST = ObjectShape(
    {
        **_OPTIONS,
        "model": Leaf.TEXT,
        "messages": ArrayShape(_MESSAGE),
        "input": ArrayShape(_MESSAGE),
        "tools": ArrayShape(_TOOL),
        "tool_choice": _TOOL_CHOICE,
        "instructions": Leaf.TEXT,
        "response_format": ObjectShape({"type": _TYPES, "json_schema": Leaf.OMIT}),
    }
)
_CHOICE = ObjectShape(
    {
        "index": Leaf.COUNT,
        "finish_reason": _REASONS,
        "stop_reason": _REASONS,
        "delta": _MESSAGE,
        "message": _MESSAGE,
        "content_filter_results": _FILTER_CATEGORIES,
        **_fields(Leaf.OMIT, "logprobs token_ids"),
    }
)
_ERROR_CODES = _enum(
    "OASValidation invalid_request_error content_filter invalid_prompt "
    "context_length_exceeded rate_limit_exceeded server_error"
)
_ERROR = ObjectShape(
    {
        "code": _ERROR_CODES,
        "type": _enum("invalid_request_error server_error"),
        **_fields(Leaf.TEXT, "message detail param"),
    }
)
_RESPONSE_OBJECTS = _enum("response chat.completion chat.completion.chunk")
_RESPONSE = ObjectShape(
    {
        **_OPTIONS,
        **_fields(
            Leaf.TEXT, "model id system_fingerprint instructions prompt_text user"
        ),
        "object": _RESPONSE_OBJECTS,
        "status": _STATUS,
        **_fields(Leaf.COUNT, "created created_at completed_at"),
        "choices": ArrayShape(_CHOICE),
        "output": ArrayShape(_MESSAGE),
        "tools": ArrayShape(_TOOL),
        "usage": _USAGE,
        "metrics": _METRICS,
        "error": _ERROR,
        "code": _ERROR_CODES,
        "message": Leaf.TEXT,
        "detail": Leaf.TEXT,
        "content_filters": ArrayShape(_CONTENT_FILTER),
        "content_filter_results": _FILTER_CATEGORIES,
        "prompt_filter_results": ArrayShape(
            ObjectShape(
                {
                    "prompt_index": Leaf.COUNT,
                    "content_filter_results": _FILTER_CATEGORIES,
                }
            )
        ),
        **_fields(Leaf.OMIT, "p prompt_token_ids"),
    }
)
_RESPONSE_EVENTS = _enum(
    "response.created response.in_progress response.completed response.failed "
    "response.incomplete response.output_item.added response.output_item.done "
    "response.content_part.added response.content_part.done response.output_text.delta "
    "response.output_text.done response.function_call_arguments.delta "
    "response.function_call_arguments.done response.reasoning_summary_text.delta "
    "response.reasoning_summary_text.done response.refusal.delta response.refusal.done error"
)
_RESPONSE_EVENT = ObjectShape(
    {
        "type": _RESPONSE_EVENTS,
        "response": _RESPONSE,
        "item": _MESSAGE,
        "part": _PART,
        "error": _ERROR,
        "code": _ERROR_CODES,
        "item_id": Leaf.CALL_ID,
        **_fields(
            Leaf.COUNT, "sequence_number output_index content_index summary_index"
        ),
        **_fields(Leaf.TEXT, "text delta arguments message param"),
        **_fields(Leaf.OMIT, "logprobs obfuscation"),
    }
)
_MODEL_SNAPSHOT = ObjectShape(
    {
        "messages": ArrayShape(_MESSAGE),
        "tools": ArrayShape(_TOOL),
        "partial": Leaf.BOOL,
    }
)
_MODEL = ObjectShape(
    {
        "version": Leaf.COUNT,
        "input": _MODEL_SNAPSHOT,
        "output": _MODEL_SNAPSHOT,
        "output_state": _enum("complete partial absent unavailable"),
        "matched_results": ArrayShape(_MESSAGE),
        "normalization": ArrayShape(
            ObjectShape(
                {
                    "status": _enum("skipped unchanged corrected unavailable"),
                    "partial": Leaf.BOOL,
                    "attempt_ref": Leaf.CALL_ID,
                    "rewrites": ArrayShape(
                        ObjectShape(
                            {
                                "frame_index": Leaf.COUNT,
                                "choice_index": Leaf.COUNT,
                                "tool_index": Leaf.COUNT,
                                "original_id": Leaf.CALL_ID,
                                "replacement_id": Leaf.CALL_ID,
                                "tool_call_id": Leaf.CALL_ID,
                            }
                        )
                    ),
                }
            )
        ),
    }
)
_TOOL_EVIDENCE = ObjectShape(
    {
        "version": Leaf.COUNT,
        "input": Leaf.OMIT,
        "output": Leaf.OMIT,
        "model_result": _MESSAGE,
        "partial": Leaf.BOOL,
    }
)
_HISTORY = ObjectShape(
    {
        "available": Leaf.BOOL,
        "messages": ArrayShape(
            ObjectShape(
                {
                    "role": _ROLES,
                    "channel": _enum(
                        "final plan thought observation tool_call tool_result error system"
                    ),
                    "rank": Leaf.COUNT,
                    "parts": ArrayShape(_PART),
                    "content": ArrayShape(_PART),
                }
            )
        ),
    }
)
_OUTGOING_EVENT = _enum(
    "assistant_delta thought_start thought_delta thought_end tool_call tool_result "
    "status awaiting_human final node_error execution_error execution_interrupted "
    "steered_user_message turn_persisted session_title"
)
_OUTGOING = ObjectShape(
    {
        "kind": _OUTGOING_EVENT,
        "type": _OUTGOING_EVENT,
        **_fields(Leaf.COUNT, "sequence timestamp rank"),
        "call_id": Leaf.CALL_ID,
        **_fields(Leaf.TEXT, "text delta message content error arguments tool_name"),
        **_fields(Leaf.OMIT, "payload data args result"),
    }
)


def _value_type(value: object) -> str:
    return {
        dict: "object",
        list: "array",
        str: "string",
        bool: "boolean",
        int: "number",
        float: "number",
        type(None): "null",
    }.get(type(value), "object")


@dataclass
class _Projection:
    inspect_arguments: bool = False
    annotations: list[TraceMaskedField] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    nodes: int = 0

    def annotate(
        self,
        path: JsonPath,
        key: str,
        value: object,
        position: int,
        *,
        invalid_json: bool | None = None,
    ) -> None:
        if len(self.annotations) >= _MAX_ANNOTATIONS:
            return
        self.annotations.append(
            TraceMaskedField.model_validate(
                {
                    "parent": list(path),
                    "key": key,
                    "value_type": _value_type(value),
                    "position": position,
                    "invalid_json": invalid_json,
                }
            )
        )

    def project(self, value: object, rule: Rule, path: JsonPath = ()) -> JsonValue:
        self.nodes += 1
        if self.nodes > _MAX_NODES or len(path) > 24:
            return _REDACTED
        if value is None:
            return None
        if isinstance(rule, ObjectShape) and isinstance(value, dict):
            result: dict[str, JsonValue] = {}
            for key, item in value.items():
                if self.nodes >= _MAX_NODES:
                    break
                child: Rule | None = rule.fields.get(key)
                if child is None:
                    continue
                if child is Leaf.OMIT:
                    self.annotate(path, key, item, len(result))
                    continue
                if (
                    self.inspect_arguments
                    and key == "arguments"
                    and isinstance(item, str)
                ):
                    try:
                        json.loads(item)
                    except (ValueError, RecursionError):
                        invalid_json = True
                    else:
                        invalid_json = False
                    self.annotate(
                        path, key, item, len(result), invalid_json=invalid_json
                    )
                result[key] = self.project(item, child, (*path, key))
            return result
        if isinstance(rule, ArrayShape) and isinstance(value, list):
            return [
                self.project(item, rule.item, (*path, index))
                for index, item in enumerate(value)
                if self.nodes < _MAX_NODES
            ]
        if isinstance(rule, frozenset) and isinstance(value, str) and value in rule:
            return value
        if rule is Leaf.CALL_ID and isinstance(value, str):
            if value in ("", "null"):
                return value
            return self.aliases.setdefault(value, f"call_{len(self.aliases) + 1}")
        if rule is Leaf.BOOL and isinstance(value, bool):
            return value
        if rule is Leaf.COUNT and type(value) is int and abs(value) < 2**53:
            return value
        if rule is Leaf.NUMBER and (
            (type(value) is int and abs(value) < 2**53)
            or (type(value) is float and math.isfinite(value))
        ):
            return value
        if value == "":
            return ""
        if value == []:
            return []
        return _REDACTED


def _document(
    value: object, rule: Rule, *, inspect_arguments: bool = False
) -> TraceMaskedDocument:
    projection = _Projection(inspect_arguments=inspect_arguments)
    return TraceMaskedDocument(
        data=projection.project(value, rule), annotations=projection.annotations
    )


def unavailable() -> TraceMaskedDocument:
    return TraceMaskedDocument(data=None, unavailable=True)


def mask_http(raw: bytes, *, request: bool, remote_tool: bool) -> TraceMaskedDocument:
    if remote_tool:
        return TraceMaskedDocument(data=_REDACTED)
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        return unavailable()
    if not isinstance(value, dict):
        return unavailable()
    return _document(
        value,
        _REQUEST if request else _RESPONSE,
        inspect_arguments=request,
    )


def mask_sse(raw: bytes, *, outgoing: bool) -> TraceMaskedDocument:
    lines = raw.removeprefix(b"\xef\xbb\xbf").splitlines()
    data = b"\n".join(
        line[5:].removeprefix(b" ") for line in lines if line.startswith(b"data:")
    )
    if data.strip() == b"[DONE]":
        return TraceMaskedDocument(data="[DONE]")
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return unavailable()
    if not isinstance(value, dict):
        return unavailable()
    if outgoing:
        return _document(value, _OUTGOING)
    event_type = value.get("type")
    if isinstance(event_type, str) and event_type in _RESPONSE_EVENTS:
        return _document(value, _RESPONSE_EVENT)
    return _document(value, _RESPONSE)


def mask_model(value: object) -> TraceMaskedDocument:
    return _document(value, _MODEL)


def mask_tool(value: object) -> TraceMaskedDocument:
    return _document(value, _TOOL_EVIDENCE)


def mask_history(value: object) -> TraceMaskedDocument:
    return _document(value, _HISTORY)
