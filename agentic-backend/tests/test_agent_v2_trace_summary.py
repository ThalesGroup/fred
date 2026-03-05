import pytest

from agentic_backend.common.structures import Agent
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2.builtin_tools import (
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
)
from agentic_backend.core.agents.v2.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    ToolContentKind,
    ToolInvocationRequest,
)
from agentic_backend.integrations.v2_runtime.adapters import (
    FredKnowledgeSearchToolInvoker,
    _classify_trace_bottleneck,
    _extract_interesting_spans,
    _render_trace_digest_summary,
)


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="session-1",
            user_id="user-1",
            language="fr-FR",
        ),
        portable_context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="user:user-1",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id="session-1",
            agent_id="internal.react_profile.log_genius",
            user_id="user-1",
            user_name="user-1",
            team_id="team-1",
        ),
    )


def test_classify_trace_bottleneck_marks_instrumentation_gap_when_breakdown_missing() -> (
    None
):
    bottleneck, bottleneck_ms = _classify_trace_bottleneck(
        model_total_ms=0,
        tool_total_ms=0,
        await_human_total_ms=0,
        trace_total_ms=12_523,
        unclassified_total_ms=12_523,
        interesting_span_count=1,
    )

    assert bottleneck == "instrumentation_gap"
    assert bottleneck_ms == 12_523


def test_extract_interesting_spans_includes_langfuse_generations_as_model_rows() -> (
    None
):
    rows = _extract_interesting_spans(
        [
            {
                "type": "GENERATION",
                "name": "analysis",
                "model": "gpt-4o-mini",
                "latency": 321,
                "startTime": "2026-03-03T04:37:14.100Z",
                "endTime": "2026-03-03T04:37:14.421Z",
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "langfuse.generation"
    assert row["category"] == "model"
    assert row["operation_label"] == "analysis"
    assert row["model_name"] == "gpt-4o-mini"
    assert row["latency_ms"] == 321


def test_render_trace_digest_summary_reports_instrumentation_gap_fields() -> None:
    summary = _render_trace_digest_summary(
        {
            "status": "ok",
            "selected_trace": {
                "trace_id": "trace-1",
                "agent_name": "Sammy",
                "fred_session_id": "session-1",
            },
            "bottleneck": "instrumentation_gap",
            "bottleneck_ms": 12_523,
            "trace_total_ms": 12_523,
            "model_total_ms": 0,
            "tool_total_ms": 0,
            "await_human_total_ms": 0,
            "unclassified_total_ms": 12_523,
            "instrumentation_gap_detected": True,
        }
    )

    assert "- bottleneck: instrumentation_gap (12523 ms)" in summary
    assert "- instrumentation_gap_detected: true" in summary
    assert "- unclassified_total_ms: 12523" in summary


def test_extract_interesting_spans_classifies_react_model_span_as_model() -> None:
    rows = _extract_interesting_spans(
        [
            {
                "type": "SPAN",
                "name": "v2.react.model",
                "latency": 245,
                "startTime": "2026-03-03T04:37:14.100Z",
                "endTime": "2026-03-03T04:37:14.345Z",
                "metadata": {"operation": "model_call", "model_name": "gpt-5-mini"},
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "v2.react.model"
    assert row["category"] == "model"
    assert row["operation_label"] == "model_call"
    assert row["model_name"] == "gpt-5-mini"
    assert row["latency_ms"] == 245


@pytest.mark.asyncio
async def test_traces_summarize_conversation_returns_disabled_status_when_langfuse_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    binding = _binding()
    fake_invoker = type(
        "FakeTraceInvoker",
        (),
        {
            "_binding": binding,
            "_settings": Agent(id="log-genius", name="LogGenius", team_id="team-1"),
        },
    )()
    result = await FredKnowledgeSearchToolInvoker._invoke_traces_summarize_conversation(
        fake_invoker,
        ToolInvocationRequest(
            tool_ref=TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
            payload={},
            context=binding.portable_context,
        ),
    )

    assert result.is_error is False
    assert len(result.blocks) == 2
    text_block, json_block = result.blocks
    assert text_block.kind == ToolContentKind.TEXT
    assert text_block.text is not None
    assert "not enabled" in text_block.text
    assert json_block.kind == ToolContentKind.JSON
    assert json_block.data is not None
    assert json_block.data.get("status") == "disabled"
    assert json_block.data.get("reason") == "langfuse_not_configured"
