"""
Offline unit tests for _parse_turn_outcome and _build_eval_trace.

All tests run without any external services or FastAPI app.
"""

from __future__ import annotations

import time

from fred_sdk.contracts.eval import EvalTrace

from fred_runtime.app.agent_app import (
    _TurnOutcome,
    _build_eval_trace,
    _parse_turn_outcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normal_payloads() -> list[dict]:
    return [
        {
            "kind": "tool_call",
            "tool_name": "knowledge.text.search",
            "call_id": "c1",
            "arguments": {"query": "test"},
        },
        {
            "kind": "tool_result",
            "tool_name": "knowledge.text.search",
            "call_id": "c1",
            "content": "Some retrieved text",
            "is_error": False,
        },
        {
            "kind": "final",
            "content": "The answer is: Some retrieved text",
            "model_name": "mistral-medium-2508",
            "finish_reason": "stop",
            "token_usage": {"input_tokens": 50, "output_tokens": 15},
        },
    ]


def _error_payloads() -> list[dict]:
    return [
        {"kind": "execution_error", "message": "ConnectionError: backend unreachable"},
    ]


def _hitl_payloads() -> list[dict]:
    return [
        {
            "kind": "tool_call",
            "tool_name": "bank.risk_guard.score_transfer",
            "call_id": "c2",
            "arguments": {"amount_eur": 5000},
        },
        {
            "kind": "tool_result",
            "tool_name": "bank.risk_guard.score_transfer",
            "call_id": "c2",
            "content": "risk_score=0.72",
            "is_error": False,
        },
        {"kind": "awaiting_human"},
    ]


# ---------------------------------------------------------------------------
# _parse_turn_outcome
# ---------------------------------------------------------------------------


class TestParseTurnOutcome:
    def test_normal_turn(self) -> None:
        ts = time.monotonic()
        outcome = _parse_turn_outcome(_normal_payloads(), ts)
        assert isinstance(outcome, _TurnOutcome)
        assert outcome.model_name == "mistral-medium-2508"
        assert outcome.finish_reason == "stop"
        assert outcome.token_usage == {"input_tokens": 50, "output_tokens": 15}
        assert outcome.input_tokens == 50
        assert outcome.output_tokens == 15
        assert outcome.tool_count == 1
        assert outcome.is_error is False
        assert outcome.total_ms >= 0
        assert outcome.final_content == "The answer is: Some retrieved text"

    def test_error_turn(self) -> None:
        ts = time.monotonic()
        outcome = _parse_turn_outcome(_error_payloads(), ts)
        assert outcome.is_error is True
        assert outcome.finish_reason == "error"
        assert outcome.model_name is None
        assert outcome.token_usage is None
        assert outcome.tool_count == 0
        assert outcome.final_content is None

    def test_empty_payloads(self) -> None:
        ts = time.monotonic()
        outcome = _parse_turn_outcome([], ts)
        assert outcome.is_error is False
        assert outcome.tool_count == 0
        assert outcome.model_name is None
        assert outcome.final_content is None
        assert outcome.finish_reason == ""

    def test_hitl_turn(self) -> None:
        ts = time.monotonic()
        outcome = _parse_turn_outcome(_hitl_payloads(), ts)
        assert outcome.is_error is False
        assert outcome.tool_count == 1
        assert outcome.final_content is None
        assert outcome.finish_reason == ""

    def test_total_ms_is_non_negative(self) -> None:
        ts = time.monotonic()
        outcome = _parse_turn_outcome([], ts)
        assert outcome.total_ms >= 0


# ---------------------------------------------------------------------------
# _build_eval_trace
# ---------------------------------------------------------------------------


class TestBuildEvalTrace:
    def _call(self, payloads: list[dict], **kwargs) -> EvalTrace:
        return _build_eval_trace(
            payloads=payloads,
            input_text=kwargs.get("input_text", "test question"),
            agent_id=kwargs.get("agent_id", "test-agent"),
            session_id=kwargs.get("session_id", "session-001"),
            turn_start=time.monotonic(),
        )

    def test_success_retrieval_context_from_content(self) -> None:
        trace = self._call(_normal_payloads())
        assert isinstance(trace, EvalTrace)
        assert trace.output == "The answer is: Some retrieved text"
        assert trace.error is None
        assert "Some retrieved text" in trace.retrieval_context
        assert trace.tools_called == ("knowledge.text.search",)

    def test_success_retrieval_context_from_sources(self) -> None:
        payloads = [
            {
                "kind": "tool_call",
                "tool_name": "search",
                "call_id": "c1",
                "arguments": {},
            },
            {
                "kind": "tool_result",
                "tool_name": "search",
                "call_id": "c1",
                "content": "raw content",
                "is_error": False,
                "sources": [
                    {"content": "source A"},
                    {"content": "source B"},
                ],
            },
            {
                "kind": "final",
                "content": "Final answer",
                "model_name": "m1",
                "finish_reason": "stop",
            },
        ]
        trace = self._call(payloads)
        # sources branch takes priority over content
        assert "source A" in trace.retrieval_context
        assert "source B" in trace.retrieval_context
        assert "raw content" not in trace.retrieval_context

    def test_error_turn_sets_error_field(self) -> None:
        trace = self._call(_error_payloads())
        assert trace.error == "ConnectionError: backend unreachable"
        assert trace.output is None
        assert trace.steps == ()
        assert trace.retrieval_context == ()
        assert trace.tools_called == ()

    def test_node_error_step_present_output_still_set(self) -> None:
        payloads = [
            {
                "kind": "tool_call",
                "tool_name": "prometheus.query",
                "call_id": "c3",
                "arguments": {},
            },
            {
                "kind": "tool_result",
                "tool_name": "prometheus.query",
                "call_id": "c3",
                "content": "",
                "is_error": True,
            },
            {
                "kind": "node_error",
                "node_id": "fetch_metrics",
                "error_message": "TimeoutError",
            },
            {
                "kind": "final",
                "content": "Using cached data instead.",
                "model_name": "m1",
                "finish_reason": "stop",
            },
        ]
        trace = self._call(payloads)
        assert trace.output == "Using cached data instead."
        assert trace.error is None
        kinds = [s.kind for s in trace.steps]
        assert "node_error" in kinds
        assert "final" in kinds

    def test_hitl_awaiting_human_step_no_output_no_error(self) -> None:
        trace = self._call(_hitl_payloads())
        assert trace.output is None
        assert trace.error is None
        kinds = [s.kind for s in trace.steps]
        assert "awaiting_human" in kinds
        assert trace.tools_called == ("bank.risk_guard.score_transfer",)

    def test_tools_called_order_matches_tool_call_order(self) -> None:
        payloads = [
            {
                "kind": "tool_call",
                "tool_name": "tool_a",
                "call_id": "c1",
                "arguments": {},
            },
            {
                "kind": "tool_result",
                "tool_name": "tool_a",
                "call_id": "c1",
                "content": "a",
                "is_error": False,
            },
            {
                "kind": "tool_call",
                "tool_name": "tool_b",
                "call_id": "c2",
                "arguments": {},
            },
            {
                "kind": "tool_result",
                "tool_name": "tool_b",
                "call_id": "c2",
                "content": "b",
                "is_error": False,
            },
            {
                "kind": "final",
                "content": "done",
                "model_name": "m",
                "finish_reason": "stop",
            },
        ]
        trace = self._call(payloads)
        assert trace.tools_called == ("tool_a", "tool_b")

    def test_errored_tool_result_not_in_retrieval_context(self) -> None:
        payloads = [
            {
                "kind": "tool_call",
                "tool_name": "bad_tool",
                "call_id": "c1",
                "arguments": {},
            },
            {
                "kind": "tool_result",
                "tool_name": "bad_tool",
                "call_id": "c1",
                "content": "error details",
                "is_error": True,
            },
            {
                "kind": "final",
                "content": "Fallback answer",
                "model_name": "m",
                "finish_reason": "stop",
            },
        ]
        trace = self._call(payloads)
        assert trace.retrieval_context == ()
        assert trace.output == "Fallback answer"

    def test_session_agent_input_passthrough(self) -> None:
        trace = self._call(
            [],
            input_text="my question",
            agent_id="my-agent",
            session_id="my-session",
        )
        assert trace.input == "my question"
        assert trace.agent_id == "my-agent"
        assert trace.session_id == "my-session"

    def test_returns_frozen_eval_trace(self) -> None:
        trace = self._call([])
        assert isinstance(trace, EvalTrace)
        import pytest

        with pytest.raises(Exception):
            trace.output = "mutated"  # type: ignore[misc]
