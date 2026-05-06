"""
Offline unit tests for fred_runtime.eval.collector.collect_eval_trace.

All inputs are plain dicts matching the Fred SSE event vocabulary.
No network, no FastAPI app, no mocks except time.monotonic for latency assertions.
"""

from __future__ import annotations

from unittest.mock import patch

from fred_runtime.eval.collector import collect_eval_trace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trace(events: list[dict], *, input: str = "test input") -> dict:
    with patch("fred_runtime.eval.collector.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        result = collect_eval_trace(
            events,
            agent_id="test.agent",
            input=input,
            session_id="s1",
            started_at=0.0,
        )
    return result


# ---------------------------------------------------------------------------
# Identity fields
# ---------------------------------------------------------------------------


def test_identity_fields_passed_through() -> None:
    trace = _trace([], input="hello")
    assert trace["agent_id"] == "test.agent"
    assert trace["session_id"] == "s1"
    assert trace["input"] == "hello"


# ---------------------------------------------------------------------------
# Final event
# ---------------------------------------------------------------------------


def test_final_event_sets_output() -> None:
    trace = _trace([{"kind": "final", "content": "Answer text."}])
    assert trace["output"] == "Answer text."


def test_final_event_non_string_content_gives_empty_output() -> None:
    trace = _trace([{"kind": "final", "content": {"nested": "dict"}}])
    assert trace["output"] == ""


def test_final_event_sets_model_and_finish_reason() -> None:
    trace = _trace(
        [
            {
                "kind": "final",
                "content": "done",
                "model_name": "gpt-4o",
                "finish_reason": "stop",
            }
        ]
    )
    assert trace["model"] == "gpt-4o"
    assert trace["finish_reason"] == "stop"


def test_final_event_sets_token_usage() -> None:
    trace = _trace(
        [
            {
                "kind": "final",
                "content": "done",
                "token_usage": {"input_tokens": 50, "output_tokens": 120},
            }
        ]
    )
    assert trace["usage"] == {"prompt_tokens": 50, "completion_tokens": 120}


def test_final_event_appears_in_steps() -> None:
    trace = _trace([{"kind": "final", "content": "Answer."}])
    assert trace["steps"] == [{"kind": "final", "content": "Answer."}]


def test_no_final_event_gives_empty_output() -> None:
    trace = _trace([])
    assert trace["output"] == ""
    assert trace["model"] is None
    assert trace["finish_reason"] is None
    assert trace["usage"] == {}


# ---------------------------------------------------------------------------
# Tool call / tool result
# ---------------------------------------------------------------------------


def test_tool_call_recorded_in_steps() -> None:
    trace = _trace(
        [{"kind": "tool_call", "tool_name": "search", "arguments": {"q": "x"}}]
    )
    assert trace["steps"] == [
        {"kind": "tool_call", "name": "search", "input": {"q": "x"}}
    ]


def test_tool_result_recorded_in_steps() -> None:
    trace = _trace(
        [
            {
                "kind": "tool_result",
                "tool_name": "search",
                "content": "result text",
                "is_error": False,
            }
        ]
    )
    assert trace["steps"] == [
        {
            "kind": "tool_result",
            "name": "search",
            "output": "result text",
            "is_error": False,
        }
    ]


def test_tool_result_error_sets_error_field() -> None:
    trace = _trace(
        [
            {
                "kind": "tool_result",
                "tool_name": "search",
                "content": "timeout",
                "is_error": True,
            }
        ]
    )
    assert trace["error"] == "timeout"


def test_tool_result_error_does_not_override_earlier_error() -> None:
    trace = _trace(
        [
            {"error": "first error"},
            {
                "kind": "tool_result",
                "tool_name": "search",
                "content": "second",
                "is_error": True,
            },
        ]
    )
    assert trace["error"] == "first error"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_top_level_error_event_sets_error() -> None:
    trace = _trace([{"error": "something went wrong"}])
    assert trace["error"] == "something went wrong"


def test_node_error_event_sets_error() -> None:
    trace = _trace([{"kind": "node_error", "error_message": "graph node crashed"}])
    assert trace["error"] == "graph node crashed"


def test_node_error_falls_back_to_error_key() -> None:
    trace = _trace([{"kind": "node_error", "error": "fallback msg"}])
    assert trace["error"] == "fallback msg"


def test_node_error_with_no_message_gives_sentinel() -> None:
    trace = _trace([{"kind": "node_error"}])
    assert trace["error"] == "node_error"


def test_error_field_present_on_tool_result_not_treated_as_top_level_error() -> None:
    trace = _trace(
        [
            {
                "kind": "tool_result",
                "tool_name": "search",
                "content": "some result",
                "is_error": False,
                "error": "should be ignored as top-level",
            }
        ]
    )
    assert trace["error"] is None


# ---------------------------------------------------------------------------
# Full turn sequence
# ---------------------------------------------------------------------------


def test_full_turn_order_preserved_in_steps() -> None:
    events = [
        {"kind": "tool_call", "tool_name": "search", "arguments": {"q": "cats"}},
        {
            "kind": "tool_result",
            "tool_name": "search",
            "content": "cats are great",
            "is_error": False,
        },
        {"kind": "final", "content": "Cats are indeed great."},
    ]
    trace = _trace(events)
    assert trace["output"] == "Cats are indeed great."
    assert trace["error"] is None
    kinds = [s["kind"] for s in trace["steps"]]
    assert kinds == ["tool_call", "tool_result", "final"]


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


def test_latency_ms_computed_from_started_at() -> None:
    with patch("fred_runtime.eval.collector.time") as mock_time:
        mock_time.monotonic.return_value = 1.5
        trace = collect_eval_trace(
            [{"kind": "final", "content": "ok"}],
            agent_id="a",
            input="q",
            session_id="s",
            started_at=1.0,
        )
    assert trace["latency_ms"] == 500
