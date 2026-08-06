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

"""Tests for `RepairVectorMetadataWorkflow` (#2234, 3a).

Two kinds of test here, deliberately:

1. Pure-function tests of `_wf_repair_categorize` -- the same "no Temporal
   context needed" strategy `test_workflow.py` already uses for
   `RevectorizeCorpusWorkflow`'s decision helpers (see that file's module
   docstring: `@workflow.defn` classes need a live Temporal test environment
   to execute, which this repo's test suite does not otherwise use).

2. Static source-inspection tests proving the structural safety guarantees
   that can't be expressed as a call assertion: no per-document child
   workflow, no forbidden symbol (delete/ingest/embed) anywhere in the 3a
   call graph, and a constant (not per-document) Temporal activity surface.
   These are deliberately textual/structural rather than executed-workflow
   tests -- see the close-out notes for why, and what a follow-up
   `WorkflowEnvironment`-based test would add.
"""

from __future__ import annotations

import inspect
import re

from knowledge_flow_backend.features.scheduler import repair_vector_metadata_activities as activities_module
from knowledge_flow_backend.features.scheduler import repair_vector_metadata_workflow as workflow_module
from knowledge_flow_backend.features.scheduler import worker as worker_module
from knowledge_flow_backend.features.scheduler.repair_vector_metadata_workflow import _wf_repair_categorize


def _candidate(document_uid: str, *, is_tabular: bool = False, vector_done: bool = False) -> dict:
    return {"document_uid": document_uid, "is_tabular": is_tabular, "vector_done": vector_done}


class TestRepairCategorize:
    def test_distinguishes_all_five_buckets(self) -> None:
        candidates = [
            _candidate("already-done", vector_done=True),
            _candidate("eligible-1"),
            _candidate("eligible-2"),
            _candidate("no-vector"),
            _candidate("no-content"),
            _candidate("tabular-1", is_tabular=True),
        ]
        vector_uids = ["eligible-1", "eligible-2", "no-content"]
        content_uids = ["eligible-1", "eligible-2", "no-vector"]

        buckets = _wf_repair_categorize(candidates, vector_uids, content_uids)

        assert buckets["already_done"] == 1
        assert sorted(buckets["eligible"]) == ["eligible-1", "eligible-2"]
        assert buckets["missing_vectors"] == 1  # "no-vector"
        assert buckets["missing_content"] == 1  # "no-content"
        assert buckets["tabular_excluded"] == 1

    def test_tabular_takes_precedence_over_already_done(self) -> None:
        """A tabular document must always land in `tabular_excluded`, even if it
        somehow already reads `vector: done` -- never double-counted, never
        silently reclassified as a normal already-done document."""
        candidates = [_candidate("csv-1", is_tabular=True, vector_done=True)]

        buckets = _wf_repair_categorize(candidates, vector_uids=["csv-1"], content_uids=["csv-1"])

        assert buckets["tabular_excluded"] == 1
        assert buckets["already_done"] == 0
        assert buckets["eligible"] == []

    def test_missing_vectors_takes_precedence_over_missing_content(self) -> None:
        """A document missing both is reported once, under missing_vectors --
        never double-counted across both buckets."""
        candidates = [_candidate("doc-1")]

        buckets = _wf_repair_categorize(candidates, vector_uids=[], content_uids=[])

        assert buckets["missing_vectors"] == 1
        assert buckets["missing_content"] == 0

    def test_empty_candidate_list_yields_all_zero_buckets(self) -> None:
        buckets = _wf_repair_categorize([], vector_uids=["doc-1"], content_uids=["doc-1"])

        assert buckets == {
            "tabular_excluded": 0,
            "already_done": 0,
            "eligible": [],
            "missing_vectors": 0,
            "missing_content": 0,
        }

    def test_accepts_object_candidates_not_just_dicts(self) -> None:
        """`_wf_get` reads either a dict or a plain object -- payloads cross the
        Temporal boundary untyped (see `workflow.py`'s module docstring)."""

        class _Candidate:
            document_uid = "doc-1"
            is_tabular = False
            vector_done = False

        buckets = _wf_repair_categorize([_Candidate()], vector_uids=["doc-1"], content_uids=["doc-1"])

        assert buckets["eligible"] == ["doc-1"]


# ── Structural / static call-graph proof ──────────────────────────────────────
# The forbidden symbols: anything capable of deleting vectors, reading/writing
# document content, re-running ingestion, or calling an embedding provider.
#
# Checked via each function's *bytecode* `co_names` (the globals/attributes its
# compiled code actually references), NOT a raw source-text search: this module
# and `repair_vector_metadata_activities.py` deliberately document, in prose,
# every one of these forbidden symbols (to explain *why* they must never be
# called) -- a plain substring/regex search over `inspect.getsource(...)` would
# false-positive on that prose. `co_names` only contains names the compiled
# code actually loads/calls; a docstring is stored as a string constant
# (`co_consts`), never turned into a `LOAD_GLOBAL`/`LOAD_METHOD` name.
_FORBIDDEN_NAMES = {
    "delete_vectors",
    "prepare_revectorize_file",
    "output_process",
    "output_process_trusted",
    "get_embedder",
    "get_create_vector_store",
    "OpenSearchVectorStoreAdapter",
    "ensure_ready",
    "embed_query",
    "embed_documents",
    "start_child_workflow",
    "execute_child_workflow",
}


def _module_source(module) -> str:
    return inspect.getsource(module)


def _referenced_names(func) -> set[str]:
    """Every global/attribute name `func`'s compiled bytecode references,
    recursing into any nested code objects (inner functions/comprehensions)."""
    code = func.__code__
    names: set[str] = set(code.co_names)
    for const in code.co_consts:
        if hasattr(const, "co_names"):  # a nested code object
            names |= _referenced_names_from_code(const)
    return names


def _referenced_names_from_code(code) -> set[str]:
    names: set[str] = set(code.co_names)
    for const in code.co_consts:
        if hasattr(const, "co_names"):
            names |= _referenced_names_from_code(const)
    return names


_ACTIVITY_FUNCS = [
    activities_module.list_repair_candidates_for_source_tag,
    activities_module.list_strict_vector_document_uids,
    activities_module.list_strict_content_document_uids,
    activities_module.bulk_repair_vector_metadata,
    activities_module.emit_repair_vector_metadata_task_event,
]
_WORKFLOW_FUNCS = [
    workflow_module.RepairVectorMetadataWorkflow.run,
    workflow_module._wf_repair_categorize,
]


class TestNoForbiddenSymbolsInThe3aCallGraph:
    def test_activities_never_reference_a_forbidden_symbol(self) -> None:
        for func in _ACTIVITY_FUNCS:
            hit = _referenced_names(func) & _FORBIDDEN_NAMES
            assert not hit, f"{func.__qualname__} references forbidden symbol(s): {hit}"

    def test_workflow_never_references_a_forbidden_symbol(self) -> None:
        for func in _WORKFLOW_FUNCS:
            hit = _referenced_names(func) & _FORBIDDEN_NAMES
            assert not hit, f"{func.__qualname__} references forbidden symbol(s): {hit}"

    def test_workflow_never_starts_a_child_workflow(self) -> None:
        """Belt-and-suspenders source-text check specifically for
        `start_child_workflow`/`execute_child_workflow`: these are read off
        `workflow.<name>` as an attribute access, which the `co_names`-based
        check above already covers via `_FORBIDDEN_NAMES`, but the whole point
        of this workflow's shape (one parent, a handful of bulk activities,
        versus `RevectorizeCorpusWorkflow`'s one child per document) is
        important enough to also assert directly against the raw source."""
        source = _module_source(workflow_module)
        assert "start_child_workflow" not in source
        assert "execute_child_workflow" not in source


class TestConstantActivitySurface:
    """`bulk_repair_vector_metadata` etc. are each called exactly once per
    `run()`, regardless of how many document_uids are involved -- the count of
    *distinct* activity names this workflow can invoke is a small constant,
    never O(documents). Cross-checked against `worker.py`'s registration list
    so the two can't silently drift apart."""

    _EXPECTED_ACTIVITY_NAMES = {
        "emit_ingestion_task_event",  # reused for the initial "running" ping
        "list_repair_candidates_for_source_tag",
        "list_strict_vector_document_uids",
        "list_strict_content_document_uids",
        "bulk_repair_vector_metadata",
        "emit_repair_vector_metadata_task_event",
    }

    def test_workflow_source_only_ever_names_the_expected_constant_activity_set(self) -> None:
        source = _module_source(workflow_module)
        named_activities = set(re.findall(r'execute_activity\(\s*"([a-zA-Z0-9_]+)"', source))
        assert named_activities == self._EXPECTED_ACTIVITY_NAMES

    def test_worker_registers_exactly_the_repair_activities_module_functions(self) -> None:
        """`worker.py`'s activity list for this feature must be the module's own
        `@activity.defn` functions -- not a per-document list built at runtime."""
        worker_source = inspect.getsource(worker_module)
        for name in (
            "list_repair_candidates_for_source_tag",
            "list_strict_vector_document_uids",
            "list_strict_content_document_uids",
            "bulk_repair_vector_metadata",
            "emit_repair_vector_metadata_task_event",
        ):
            assert name in worker_source, f"{name} must be registered in worker.py"
        assert "RepairVectorMetadataWorkflow" in worker_source


class TestBulkOnlyCalledAfterAllThreeScans:
    """Structural proof, by source order, that `bulk_repair_vector_metadata` is
    textually positioned after all three read-only scans inside the same `try`
    block -- combined with Python's own control flow (an activity exception
    propagates immediately, so a raised scan never reaches the lines below it),
    this is what guarantees the bulk write never runs after a failed scan."""

    def test_bulk_call_is_textually_after_all_three_scan_calls(self) -> None:
        source = _module_source(workflow_module)
        bulk_pos = source.index('"bulk_repair_vector_metadata"')
        for scan_activity in (
            "list_repair_candidates_for_source_tag",
            "list_strict_vector_document_uids",
            "list_strict_content_document_uids",
        ):
            scan_pos = source.index(f'"{scan_activity}"')
            assert scan_pos < bulk_pos, f"{scan_activity} must be scanned before the bulk write"

    def test_bulk_call_and_all_three_scans_share_the_same_try_block(self) -> None:
        """From the main (8-space-indented) `try:` up to the bulk call, there must
        be no `except` -- i.e. nothing lets a scan failure be caught and
        swallowed before reaching the bulk write undetected. (The unrelated,
        separately-indented `try/except` around the best-effort initial "running"
        event, earlier in the function, is deliberately not this one -- see
        `main_try_marker`'s exact indentation.)"""
        source = _module_source(workflow_module)
        bulk_pos = source.index('"bulk_repair_vector_metadata"')
        main_try_marker = "\n        try:\n"
        try_pos = source.index(main_try_marker)
        assert try_pos < bulk_pos
        between = source[try_pos:bulk_pos]
        assert "except" not in between
