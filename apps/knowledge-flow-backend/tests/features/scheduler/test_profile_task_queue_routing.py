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

"""Extraction runs on worker pods dedicated to the document's profile; everything
around it stays on the common queue. These cover the two halves of that contract:
what the submission side writes onto each document, and what the workflow does
with it."""

import logging
from contextlib import AbstractContextManager, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fred_core import KeycloakUser
from temporalio.exceptions import ApplicationError

from knowledge_flow_backend.common.structures import (
    IngestionProcessingProfile,
    IngestionWorkerRole,
    extraction_task_queue,
)
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler import workflow as workflow_module
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcessWithoutUser
from knowledge_flow_backend.features.scheduler.workflow import (
    PullInputProcess,
    PushInputProcess,
    _wf_extraction_task_queue,
)

USER = KeycloakUser(uid="test-user", username="testuser", email="testuser@localhost", roles=["admin"])


def _service(app_context, captured: dict) -> IngestionTaskService:
    """The submission service with a stub scheduler that records the definition it
    was handed, so the per-document routing is observable."""
    service = IngestionTaskService(
        scheduler_config=app_context.configuration.scheduler.model_copy(update={"backend": "memory"}),
        processing_config=app_context.configuration.processing,
        metadata_service=MetadataService(),
        max_parallelism=2,
    )

    class _StubScheduler:
        async def start_document_processing(self, *, user, definition, background_tasks=None):
            captured["definition"] = definition
            return SimpleNamespace(workflow_id="wf-123", run_id="run-123")

    service._scheduler = _StubScheduler()
    return service


def _file(profile: IngestionProcessingProfile, document_uid: str) -> FileToProcessWithoutUser:
    return FileToProcessWithoutUser(source_tag="fred", display_name=f"{document_uid}.md", document_uid=document_uid, profile=profile)


def _pull_file(profile: IngestionProcessingProfile, name: str) -> FileToProcessWithoutUser:
    return FileToProcessWithoutUser(source_tag="fred", display_name=f"{name}.pdf", external_path=f"/inbox/{name}.pdf", profile=profile)


def _queues(captured: dict) -> dict[str, str | None]:
    return {file.document_uid: file.extraction_task_queue for file in captured["definition"].files}


async def _submitted_payload(app_context, file: FileToProcessWithoutUser) -> dict:
    """The exact payload the workflow receives: built by the real submission path,
    then serialized the way the Temporal data converter serializes it."""
    captured: dict[str, object] = {}
    service = _service(app_context, captured)
    await service.submit_documents(user=USER, pipeline_name="routing", files=[file])
    return captured["definition"].files[0].model_dump()


def _capture_activities() -> tuple[list[tuple[str, dict]], AbstractContextManager]:
    """Intercept `workflow.execute_activity` so the sub-workflow can be run without
    a Temporal server, recording the activity name and every option it was given.

    The workflow logger goes with it: the SDK's own adapter asks the workflow event
    loop whether it is replaying, which there is none of here."""
    calls: list[tuple[str, dict]] = []

    async def _execute_activity(name, **kwargs):
        calls.append((name, kwargs))
        return {"document_uid": "doc-1"}

    @contextmanager
    def _intercept():
        with (
            patch.object(workflow_module.workflow, "execute_activity", _execute_activity),
            patch.object(workflow_module.workflow, "logger", logging.getLogger("test-workflow")),
        ):
            yield

    return calls, _intercept()


# ── profile → queue, one name derived on both sides ───────────────────────────


def test_every_profile_has_its_own_extraction_queue() -> None:
    """The worker derives its own queue through this same function, which is what
    makes a disagreement between the two sides impossible."""
    assert extraction_task_queue("ingestion", IngestionProcessingProfile.fast) == "ingestion-fast"
    assert extraction_task_queue("ingestion", IngestionProcessingProfile.medium) == "ingestion-medium"
    assert extraction_task_queue("ingestion", IngestionProcessingProfile.rich) == "ingestion-rich"


def test_each_extraction_role_carries_the_profile_it_serves() -> None:
    assert IngestionWorkerRole.common.extraction_profile is None
    assert IngestionWorkerRole.extraction_fast.extraction_profile is IngestionProcessingProfile.fast
    assert IngestionWorkerRole.extraction_medium.extraction_profile is IngestionProcessingProfile.medium
    assert IngestionWorkerRole.extraction_rich.extraction_profile is IngestionProcessingProfile.rich


# ── submission side: one queue per document ───────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_queue"),
    [
        (IngestionProcessingProfile.fast, "ingestion-fast"),
        (IngestionProcessingProfile.medium, "ingestion-medium"),
        (IngestionProcessingProfile.rich, "ingestion-rich"),
    ],
)
async def test_each_profile_is_routed_to_its_extraction_queue(app_context, profile, expected_queue) -> None:
    captured: dict[str, object] = {}
    service = _service(app_context, captured)

    await service.submit_documents(user=USER, pipeline_name="one-profile", files=[_file(profile, "doc-1")])

    assert _queues(captured) == {"doc-1": expected_queue}


@pytest.mark.asyncio
async def test_a_submission_may_mix_profiles(app_context) -> None:
    """Routing is per document, not per workflow, so nothing has to be refused:
    each file carries the queue its own extraction belongs on."""
    captured: dict[str, object] = {}
    service = _service(app_context, captured)

    files = [
        _file(IngestionProcessingProfile.fast, "doc-fast"),
        _file(IngestionProcessingProfile.medium, "doc-medium"),
        _file(IngestionProcessingProfile.rich, "doc-rich"),
    ]
    await service.submit_documents(user=USER, pipeline_name="mixed", files=files)

    assert _queues(captured) == {
        "doc-fast": "ingestion-fast",
        "doc-medium": "ingestion-medium",
        "doc-rich": "ingestion-rich",
    }


@pytest.mark.asyncio
async def test_mixing_push_and_pull_is_still_refused(app_context) -> None:
    """The business validations that have nothing to do with routing stay in place."""
    captured: dict[str, object] = {}
    service = _service(app_context, captured)

    files = [
        _file(IngestionProcessingProfile.fast, "doc-push"),
        FileToProcessWithoutUser(source_tag="fred", display_name="pulled.md", external_path="/somewhere/pulled.md"),
    ]
    with pytest.raises(ValueError, match="Mixed push and pull"):
        await service.submit_documents(user=USER, pipeline_name="mixed-kinds", files=files)

    assert "definition" not in captured


# ── workflow side: the activity call the sub-workflow actually makes ──────────

_PROFILE_QUEUES = [
    (IngestionProcessingProfile.fast, "ingestion-fast"),
    (IngestionProcessingProfile.medium, "ingestion-medium"),
    (IngestionProcessingProfile.rich, "ingestion-rich"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("profile", "expected_queue"), _PROFILE_QUEUES)
async def test_push_extraction_activity_is_scheduled_on_the_profile_queue(app_context, profile, expected_queue) -> None:
    """End of the routing contract: the queue the submission wrote onto the document
    is the queue this activity is actually scheduled on."""
    payload = await _submitted_payload(app_context, _file(profile, "doc-1"))
    calls, intercept = _capture_activities()

    with intercept:
        await PushInputProcess().run(payload, payload["processed_by"], "", {"document_uid": "doc-1"}, profile.value, 60, 30)

    assert [(name, options["task_queue"]) for name, options in calls] == [("push_input_process", expected_queue)]


@pytest.mark.asyncio
@pytest.mark.parametrize(("profile", "expected_queue"), _PROFILE_QUEUES)
async def test_pull_extraction_activity_is_scheduled_on_the_profile_queue(app_context, profile, expected_queue) -> None:
    payload = await _submitted_payload(app_context, _pull_file(profile, "doc-1"))
    calls, intercept = _capture_activities()

    with intercept:
        await PullInputProcess().run(payload, payload["processed_by"], {"document_uid": "doc-1"}, profile.value, 60, 30)

    assert [(name, options["task_queue"]) for name, options in calls] == [("pull_input_process", expected_queue)]


@pytest.mark.asyncio
async def test_extraction_is_the_only_activity_a_sub_workflow_routes(app_context) -> None:
    """Routing one activity is the whole design: anything else the pipeline runs must
    keep inheriting the workflow's own queue, which means passing no task_queue."""
    payload = await _submitted_payload(app_context, _file(IngestionProcessingProfile.rich, "doc-1"))
    calls, intercept = _capture_activities()

    with intercept:
        await PushInputProcess().run(payload, payload["processed_by"], "", {"document_uid": "doc-1"}, "rich", 60, 30)

    name, options = calls[0]
    assert name == "push_input_process"
    # The profile's own timeouts still apply — routing did not displace them.
    assert options["start_to_close_timeout"].total_seconds() == 60
    assert options["heartbeat_timeout"].total_seconds() == 30


# ── workflow side: the payload is the only source, and it is mandatory ─────────


def test_the_workflow_reads_the_queue_off_the_document_payload() -> None:
    """Deliberately not from configuration: a workflow reading its deployment's
    environment would not be deterministic."""
    assert _wf_extraction_task_queue({"extraction_task_queue": "ingestion-rich"}) == "ingestion-rich"


@pytest.mark.parametrize("payload", [{}, {"extraction_task_queue": None}, {"extraction_task_queue": "   "}])
def test_an_unrouted_document_fails_instead_of_falling_back(payload) -> None:
    """The common queue does not register extraction, so falling back to it would
    park the activity there indefinitely with nothing in the logs: an activity
    nobody polls is never started, and start_to_close_timeout only runs from the
    moment a worker starts it.

    An ApplicationError specifically: any other exception would fail the workflow
    task instead of the workflow, and Temporal would retry it forever with the
    document still showing as running."""
    with pytest.raises(ApplicationError, match="did not route this document") as raised:
        _wf_extraction_task_queue({**payload, "display_name": "report.pdf"})
    assert raised.value.non_retryable is True
