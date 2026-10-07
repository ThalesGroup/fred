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

"""Unit tests for the plain-data helper functions in `features/scheduler/workflow.py`."""

from __future__ import annotations

import pytest
from temporalio.exceptions import ActivityError, ApplicationError, CancelledError, ChildWorkflowError, RetryState, TimeoutError, TimeoutType

from knowledge_flow_backend.features.scheduler.workflow import (
    _wf_file_terminal_event_args,
)

# ── #2315: telling a user cancel apart from a real failure in compensation ────


def _child_workflow_error(message: str, cause: Exception) -> ChildWorkflowError:
    """The real shape the compensation handler sees: a per-file child failure
    reaches the parent wrapped in a ChildWorkflowError, so the cancel-vs-failure
    verdict has to come from the wrapper's cause, not its type."""
    error = ChildWorkflowError(
        message,
        namespace="default",
        workflow_id="ProcessPushFile-0-abc",
        run_id="run-1",
        workflow_type="PushInputProcess",
        initiated_event_id=1,
        started_event_id=2,
        retry_state=None,
    )
    error.__cause__ = cause
    return error


def test_cancelled_child_workflow_reports_cancelled_not_failed() -> None:
    # A user stop must never read as an error: the state decides whether the
    # event handler fails the document's stages or erases the document.
    args = _wf_file_terminal_event_args(_child_workflow_error("Child Workflow execution cancelled", CancelledError("cancelled")), "task-1", "doc-1", "report.pdf")
    assert args[1] == "cancelled"
    assert args[4] == "Ingestion cancelled"
    # Not counted as a failure in the task's own tallies.
    assert args[7] == 0


def test_genuine_child_failure_reports_failed_with_its_message() -> None:
    args = _wf_file_terminal_event_args(_child_workflow_error("Child Workflow execution failed", ApplicationError("worker exploded")), "task-1", "doc-1", "report.pdf")
    assert args[1] == "failed"
    assert args[4] == "Ingestion failed. worker exploded"
    assert args[7] == 1


def test_plain_failure_reports_failed() -> None:
    args = _wf_file_terminal_event_args(RuntimeError("boom"), "task-1", "doc-1", "report.pdf")
    assert args[1] == "failed"
    assert args[4] == "Ingestion failed. boom"


def test_failure_without_a_message_still_carries_one() -> None:
    args = _wf_file_terminal_event_args(RuntimeError(), "task-1", "doc-1", "report.pdf")
    assert args[4] == "Ingestion failed. No failure details were reported."


@pytest.mark.parametrize("timeout_type", [TimeoutType.START_TO_CLOSE, TimeoutType.HEARTBEAT])
def test_failure_names_stage_timeout_and_exhausted_activity_attempts(timeout_type):
    activity_error = ActivityError(
        "Activity task failed", scheduled_event_id=1, started_event_id=2, identity="worker", activity_type="output_process", activity_id="activity-1", retry_state=RetryState.MAXIMUM_ATTEMPTS_REACHED
    )
    activity_error.__cause__ = TimeoutError("activity timed out", type=timeout_type, last_heartbeat_details=[])
    exc = _child_workflow_error("Child Workflow execution failed", activity_error)
    args = _wf_file_terminal_event_args(exc, "task-1", "doc-1", "report.pdf", "indexing")
    assert args[2] == "indexing"
    assert "indexing step" in args[4]
    assert "Configured attempts exhausted" in args[4]
    assert timeout_type.name in args[4]
    assert "Child Workflow" not in args[4]


def test_child_workflow_retry_limit_does_not_claim_activity_attempts_exhausted():
    exc = _child_workflow_error("Child Workflow execution failed", ApplicationError("Invalid PDF", non_retryable=True))
    args = _wf_file_terminal_event_args(exc, "task-1", "doc-1", "report.pdf", "processing")
    assert "content extraction" in args[4]
    assert "Invalid PDF" in args[4]
    assert "exhausted" not in args[4]
