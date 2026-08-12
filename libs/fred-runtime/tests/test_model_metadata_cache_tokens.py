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

from fred_runtime.runtime_support.model_metadata import (
    normalize_token_usage,
    sum_token_usage,
)


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
