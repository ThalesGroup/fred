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

"""Unit tests for the plain-data helper functions in `features/scheduler/workflow.py`.

The `@workflow.defn` classes themselves need a live Temporal (test) environment to
execute — not used elsewhere in this repo (see `test_temporal_scheduler.py`, which
only tests the module's plain helper functions) — so MIGR-07's revectorize decision
logic is kept in a pure, directly-testable helper (`_wf_should_skip_revectorize`),
mirroring the existing `_wf_*` helpers.
"""

from __future__ import annotations

import pytest

from knowledge_flow_backend.features.scheduler.workflow import (
    _wf_final_revectorize_state,
    _wf_should_skip_revectorize,
)


@pytest.mark.parametrize(
    ("mode", "force", "chunk_count", "expected"),
    [
        # incremental + already vectorized + not forced -> skip
        ("incremental", False, 3, True),
        # incremental but no vectors yet -> don't skip, needs (re)embedding
        ("incremental", False, 0, False),
        # force always re-embeds, even if already vectorized
        ("incremental", True, 3, False),
        # full mode always re-embeds every in-scope doc (RFC §4)
        ("full", False, 3, False),
        ("full", True, 3, False),
        ("full", False, 0, False),
    ],
)
def test_should_skip_revectorize_matches_rfc_scope_semantics(mode, force, chunk_count, expected) -> None:
    assert _wf_should_skip_revectorize(mode=mode, force=force, chunk_count=chunk_count) is expected


def test_final_revectorize_state_is_succeeded_when_nothing_failed() -> None:
    assert _wf_final_revectorize_state(failed=0, total=5) == ("succeeded", None)


def test_final_revectorize_state_is_failed_when_any_document_failed() -> None:
    """The terminal-status regression this fixes: previously the workflow
    always emitted `"succeeded"` regardless of `failed`, silently hiding
    per-document failures (e.g. the cross-team CSV permission gap
    `output_process_trusted` fixes) behind an apparently clean run."""
    state, error = _wf_final_revectorize_state(failed=2, total=5)
    assert state == "failed"
    assert error == "2 of 5 document(s) failed to re-vectorize"


def test_final_revectorize_state_failed_even_when_every_document_failed() -> None:
    state, error = _wf_final_revectorize_state(failed=5, total=5)
    assert state == "failed"
    assert error == "5 of 5 document(s) failed to re-vectorize"
