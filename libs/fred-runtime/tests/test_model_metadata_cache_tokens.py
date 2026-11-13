# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for prompt-cache token extraction (CACHE-01).

Why this exists:
- LangChain's standardized `UsageMetadata.input_token_details` has carried
  `cache_read`/`cache_creation` since `langchain-core` 0.3.9, but
  `normalize_token_usage` silently dropped it — every input token was
  treated as fresh regardless of provider-side cache hits
- `sum_token_usage` must fold the new fields across a multi-call turn the
  same way it already folds input/output/total
"""

from __future__ import annotations

import pytest
from fred_runtime.runtime_support.model_metadata import (
    normalize_token_usage,
    reported_model_call_usage,
    sum_token_usage,
)
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata


def test_normalize_token_usage_extracts_cache_detail_when_present() -> None:
    raw = {
        "input_tokens": 350,
        "output_tokens": 240,
        "total_tokens": 590,
        "input_token_details": {"cache_creation": 200, "cache_read": 100},
    }

    result = normalize_token_usage(raw)

    assert result == {
        "input_tokens": 350,
        "output_tokens": 240,
        "total_tokens": 590,
        "cache_read_tokens": 100,
        "cache_creation_tokens": 200,
    }


def test_normalize_token_usage_defaults_cache_fields_to_zero_when_absent() -> None:
    raw = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

    result = normalize_token_usage(raw)

    assert result is not None
    assert result["cache_read_tokens"] == 0
    assert result["cache_creation_tokens"] == 0


def test_normalize_token_usage_ignores_non_dict_input_token_details() -> None:
    raw = {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "input_token_details": "not-a-dict",
    }

    result = normalize_token_usage(raw)

    assert result is not None
    assert result["cache_read_tokens"] == 0
    assert result["cache_creation_tokens"] == 0


def test_sum_token_usage_folds_cache_fields_across_calls() -> None:
    first = {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cache_read_tokens": 80,
        "cache_creation_tokens": 0,
    }
    second = {
        "input_tokens": 30,
        "output_tokens": 10,
        "total_tokens": 40,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 25,
    }

    total = sum_token_usage(first, second)

    assert total == {
        "input_tokens": 130,
        "output_tokens": 30,
        "total_tokens": 160,
        "cache_read_tokens": 80,
        "cache_creation_tokens": 25,
    }


def test_sum_token_usage_treats_missing_cache_fields_as_zero() -> None:
    legacy_call = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    cache_aware_call = {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cache_read_tokens": 8,
        "cache_creation_tokens": 0,
    }

    total = sum_token_usage(legacy_call, cache_aware_call)

    assert total is not None
    assert total["cache_read_tokens"] == 8
    assert total["cache_creation_tokens"] == 0


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"prompt_tokens": 20672, "completion_tokens": 679}, (20672, 679)),
        ({"input_tokens": 0, "output_tokens": 0}, (0, 0)),
        ({"input_token_count": 12}, (12, None)),
        ({"prompt_eval_count": "12", "eval_count": "3"}, (12, 3)),
        ({"usage": {"prompt_tokens_total": 7, "completion_tokens_total": 2}}, (7, 2)),
        ({"input_tokens": -2, "output_tokens": 1.5}, None),
        ({"input_tokens": True, "output_tokens": "bad"}, None),
        ({"total_tokens": 50}, None),
        ({}, None),
    ],
)
def test_reported_model_usage_preserves_only_actual_counters(payload, expected) -> None:
    message = AIMessage(
        content="", id="provider-response", response_metadata={"usage": payload}
    )
    usage = reported_model_call_usage(message, model="model", tool_call_count=2)
    if expected is None:
        assert usage is not None
        assert usage.input_tokens is None and usage.output_tokens is None
    else:
        assert usage is not None
        assert (usage.input_tokens, usage.output_tokens) == expected
        assert usage.model_call_id == "provider-response"
        assert usage.model == "model"
        assert usage.tool_call_count == 2


@pytest.mark.parametrize(
    "location", ["usage_metadata", "token_usage", "usage", "additional"]
)
def test_reported_usage_handles_provider_locations(location: str) -> None:
    payload: UsageMetadata = {
        "input_tokens": 21,
        "output_tokens": 7,
        "total_tokens": 28,
    }
    message = AIMessage(content="")
    if location == "usage_metadata":
        message.usage_metadata = payload
    elif location == "additional":
        message.additional_kwargs = {"token_usage": payload}
    else:
        message.response_metadata = {location: payload}
    usage = reported_model_call_usage(message, model=None, tool_call_count=1)
    assert usage is not None
    assert usage.input_tokens == 21
    assert usage.output_tokens == 7


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"prompt_tokens": 21}, (21, None)),
        ({"total_tokens": 28}, None),
        ({"prompt_tokens": 21, "completion_tokens": 0}, (21, 0)),
    ],
)
def test_reported_usage_does_not_trust_adapter_synthesized_zeros(raw, expected) -> None:
    from langchain_openai.chat_models.base import _create_usage_metadata

    message = AIMessage(
        content="",
        usage_metadata=_create_usage_metadata(raw),
        response_metadata={"token_usage": raw},
    )
    usage = reported_model_call_usage(message, model=None, tool_call_count=1)
    if expected is None:
        assert usage is not None
        assert usage.input_tokens is None and usage.output_tokens is None
    else:
        assert usage is not None
        assert (usage.input_tokens, usage.output_tokens) == expected


def test_normalized_only_zero_is_unavailable_without_raw_provider_presence() -> None:
    message = AIMessage(
        content="",
        usage_metadata={"input_tokens": 21, "output_tokens": 0, "total_tokens": 21},
    )
    usage = reported_model_call_usage(message, model=None, tool_call_count=1)
    assert usage is not None
    assert usage.input_tokens == 21
    assert usage.output_tokens is None
