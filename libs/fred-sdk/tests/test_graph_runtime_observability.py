from typing import cast

from fred_core.portable import InMemoryMetricsProvider, Span, Tracer
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from fred_sdk.graph.graph_runtime import _graph_phase_timer, _start_runtime_span


class _RecordingSpan(Span):
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.ended = False

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True


class _RecordingTracer(Tracer):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def start_span(self, name: str, *, context=None, attributes=None, **kwargs) -> Span:  # type: ignore[override]
        span = _RecordingSpan()
        self.calls.append(
            {
                "name": name,
                "context": context,
                "attributes": dict(attributes or {}),
                "span": span,
            }
        )
        return span


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="sess-1",
            checkpoint_id="cp-1",
            user_id="alice",
            team_id="team-red",
            trace_id="trace-1",
            correlation_id="corr-1",
            agent_instance_id="inst-1",
            template_agent_id="template-1",
            execution_action="resume",
        ),
        portable_context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            trace_id="trace-1",
            agent_id="template-1",
            agent_name="template-1",
            session_id="sess-1",
            user_id="alice",
            team_id="team-red",
            baggage={
                "agent_instance_id": "inst-1",
                "template_agent_id": "template-1",
                "checkpoint_id": "cp-1",
                "execution_action": "resume",
            },
        ),
    )


def test_graph_phase_timer_includes_managed_observability_dims() -> None:
    metrics = InMemoryMetricsProvider()
    binding = _binding()

    with _graph_phase_timer(
        metrics=metrics,
        binding=binding,
        agent_id="template-1",
        phase="graph_turn",
        agent_step="execute",
    ):
        pass

    assert len(metrics.timers) == 1
    dims = metrics.timers[0].dims
    assert dims["user_id"] == "alice"
    assert dims["team_id"] == "team-red"
    assert dims["session_id"] == "sess-1"
    assert dims["agent_instance_id"] == "inst-1"
    assert dims["template_agent_id"] == "template-1"
    assert dims["checkpoint_id"] == "cp-1"
    assert dims["trace_id"] == "trace-1"
    assert dims["correlation_id"] == "corr-1"
    assert dims["execution_action"] == "resume"


def test_start_runtime_span_includes_managed_observability_attrs() -> None:
    tracer = _RecordingTracer()
    binding = _binding()

    span = _start_runtime_span(
        services=RuntimeServices(tracer=tracer),
        binding=binding,
        name="agent.run",
        attributes={"status": "ok"},
    )

    assert span is not None
    assert len(tracer.calls) == 1
    attrs = cast(dict[str, object], tracer.calls[0]["attributes"])
    assert attrs["status"] == "ok"
    assert attrs["user_id"] == "alice"
    assert attrs["team_id"] == "team-red"
    assert attrs["session_id"] == "sess-1"
    assert attrs["agent_instance_id"] == "inst-1"
    assert attrs["template_agent_id"] == "template-1"
    assert attrs["checkpoint_id"] == "cp-1"
    assert attrs["trace_id"] == "trace-1"
    assert attrs["correlation_id"] == "corr-1"
    assert attrs["execution_action"] == "resume"
