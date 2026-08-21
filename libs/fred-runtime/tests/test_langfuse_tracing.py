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
Langfuse trace shape: session grouping, typed observations, and the content gate.

The rule under test that matters most is the last one: content capture is off
unless explicitly enabled, because `OBSERVABILITY-AND-AUDIT.md` §7 excludes
prompts and tool payloads from every observability stream.
"""

from typing import Any, cast

from fred_runtime.integrations.v2_runtime.adapters import (
    LangfuseTracerAdapter,
    langfuse_content_capture_enabled,
    langfuse_max_content_chars,
)
from fred_sdk.contracts.context import PortableContext, PortableEnvironment


class _FakeOtelSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        self.attributes.update(attributes)


class _FakeObservation:
    def __init__(self) -> None:
        self.id = "obs-1"
        self.updates: list[dict[str, Any]] = []
        self.ended = False
        self._otel_span = _FakeOtelSpan()

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def end(self, *, end_time: int | None = None) -> None:
        self.ended = True


class _FakeLangfuse:
    def __init__(self) -> None:
        self.seeds: list[str] = []
        self.observations: list[_FakeObservation] = []
        self.start_kwargs: list[dict[str, Any]] = []

    def create_trace_id(self, seed: str) -> str:
        self.seeds.append(seed)
        return f"trace-{seed}"

    def start_observation(self, **kwargs: Any) -> _FakeObservation:
        self.start_kwargs.append(kwargs)
        observation = _FakeObservation()
        self.observations.append(observation)
        return observation


def _context(**overrides: Any) -> PortableContext:
    base: dict[str, Any] = {
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "actor": "alice",
        "tenant": "fred",
        "environment": PortableEnvironment.DEV,
        "agent_id": "rag-agent",
        "agent_name": "rag-agent",
        "session_id": "sess-42",
        "user_id": "user-7",
        "team_id": "team-red",
        "baggage": {"exchange_id": "exch-9", "execution_action": "execute"},
    }
    base.update(overrides)
    return PortableContext(**base)


def _tracer(**kwargs: Any) -> tuple[LangfuseTracerAdapter, _FakeLangfuse]:
    fake = _FakeLangfuse()
    return LangfuseTracerAdapter(cast(Any, fake), **kwargs), fake


# ---------------------------------------------------------------------------
# Session grouping
# ---------------------------------------------------------------------------


def test_session_and_user_reach_langfuse_native_trace_fields() -> None:
    """Without these, Langfuse's Sessions and Users views stay empty."""

    tracer, fake = _tracer()
    tracer.start_span("agent.stream", context=_context())

    attributes = fake.observations[0]._otel_span.attributes
    assert attributes["session.id"] == "sess-42"
    assert attributes["user.id"] == "user-7"


def test_trace_is_named_after_the_agent_and_tagged() -> None:
    tracer, fake = _tracer()
    tracer.start_span("agent.stream", context=_context())

    attributes = fake.observations[0]._otel_span.attributes
    assert attributes["langfuse.trace.name"] == "rag-agent"
    assert attributes["langfuse.trace.tags"] == ["team-red", "execute", "dev"]


def test_only_the_turn_root_names_the_trace() -> None:
    """A model call must not rename the trace it belongs to."""

    tracer, fake = _tracer()
    tracer.start_span("v2.react.model", context=_context())

    attributes = fake.observations[0]._otel_span.attributes
    assert "langfuse.trace.name" not in attributes
    # Identity still propagates, so per-session aggregation covers every span.
    assert attributes["session.id"] == "sess-42"


def test_every_span_of_one_turn_shares_one_trace() -> None:
    tracer, fake = _tracer()
    context = _context()
    tracer.start_span("agent.stream", context=context)
    tracer.start_span("v2.react.model", context=context)
    tracer.start_span("tool.invoke", context=context)

    assert len(set(fake.seeds)) == 1


def test_a_resume_rejoins_the_trace_of_the_exchange_it_resumes() -> None:
    """
    A HITL resume is a new request with a fresh `request_id` but the same
    exchange. Seeding on `request_id` split it into a second, parentless trace.
    """

    tracer, fake = _tracer()
    tracer.start_span("agent.stream", context=_context(request_id="req-1"))
    tracer.start_span(
        "agent.stream",
        context=_context(
            request_id="req-2",
            baggage={"exchange_id": "exch-9", "execution_action": "resume"},
        ),
    )

    assert fake.seeds[0] == fake.seeds[1] == "exch-9"


def test_two_turns_of_one_session_are_two_traces() -> None:
    """Collapsing a whole conversation into one trace makes it unreadable."""

    tracer, fake = _tracer()
    tracer.start_span("agent.stream", context=_context(baggage={"exchange_id": "e1"}))
    tracer.start_span("agent.stream", context=_context(baggage={"exchange_id": "e2"}))

    assert fake.seeds[0] != fake.seeds[1]
    for observation in fake.observations:
        assert observation._otel_span.attributes["session.id"] == "sess-42"


def test_an_upstream_trace_id_still_wins() -> None:
    tracer, fake = _tracer()
    tracer.start_span("agent.stream", context=_context(trace_id="trace-upstream"))

    assert fake.seeds == ["trace-upstream"]


# ---------------------------------------------------------------------------
# Observation typing
# ---------------------------------------------------------------------------


def test_span_names_map_to_langfuse_observation_types() -> None:
    """Only a `generation` renders model, token, and cost columns."""

    tracer, fake = _tracer()
    for name in (
        "agent.stream",
        "v2.react.model",
        "tool.invoke",
        "v2.graph.await_human",
    ):
        tracer.start_span(name, context=_context())

    assert [kwargs["as_type"] for kwargs in fake.start_kwargs] == [
        "agent",
        "generation",
        "tool",
        "span",
    ]


# ---------------------------------------------------------------------------
# Content gate (OBSERVABILITY-AND-AUDIT.md §7)
# ---------------------------------------------------------------------------


def test_content_capture_is_off_by_default() -> None:
    tracer, _ = _tracer()
    assert tracer.captures_content is False


def test_content_is_dropped_when_capture_is_disabled() -> None:
    tracer, fake = _tracer()
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_io(input=[{"role": "user", "content": "my private question"}])
    span.set_io(output="the private answer")
    span.end()

    flushed = fake.observations[0].updates
    assert all("input" not in update for update in flushed)
    assert all("output" not in update for update in flushed)


def test_content_is_exported_when_capture_is_enabled() -> None:
    tracer, fake = _tracer(capture_content=True)
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_io(input=[{"role": "user", "content": "question"}], output="answer")
    span.end()

    update = fake.observations[0].updates[0]
    assert update["input"] == [{"role": "user", "content": "question"}]
    assert update["output"] == "answer"


def test_long_payloads_are_truncated_with_a_visible_marker() -> None:
    tracer, fake = _tracer(capture_content=True, max_content_chars=100)
    span = tracer.start_span("tool.invoke", context=_context())
    span.set_io(output={"hits": ["x" * 500]})
    span.end()

    output = cast(dict[str, Any], fake.observations[0].updates[0]["output"])
    assert output["hits"][0] == "x" * 100 + "…[truncated 400 chars]"


def test_the_budget_bounds_the_whole_payload_not_each_string() -> None:
    """
    Every model call of a ReAct turn re-exports the whole transcript, which
    grows with each tool round. A per-string cap alone leaves the payload
    unbounded in the number of strings.
    """

    tracer, fake = _tracer(capture_content=True, max_content_chars=200)
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_io(
        input=[
            {"content": "a" * 150},
            {"content": "b" * 150},
            {"content": "c" * 150},
        ]
    )
    span.end()

    payload = cast(list[dict[str, Any]], fake.observations[0].updates[0]["input"])
    # Spent newest-first: the last message is whole, the middle one is cut at
    # the remaining 50, and the oldest is past the budget entirely.
    assert payload[2]["content"] == "c" * 150
    assert payload[1]["content"] == "b" * 50 + "…[truncated 100 chars]"
    assert payload[0]["content"] == "…[truncated 150 chars]"


def test_short_structural_strings_are_never_mangled() -> None:
    """
    Replacing `"system"` with a 24-character marker grows the payload while
    destroying the field's meaning.
    """

    tracer, fake = _tracer(capture_content=True, max_content_chars=1)
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_io(input=[{"role": "system", "name": "search", "content": "x" * 500}])
    span.end()

    payload = cast(list[dict[str, Any]], fake.observations[0].updates[0]["input"])
    assert payload[0]["role"] == "system"
    assert payload[0]["name"] == "search"
    assert payload[0]["content"].endswith("…[truncated 500 chars]")


def test_a_verbose_system_prompt_cannot_blank_out_the_question() -> None:
    """
    A message list starts with the system prompt, which carries every tool's
    JSON schema. Spending the budget front-to-back let that boilerplate eat it
    all and truncate away the two things a trace reader actually wants.
    """

    tracer, fake = _tracer(capture_content=True, max_content_chars=20)
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_io(
        input=[
            {"role": "system", "content": "S" * 5000},
            {"role": "user", "content": "what is fred?"},
        ]
    )
    span.end()

    payload = cast(list[dict[str, Any]], fake.observations[0].updates[0]["input"])
    # Order is preserved; the budget went to the most recent message.
    assert payload[0]["role"] == "system"
    assert payload[1]["content"] == "what is fred?"
    assert payload[0]["content"].startswith("…[truncated")


def test_the_env_var_overrides_the_budget() -> None:
    """
    `build_default_tracer` never reads configuration.yaml, so on a pod with
    `tracer: logging` plus Langfuse keys this env var is the only knob.
    """

    assert langfuse_max_content_chars(1234) == 1234


def test_a_bad_budget_env_value_falls_back_instead_of_disabling_truncation(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("LANGFUSE_MAX_CONTENT_CHARS", "not-a-number")
    assert langfuse_max_content_chars(999) == 999
    monkeypatch.setenv("LANGFUSE_MAX_CONTENT_CHARS", "0")
    assert langfuse_max_content_chars(999) == 999
    monkeypatch.setenv("LANGFUSE_MAX_CONTENT_CHARS", "-5")
    assert langfuse_max_content_chars(999) == 999
    monkeypatch.setenv("LANGFUSE_MAX_CONTENT_CHARS", "250000")
    assert langfuse_max_content_chars(999) == 250000


def test_structure_survives_truncation() -> None:
    """Cutting the serialized JSON instead would produce invalid JSON."""

    tracer, fake = _tracer(capture_content=True, max_content_chars=1)
    span = tracer.start_span("tool.invoke", context=_context())
    span.set_io(input={"query": "hello", "top_k": 8, "flags": [True, None]})
    span.end()

    payload = cast(dict[str, Any], fake.observations[0].updates[0]["input"])
    assert payload["top_k"] == 8
    assert payload["flags"] == [True, None]
    assert payload["query"].startswith("h")


def test_env_var_overrides_the_configured_default() -> None:
    assert langfuse_content_capture_enabled(False) is False
    assert langfuse_content_capture_enabled(True) is True


def test_env_var_parsing(monkeypatch: Any) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_CONTENT", "true")
    assert langfuse_content_capture_enabled(False) is True
    monkeypatch.setenv("LANGFUSE_CAPTURE_CONTENT", "false")
    assert langfuse_content_capture_enabled(True) is False


# ---------------------------------------------------------------------------
# Usage, errors, flush behaviour
# ---------------------------------------------------------------------------


def test_usage_is_recorded_even_when_content_capture_is_off() -> None:
    """Token counts are technical measurement, not content — always exported."""

    tracer, fake = _tracer()
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_usage(model="gpt-4o", usage={"input": 812, "output": 96})
    span.end()

    update = fake.observations[0].updates[0]
    assert update["model"] == "gpt-4o"
    assert update["usage_details"] == {"input": 812, "output": 96}


def test_usage_on_a_span_like_observation_falls_back_to_metadata() -> None:
    """
    Langfuse keeps model/usage/cost only on generation-like observations; on an
    `agent`/`tool`/`span` it drops them without warning, so a turn total
    recorded on the `agent.stream` root vanished silently.
    """

    tracer, fake = _tracer()
    span = tracer.start_span("agent.stream", context=_context())
    span.set_usage(
        model="mistral-small-latest", usage={"input": 812, "output": 96, "total": 908}
    )
    span.end()

    update = fake.observations[0].updates[0]
    # Not sent as fields Langfuse would discard...
    assert "usage_details" not in update
    assert "model" not in update
    # ...but still readable on the span.
    metadata = cast(dict[str, Any], update["metadata"])
    assert metadata["usage_input"] == 812
    assert metadata["usage_output"] == 96
    assert metadata["usage_total"] == 908
    assert metadata["model_name"] == "mistral-small-latest"


def test_a_generation_keeps_usage_as_first_class_fields() -> None:
    """The per-call generation is where Langfuse aggregates trace totals from."""

    tracer, fake = _tracer()
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_usage(model="mistral-small-latest", usage={"input": 812})
    span.end()

    update = fake.observations[0].updates[0]
    assert update["usage_details"] == {"input": 812}
    assert update["model"] == "mistral-small-latest"


def test_error_status_becomes_a_langfuse_error_level() -> None:
    tracer, fake = _tracer()
    span = tracer.start_span("tool.invoke", context=_context())
    span.set_attribute("status", "error")
    span.end()

    assert fake.observations[0].updates[0]["level"] == "ERROR"


def test_a_successful_span_carries_no_error_level() -> None:
    tracer, fake = _tracer()
    span = tracer.start_span("tool.invoke", context=_context())
    span.set_attribute("status", "ok")
    span.end()

    assert "level" not in fake.observations[0].updates[0]


def test_a_span_flushes_once_and_ends_once() -> None:
    """One SDK call per span, not one per recorded attribute."""

    tracer, fake = _tracer(capture_content=True)
    span = tracer.start_span("v2.react.model", context=_context())
    span.set_attribute("status", "ok")
    span.set_attribute("finish_reason", "stop")
    span.set_io(input="in", output="out")
    span.set_usage(model="gpt-4o", usage={"input": 1})
    span.end()
    span.end()

    observation = fake.observations[0]
    assert len(observation.updates) == 1
    assert observation.ended is True


def test_the_turn_root_mirrors_io_to_the_trace_row() -> None:
    """The Langfuse trace list shows trace-level io, not the root span's."""

    tracer, fake = _tracer(capture_content=True)
    span = tracer.start_span("agent.stream", context=_context())
    span.set_io(input="what is fred?", output="a platform.")
    span.end()

    attributes = fake.observations[0]._otel_span.attributes
    assert attributes["langfuse.trace.input"] == "what is fred?"
    assert attributes["langfuse.trace.output"] == "a platform."


def test_a_child_span_does_not_overwrite_the_trace_row() -> None:
    tracer, fake = _tracer(capture_content=True)
    root = tracer.start_span("agent.stream", context=_context())
    child = tracer.start_span("v2.react.model", context=_context(), parent=root)
    child.set_io(input="inner prompt", output="inner answer")
    child.end()

    attributes = fake.observations[1]._otel_span.attributes
    assert "langfuse.trace.input" not in attributes
    assert "langfuse.trace.output" not in attributes


def test_a_failed_flush_still_closes_the_span() -> None:
    """
    Tracing degrades the trace, never the agent — and a span left open renders
    as a turn that never finished, skewing every duration in the trace.
    """

    tracer, fake = _tracer()
    span = tracer.start_span("v2.react.model", context=_context())

    def _boom(**kwargs: Any) -> None:
        raise RuntimeError("langfuse is down")

    fake.observations[0].update = _boom  # type: ignore[method-assign]
    span.set_attribute("status", "ok")
    span.end()  # must not raise

    assert fake.observations[0].ended is True


def test_a_failure_to_end_is_swallowed_too() -> None:
    tracer, fake = _tracer()
    span = tracer.start_span("v2.react.model", context=_context())

    def _boom(**kwargs: Any) -> None:
        raise RuntimeError("langfuse is down")

    fake.observations[0].end = _boom  # type: ignore[method-assign]
    span.end()  # must not raise
