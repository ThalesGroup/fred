# Copyright Thales 2025

import time
import pytest
from fred.monitoring.metric_util import translate_response_metadata_to_metric
from fred.monitoring.metric_store import Metric
from fred.monitoring.metric_types import TokenUsage, TokenDetails


def test_translate_response_metadata_to_metric_valid_dict():
    now = time.time()
    raw = {
        "token_usage": {
            "completion_tokens": 7,
            "prompt_tokens": 36,
            "total_tokens": 43,
            "completion_tokens_details": {
                "accepted_prediction_tokens": 0,
                "audio_tokens": 0,
                "reasoning_tokens": 0,
                "rejected_prediction_tokens": 0
            },
            "prompt_tokens_details": {
                "audio_tokens": 0,
                "cached_tokens": 0
            }
        },
        "model_name": "gpt-4o",
        "system_fingerprint": "abc123",
        "finish_reason": "stop",
        "service_tier": "standard",
        "timestamp": now
    }

    ctx = {
        "user_id": "user@example.com",
        "session_id": "session-123"
    }

    metric = translate_response_metadata_to_metric(
        raw=raw,
        ctx=ctx,
        latency=0.1234,
        model_type="gpt-4o"
    )

    assert isinstance(metric, Metric)
    assert metric.user_id == "user@example.com"
    assert metric.session_id == "session-123"
    assert metric.latency == 0.1234
    assert metric.model_name == "gpt-4o"
    assert metric.token_usage is not None
    assert metric.token_usage.completion_tokens == 7
    assert metric.token_usage.total_tokens == 43


def test_translate_response_metadata_with_existing_token_usage_object():
    # TokenUsage instance is passed directly
    token_usage = TokenUsage(
        completion_tokens=5,
        prompt_tokens=20,
        total_tokens=25,
        completion_tokens_details=TokenDetails(audio_tokens=0),
        prompt_tokens_details=TokenDetails(cached_tokens=0)
    )

    raw = {
        "token_usage": token_usage,
        "model_name": "custom-llm",
        "finish_reason": "stop"
    }

    ctx = {"user_id": "u", "session_id": "s"}
    metric = translate_response_metadata_to_metric(
        raw=raw,
        ctx=ctx,
        latency=0.99,
        model_type="custom"
    )

    assert metric.token_usage.total_tokens == 25


def test_translate_response_metadata_missing_token_usage():
    raw = {
        "model_name": "gpt-4o",
        "finish_reason": "length",
        "service_tier": "free"
    }

    ctx = {"user_id": "x", "session_id": "y"}
    metric = translate_response_metadata_to_metric(
        raw=raw,
        ctx=ctx,
        latency=0.4,
        model_type="gpt"
    )

    assert isinstance(metric, Metric)
    assert metric.token_usage is None


def test_translate_response_metadata_invalid_token_usage_raises():
    raw = {
        "token_usage": "this-is-invalid"  # not a dict or TokenUsage
    }

    ctx = {"user_id": "bad", "session_id": "data"}
    metric = translate_response_metadata_to_metric(
        raw=raw,
        ctx=ctx,
        latency=0.0,
        model_type="bad"
    )

    assert metric is None  # should safely fail and return None
