"""Isolated synthetic producer; OTLP endpoint provided by the test harness."""

import json
import sys
from fred_core.portable.observability import set_tracer
from fred_core.technical_tracing import activate_span, extract_trace, technical_span
from fred_runtime.app.technical_tracing import OTLPTracer
from fred_sdk.contracts.context import PortableContext, PortableEnvironment

tracer = OTLPTracer(collector_endpoint=sys.argv[1])
set_tracer(tracer)
context = PortableContext(
    request_id="synthetic-request",
    correlation_id="synthetic-correlation",
    actor="synthetic-user",
    tenant="synthetic",
    environment=PortableEnvironment.DEV,
    session_id="synthetic-session",
    user_id="synthetic-user",
    agent_name="Synthetic",
    baggage={"exchange_id": "synthetic-exchange"},
)
try:
    with technical_span(
        "agent.http",
        context=extract_trace(
            {
                "traceparent": f"00-{'a' * 32}-{'b' * 16}-01",
            }
        ),
    ):
        root = tracer.start_span("agent.stream", context=context)
        root.set_io(input="synthetic-private-input", output="synthetic-private-output")
        model = tracer.start_span("v2.react.model", context=context, parent=root)
        model.set_usage(
            model="synthetic-model",
            usage={"input": 3, "output": 5},
            cost={"total": 0.1},
        )
        model.set_attribute("first_chunk_ms", 12.5)
        model.set_attribute("secret", "synthetic-private-metadata")
        model.set_io(
            input="synthetic-private-prompt", output="synthetic-private-answer"
        )
        model.end()
        tool = tracer.start_span("tool.invoke", context=context, parent=root)
        with activate_span(tool):
            with technical_span("mcp.http"):
                pass
        tool.end()
        root.end()
    print(
        json.dumps(
            {"trace_id": "a" * 32, "root_parent_span_id": "b" * 16, "span_count": 5}
        )
    )
    tracer.provider.force_flush()
finally:
    tracer.shutdown()
