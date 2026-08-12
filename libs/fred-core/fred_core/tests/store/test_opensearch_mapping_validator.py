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

"""Tests for the additive-mapping diff shared by the OpenSearch stores.

`missing_mapping_branches` is what lets `ensure_index_mapping` repair an index
created by an older version instead of hard-failing startup on it. Its contract
is narrow on purpose: report what is *absent*, never what merely differs.

The orchestration around it (read once, patch, validate) is exercised end to end
through the stores that call it — see `tests/kpi/test_opensearch_kpi_store_
ensure_ready.py` and `tests/logs/test_opensearch_log_store_ensure_ready.py`.
"""

from __future__ import annotations

from fred_core.store.opensearch_mapping_validator import missing_mapping_branches


def test_reports_nothing_when_the_live_index_already_matches() -> None:
    expected = {"dims": {"properties": {"env": {"type": "keyword"}}}}

    assert missing_mapping_branches(expected, expected) == {}


def test_reports_a_missing_leaf_with_its_expected_definition() -> None:
    expected = {
        "dims": {
            "properties": {"env": {"type": "keyword"}, "team_id": {"type": "keyword"}}
        }
    }
    current = {"dims": {"properties": {"env": {"type": "keyword"}}}}

    assert missing_mapping_branches(expected, current) == {
        "dims": {"properties": {"team_id": {"type": "keyword"}}}
    }


def test_reports_a_missing_object_whole() -> None:
    """A branch the live index never had is carried over with all its leaves."""
    expected = {"trace": {"properties": {"trace_id": {"type": "keyword"}}}}

    assert missing_mapping_branches(expected, {}) == expected


def test_ignores_a_field_whose_type_drifted() -> None:
    """put_mapping cannot retype a field, and one rejected field fails the whole
    request — so drift is left for validate_index_mapping to report."""
    expected = {"dims": {"properties": {"env": {"type": "keyword"}}}}
    current = {"dims": {"properties": {"env": {"type": "text"}}}}

    assert missing_mapping_branches(expected, current) == {}


def test_ignores_an_object_the_live_index_holds_as_a_leaf() -> None:
    """Same reasoning one level up: `dims` mapped as a keyword cannot grow
    properties, so nothing under it is patchable."""
    expected = {"dims": {"properties": {"env": {"type": "keyword"}}}}
    current = {"dims": {"type": "keyword"}}

    assert missing_mapping_branches(expected, current) == {}
