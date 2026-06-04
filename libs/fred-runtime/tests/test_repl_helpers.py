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
Offline unit tests for the pure-function slice of fred_runtime.cli.repl_helpers.

Only covers functions with no I/O or terminal side effects:
  fmt_bytes, parse_mode_command, parse_tuning_value.

The print_* functions (print_help, print_inspect, print_tuning_table) are
terminal-output helpers — not tested here.
"""

from __future__ import annotations

import pytest

from fred_runtime.cli.repl_helpers import (
    fmt_bytes,
    parse_mode_command,
    parse_tuning_value,
)

# ---------------------------------------------------------------------------
# fmt_bytes
# ---------------------------------------------------------------------------


class TestFmtBytes:
    def test_zero(self) -> None:
        assert fmt_bytes(0) == "0 B"

    def test_below_kb(self) -> None:
        assert fmt_bytes(512) == "512 B"

    def test_exact_kb(self) -> None:
        assert fmt_bytes(1024) == "1.0 KB"

    def test_fractional_kb(self) -> None:
        assert fmt_bytes(1536) == "1.5 KB"

    def test_below_mb(self) -> None:
        assert fmt_bytes(1023 * 1024) == "1023.0 KB"

    def test_exact_mb(self) -> None:
        assert fmt_bytes(1024 * 1024) == "1.0 MB"

    def test_fractional_mb(self) -> None:
        assert fmt_bytes(int(2.5 * 1024 * 1024)) == "2.5 MB"


# ---------------------------------------------------------------------------
# parse_mode_command
# ---------------------------------------------------------------------------


class TestParseModeCommand:
    def test_stream_mode(self) -> None:
        assert parse_mode_command("/mode stream") == "stream"

    def test_final_mode(self) -> None:
        assert parse_mode_command("/mode final") == "final"

    def test_eval_mode(self) -> None:
        assert parse_mode_command("/mode eval") == "eval"

    def test_case_insensitive(self) -> None:
        assert parse_mode_command("/mode STREAM") == "stream"

    def test_extra_whitespace(self) -> None:
        assert parse_mode_command("/mode   final  ") == "final"

    def test_bare_mode_command_returns_none(self) -> None:
        assert parse_mode_command("/mode") is None

    def test_mode_with_only_spaces_returns_none(self) -> None:
        assert parse_mode_command("/mode   ") is None

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown mode"):
            parse_mode_command("/mode turbo")


# ---------------------------------------------------------------------------
# parse_tuning_value
# ---------------------------------------------------------------------------


class TestParseTuningValue:
    def test_true_bool(self) -> None:
        assert parse_tuning_value("true") is True

    def test_false_bool(self) -> None:
        assert parse_tuning_value("false") is False

    def test_bool_case_insensitive(self) -> None:
        assert parse_tuning_value("True") is True
        assert parse_tuning_value("FALSE") is False

    def test_integer(self) -> None:
        assert parse_tuning_value("42") == 42
        assert isinstance(parse_tuning_value("42"), int)

    def test_negative_integer(self) -> None:
        assert parse_tuning_value("-7") == -7

    def test_float(self) -> None:
        assert parse_tuning_value("3.14") == pytest.approx(3.14)
        assert isinstance(parse_tuning_value("3.14"), float)

    def test_negative_float(self) -> None:
        assert parse_tuning_value("-0.5") == pytest.approx(-0.5)

    def test_plain_string(self) -> None:
        assert parse_tuning_value("hello") == "hello"

    def test_string_with_spaces(self) -> None:
        assert parse_tuning_value("hello world") == "hello world"

    def test_empty_string(self) -> None:
        assert parse_tuning_value("") == ""

    def test_integer_not_coerced_to_float(self) -> None:
        result = parse_tuning_value("10")
        assert isinstance(result, int)
        assert not isinstance(result, float)
