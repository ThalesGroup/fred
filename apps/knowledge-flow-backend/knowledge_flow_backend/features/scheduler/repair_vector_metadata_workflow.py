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

"""Temporal workflow (sandboxed) for the vector-metadata repair action
("3a — Réparer uniquement", #2234).

Deliberately NOT built on `RevectorizeCorpusWorkflow`/`RevectorizeDocument`
(`features/scheduler/workflow.py`): that shape is one child workflow per
document, sized for a real re-vectorization pipeline. A metadata-only status
repair needs none of that -- one parent workflow, a handful of bulk
activities (each internally paginated/batched, never one Temporal call per
document), no children. History stays a few dozen events even at ~10,000
documents; `continue_as_new` is never needed.

Same plain-data sandbox convention as `workflow.py` (see its module
docstring): only stdlib + temporalio here, payloads read via `_wf_get`.

Fail-closed by construction: `list_strict_vector_document_uids` and
`list_strict_content_document_uids` raise on any scan failure (see their
docstrings) instead of returning an incomplete/empty list, and both scans
happen before the one write (`bulk_repair_vector_metadata`). Any exception
raised while scanning or writing is caught once, reported as a `failed`
terminal task event with the real error text, and re-raised -- so a scan
failure can never read as "0 vectors found" or a silent empty success.

Business outcome vs. reporting outcome are kept separate: the *scans and the
bulk write* are what can put a document in the wrong state, so only their
failure aborts the batch and reports `failed`. Publishing a task event
(initial "running" ping, or the terminal event) is best-effort on top of that
-- a bounded number of retries, then a logged warning, never a re-raise --
because a reporting hiccup after a successful bulk write must never read as
"the repair did not happen" when it did.

Neither scan proves *complete* recovery, only *some* recovery: "has a vector"
means at least one chunk was found, and "has content" means at least one
object was found under the document's prefix -- there is no reliable expected
count to compare against. See `RepairVectorMetadataResult`'s docstring.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from knowledge_flow_backend.features.scheduler.workflow import _wf_get


def _wf_repair_categorize(candidates: list[Any], vector_uids: list[str], content_uids: list[str]) -> dict:
    """
    Pure, deterministic intersection over the three scans -- no I/O, so it runs
    directly in workflow code rather than as its own activity.

    Precedence (mutually exclusive buckets):
      1. tabular (CSV/XLSX) -> `tabular_excluded`, regardless of its vector stage
         -- this repair is vector-only; `sql` reconciliation for tabular docs is
         a separate, out-of-scope gap (#2234 remediation notes).
      2. already `vector: done` -> `already_done`, left untouched.
      3. any processing stage reads `failed` or `in_progress` -> `failed_or_running_excluded`,
         left untouched. A stale `not_started` flag and a real failure/stuck stage are not
         the same problem: this repair must never silently mark such a document `done`
         (clearing its error) just because it happens to already have vectors/content --
         that would erase a real failure signal instead of surfacing it for investigation.
      4. has both real vectors and real content -> eligible for repair.
      5. no real vectors -> `missing_vectors`, left untouched.
      6. has vectors but no real content -> `missing_content`, left untouched.

    "has real vectors"/"has real content" means the document_uid appeared at
    least once in the corresponding strict scan -- not that every expected
    chunk/object was found (see `list_strict_vector_document_uids`'s docstring).
    """
    vector_set = set(vector_uids)
    content_set = set(content_uids)

    tabular_excluded = 0
    already_done = 0
    failed_or_running_excluded = 0
    eligible: list[str] = []
    missing_vectors = 0
    missing_content = 0

    for candidate in candidates:
        document_uid = _wf_get(candidate, "document_uid")
        if _wf_get(candidate, "is_tabular", False):
            tabular_excluded += 1
            continue
        if _wf_get(candidate, "vector_done", False):
            already_done += 1
            continue
        if _wf_get(candidate, "failed_or_running", False):
            failed_or_running_excluded += 1
            continue
        if document_uid not in vector_set:
            missing_vectors += 1
        elif document_uid not in content_set:
            missing_content += 1
        else:
            eligible.append(document_uid)

    return {
        "tabular_excluded": tabular_excluded,
        "already_done": already_done,
        "failed_or_running_excluded": failed_or_running_excluded,
        "eligible": eligible,
        "missing_vectors": missing_vectors,
        "missing_content": missing_content,
    }


@workflow.defn
class RepairVectorMetadataWorkflow:
    @workflow.run
    async def run(self, payload: Any) -> dict:
        """
        payload: {"source_tag": str, "task_id": str | None}

        Phase 1 (read-only): list metadata candidates for `source_tag` (1 SQL
        query), the real vector document_uids (1 strict, internally-paginated
        OpenSearch scan), the real content document_uids (1 strict content-store
        listing). Any failure here raises before phase 2 ever runs.

        Phase 2 (the only write): one bulk Postgres update for exactly the
        eligible document_uids.

        Always ends with one terminal task event carrying the structured
        `RepairVectorMetadataResult` report -- unless publishing that event
        itself fails after a successful repair, in which case the failure is
        logged, not raised (see module docstring: reporting failure must never
        masquerade as business failure).
        """
        source_tag = _wf_get(payload, "source_tag")
        task_id = _wf_get(payload, "task_id", None)

        # Best-effort progress ping: bounded retries, then give up quietly. A
        # failure here must never abort a repair that hasn't touched anything yet.
        if task_id:
            try:
                await workflow.execute_activity(
                    "emit_ingestion_task_event",
                    args=[task_id, "running", "scanning", None, None, 0, 1, 0, None, None],
                    schedule_to_close_timeout=timedelta(hours=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception:
                workflow.logger.warning("repair-vector-metadata: failed to publish the initial running event for task_id=%s", task_id)

        try:
            candidates = await workflow.execute_activity(
                "list_repair_candidates_for_source_tag",
                args=[source_tag],
                schedule_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            vector_uids = await workflow.execute_activity(
                "list_strict_vector_document_uids",
                args=[],
                schedule_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            content_uids = await workflow.execute_activity(
                "list_strict_content_document_uids",
                args=[],
                schedule_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            buckets = _wf_repair_categorize(candidates, vector_uids, content_uids)
            eligible = buckets["eligible"]

            repaired_uids = (
                await workflow.execute_activity(
                    "bulk_repair_vector_metadata",
                    args=[source_tag, eligible],
                    schedule_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                if eligible
                else []
            )

            report = {
                "source_tag": source_tag,
                "metadata_documents": len(candidates),
                "already_done": buckets["already_done"],
                "eligible_with_vectors_and_content": len(eligible),
                "repaired": len(repaired_uids),
                "missing_vectors": buckets["missing_vectors"],
                "missing_content": buckets["missing_content"],
                "tabular_excluded": buckets["tabular_excluded"],
                "failed_or_running_excluded": buckets["failed_or_running_excluded"],
                "errors": 0,
            }
        except Exception as exc:
            # A failure at or before the bulk write -- the real business failure
            # this workflow reports for. Reporting it is itself best-effort: if
            # publishing the failed event also fails, log and still raise the
            # ORIGINAL exception, never mask it with the reporting error.
            if task_id:
                error_str = str(exc).strip() or "Vector-metadata repair failed"
                try:
                    await workflow.execute_activity(
                        "emit_repair_vector_metadata_task_event",
                        args=[task_id, "failed", error_str, None],
                        schedule_to_close_timeout=timedelta(hours=1),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception:
                    workflow.logger.warning("repair-vector-metadata: failed to publish the failed task event for task_id=%s (original error: %s)", task_id, error_str)
            raise

        # The bulk write (if any) already committed by this point -- everything
        # below is reporting only, and must never turn a successful repair into
        # an apparent failure.
        if task_id:
            try:
                await workflow.execute_activity(
                    "emit_repair_vector_metadata_task_event",
                    args=[task_id, "succeeded", None, report],
                    schedule_to_close_timeout=timedelta(hours=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception:
                workflow.logger.warning(
                    "repair-vector-metadata: repair succeeded (repaired=%d) but failed to publish the terminal task event for task_id=%s",
                    report["repaired"],
                    task_id,
                )
        return report
