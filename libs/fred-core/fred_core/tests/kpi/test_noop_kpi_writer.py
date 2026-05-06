"""
Offline unit tests for fred_core.kpi.noop_kpi_writer.NoOpKPIWriter.

The NoOp writer is used in every unit and integration test that instruments
code with the KPI API. If its contract is broken (timer doesn't yield a
mutable Dims dict, timed() fails to call the function, etc.) every caller
silently misbehaves.

Focus: verify the contract is honoured, not that operations do nothing.
"""

from __future__ import annotations

from fred_core.kpi.kpi_writer_structures import Dims, KPIActor
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter

ACTOR = KPIActor(type="system")


class TestNoOpKPIWriterEmitPrimitives:
    def setup_method(self) -> None:
        self.writer = NoOpKPIWriter()

    def test_emit_does_not_raise(self) -> None:
        self.writer.emit(name="test.metric", type="counter", actor=ACTOR)

    def test_count_does_not_raise(self) -> None:
        self.writer.count("test.count", actor=ACTOR)

    def test_gauge_does_not_raise(self) -> None:
        self.writer.gauge("test.gauge", 3.14, actor=ACTOR)

    def test_log_llm_does_not_raise(self) -> None:
        self.writer.log_llm(model="gpt-4o", tokens=100, actor=ACTOR)

    def test_doc_used_does_not_raise(self) -> None:
        self.writer.doc_used(doc_id="d1", actor=ACTOR)

    def test_api_call_does_not_raise(self) -> None:
        self.writer.api_call(endpoint="/test", actor=ACTOR)

    def test_api_error_does_not_raise(self) -> None:
        self.writer.api_error(endpoint="/test", status=500, actor=ACTOR)

    def test_record_error_does_not_raise(self) -> None:
        self.writer.record_error(error="oops", actor=ACTOR)


class TestNoOpKPIWriterTimerContract:
    def setup_method(self) -> None:
        self.writer = NoOpKPIWriter()

    def test_timer_context_manager_enters_and_exits(self) -> None:
        with self.writer.timer("test.timer", actor=ACTOR):
            pass  # must not raise

    def test_timer_yields_mutable_dims_dict(self) -> None:
        with self.writer.timer("test.timer", actor=ACTOR) as d:
            assert isinstance(d, dict)
            d["agent_id"] = "test-agent"
        # mutation must not raise

    def test_timer_with_initial_dims_yields_copy(self) -> None:
        initial: Dims = {"phase": "routing"}
        with self.writer.timer("test.timer", dims=initial, actor=ACTOR) as d:
            assert d["phase"] == "routing"
            d["extra"] = "added"
        assert "extra" not in initial  # original not mutated

    def test_timer_without_dims_yields_empty_dict(self) -> None:
        with self.writer.timer("test.timer", actor=ACTOR) as d:
            assert d == {}

    def test_timer_does_not_swallow_exceptions(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="deliberate"):
            with self.writer.timer("test.timer", actor=ACTOR):
                raise ValueError("deliberate")


class TestNoOpKPIWriterTimedDecorator:
    def setup_method(self) -> None:
        self.writer = NoOpKPIWriter()

    def test_timed_calls_wrapped_function(self) -> None:
        called: list[bool] = []

        @self.writer.timed("test.timed", actor=ACTOR)
        def my_fn() -> str:
            called.append(True)
            return "result"

        result = my_fn()
        assert result == "result"
        assert called == [True]

    def test_timed_propagates_return_value(self) -> None:
        @self.writer.timed("test.timed", actor=ACTOR)
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    def test_timed_propagates_exceptions(self) -> None:
        import pytest

        @self.writer.timed("test.timed", actor=ACTOR)
        def explode() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            explode()
