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

"""Unit tests for `_cap_warnings` (MIGR-05 cutover-scale hardening, #2127).

`MigrationResult.warnings` ends up in a `pg_notify` payload capped at ~8000 bytes
by Postgres. A cutover-scale bundle can blow past that either with many short
warning lines or with a single very long one (an uncapped comma-joined id list) —
`_cap_warnings` must bound the serialized byte size in both cases, not just the
line count.
"""

from __future__ import annotations

from control_plane_backend.import_export.importer import (
    _MAX_WARNINGS_BYTES,
    _cap_warnings,
)


def test_cap_warnings_passes_through_when_under_budget():
    warnings = [f"warning {i}" for i in range(10)]
    assert _cap_warnings(warnings) == warnings


def test_cap_warnings_bounds_many_short_lines_by_byte_budget():
    warnings = ["w" * 50 for _ in range(200)]  # 10 000 bytes raw, over budget

    result = _cap_warnings(warnings)

    total_bytes = sum(len(line.encode("utf-8")) for line in result)
    assert total_bytes <= _MAX_WARNINGS_BYTES + 100  # + summary line headroom
    assert result[-1].startswith("…")
    assert len(result) < len(warnings)


def test_cap_warnings_truncates_a_single_line_larger_than_the_whole_budget():
    # e.g. an uncapped ", ".join(...) of thousands of team ids — the exact
    # shape that a line-count-only cap (the original fix) does not bound.
    warnings = ["x" * 20_000]

    result = _cap_warnings(warnings)

    total_bytes = sum(len(line.encode("utf-8")) for line in result)
    assert total_bytes <= _MAX_WARNINGS_BYTES + 100
    assert len(result) == 1
    assert result[0].endswith("…")
