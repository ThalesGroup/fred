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

import gc

from fred_core.kpi.kpi_writer_structures import KPIEvent, Metric


def _make_event(i: int = 0) -> KPIEvent:
    return KPIEvent(
        metric=Metric(name="test.metric", type="counter", value=float(i)),
        labels=["a", "b", "c"],
    )


def test_kpievent_labels_validates_to_a_concrete_list():
    """`labels` must validate to a plain `list`, not something pydantic-core wraps
    lazily. `Iterable[str]` does this via a `ValidatorIterator` even when fed an
    already-materialized list — confirmed live (fredlab, 2026-07-31) to leave a
    reference cycle behind on every KPIEvent construction. See ISSUE-010."""
    event = _make_event()
    assert type(event.labels) is list
    assert event.labels == ["a", "b", "c"]


def test_kpievent_construction_leaves_no_reference_cycles():
    """Regression test for the ValidatorIterator cycle itself: constructing many
    KPIEvents and dropping every reference must free them via plain refcounting
    alone, leaving nothing cyclic behind. Asserts on the specific types involved
    (ValidatorIterator/KPIEvent) rather than a bare `gc.collect() == 0`, since an
    unrelated cyclic object created elsewhere in the test process would otherwise
    make this flaky. gc.DEBUG_SAVEALL is scoped to this one collection and cleared
    up afterward so nothing stays pinned in gc.garbage."""
    gc.collect()
    old_flags = gc.get_debug()
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        for i in range(200):
            _make_event(i)
        gc.collect()
        leaked_types = {type(obj).__name__ for obj in gc.garbage}
    finally:
        gc.garbage.clear()
        gc.set_debug(old_flags)
        gc.collect()
    assert "ValidatorIterator" not in leaked_types
    assert "KPIEvent" not in leaked_types
