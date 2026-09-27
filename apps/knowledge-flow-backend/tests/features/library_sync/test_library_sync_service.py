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

"""Writing a library from a source, addressed by the caller's own names.

Every test here is one the first Knowledge Base got wrong by running: a file
edited daily left a year of copies, retraction went through the folder's own
properties, and the writer was filed as a person.
"""

from __future__ import annotations

import io
import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, UploadFile
from fred_core import AuthorizationError, KeycloakUser, RebacReference, RelationType, Resource, TagPermission
from fred_core.documents.document_structures import ProcessingStage, ProcessingStatus
from fred_core.scheduler import SchedulerBackend
from fred_core.security.structure import SERVICE_AGENT_ROLE
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import IngestionTaskEvent, TaskState, TaskTarget
from fred_core.tasks.service import TaskService
from fred_core.tasks.workflow_control import ExecutionStatus
from sqlalchemy.ext.asyncio import create_async_engine

import knowledge_flow_backend.features.library_sync.service as service_module
import knowledge_flow_backend.features.metadata.service as metadata_service_module
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
from knowledge_flow_backend.features.library_sync.structures import InvalidSourceRequest, SynchronizationUnavailable
from knowledge_flow_backend.features.scheduler.base_scheduler import WorkflowHandle
from knowledge_flow_backend.features.scheduler.document_failure import mark_in_progress_stages_failed, on_reconciled_terminal
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.tag.structure import Tag, TagType
from knowledge_flow_backend.models.base import Base as KFBase
from knowledge_flow_backend.models.task_models import TASK_TABLES

TEAM = "team-1"


class InMemoryTagStore:
    """Enough of the tag store for folders under a library to be found and made."""

    def __init__(self) -> None:
        self.tags: dict[str, Tag] = {}

    def add(self, tag: Tag) -> Tag:
        self.tags[tag.id] = tag
        return tag

    async def list_all_tags(self, session=None) -> list[Tag]:
        return list(self.tags.values())

    async def get_tag_by_id(self, tag_id: str, session=None) -> Tag:
        if tag_id not in self.tags:
            raise TagNotFoundError(tag_id)
        return self.tags[tag_id]

    async def get_by_owner_type_full_path(self, owner_id, tag_type, full_path, session=None):
        for tag in self.tags.values():
            if tag.owner_id == owner_id and tag.type == tag_type and tag.full_path == full_path:
                return tag
        return None

    async def create_tag(self, tag: Tag, session=None) -> Tag:
        return self.add(tag)

    async def update_tag_by_id(self, tag_id: str, tag: Tag, session=None) -> Tag:
        self.tags[tag_id] = tag
        return tag

    async def delete_tag_by_id(self, tag_id: str, session=None) -> None:
        self.tags.pop(tag_id, None)


class GrantedLibraryRebac:
    """Grants a permission over some libraries, inherited by everything under them.

    That inheritance is the property under test as much as the grant itself: a
    folder created inside a library must be writable without a second grant, and
    a folder in another library must not be.
    """

    def __init__(self, store: InMemoryTagStore, *, writable: set[str] = frozenset(), readable: set[str] = frozenset()) -> None:
        self._store = store
        self._writable = set(writable)
        self._readable = set(readable) | set(writable)
        self.relations: list[object] = []
        self.deleted_relations: list[object] = []
        self.team_checked = False

    def _reaches(self, granted: set[str], resource_id: str) -> bool:
        if resource_id in granted:
            return True
        tag = self._store.tags.get(resource_id)
        if tag is None:
            return False
        for root_id in granted:
            root = self._store.tags.get(root_id)
            if root is not None and tag.full_path.startswith(f"{root.full_path}/"):
                return True
        return False

    def _allows(self, permission, resource_id: str) -> bool:
        granted = self._writable if permission == TagPermission.UPDATE else self._readable
        return self._reaches(granted, resource_id)

    async def has_user_permission(self, user, permission, resource_id, consistency_token=None) -> bool:
        return self._allows(permission, resource_id)

    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        if not self._allows(permission, resource_id):
            raise AuthorizationError(user.uid, str(permission), Resource.TAGS)

    async def check_user_team_permission_or_raise(self, *, user, permission, team_id) -> None:
        self.team_checked = True
        raise AuthorizationError(user.uid, str(permission), Resource.TEAM)

    async def add_relation(self, relation, actor_uid=None) -> None:
        self.relations.append(relation)

    async def add_user_relation(self, user, relation, *, resource_type, resource_id) -> None:
        self.relations.append((resource_type, resource_id, relation))

    async def delete_relation(self, relation) -> None:
        self.deleted_relations.append(relation)

    async def lookup_subjects(self, resource, relation, subject_type):
        # A library and the folders under it are the team's: what ReBAC answers
        # when asked who owns them, and what a task for them is filed under.
        tag = self._store.tags.get(resource.id)
        if tag is not None and relation == RelationType.OWNER and subject_type == Resource.TEAM:
            return [RebacReference(type=Resource.TEAM, id=tag.owner_id)]
        return []

    async def lookup_user_resources(self, user, permission):
        return []


class RecordingKpiWriter:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def count(self, name, value=1, *, dims=None, actor=None, **_) -> None:
        self.events.append((name, actor))

    def emit(self, **kwargs) -> None:
        self.events.append((kwargs.get("name"), kwargs.get("actor")))

    def actors_for(self, name: str) -> list[object]:
        return [actor for emitted, actor in self.events if emitted == name]


def library(store: InMemoryTagStore, name: str = "Mirror", owner_id: str = TEAM) -> Tag:
    now = datetime.now(timezone.utc)
    return store.add(
        Tag(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            owner_id=owner_id,
            name=name,
            path=None,
            description=f"{name} library",
            type=TagType.DOCUMENT,
        )
    )


def pod(uid: str = "kb-pod") -> KeycloakUser:
    """A Knowledge Base's own workload identity: a service, holding no team role."""
    return KeycloakUser(uid=uid, username=uid, roles=[SERVICE_AGENT_ROLE], email=None)


def upload(name: str = "readme.md", content: bytes = b"# hello\n") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name)


class Scheduler:
    """Stands in for the pipeline's front door, which the upload surface shares.

    Conversion and vectorization are the pipeline's and tested there. What is
    asserted here is what this surface owes it: one push file per write, whose
    row already exists — the worker's first step reads it, and would find
    nothing to process otherwise.
    """

    def __init__(self) -> None:
        self.fails = False
        self.complete = True
        self.built: dict[str, object] = {}
        self.submissions: list[SimpleNamespace] = []
        self.saw_rows: list[bool] = []

    def build(self, **kwargs) -> Scheduler:
        self.built = kwargs
        service = IngestionTaskService(**kwargs)
        service._scheduler = self
        return service

    async def start_document_processing(self, *, user, definition, background_tasks=None):
        files = definition.files
        pipeline_name = definition.name
        store = _metadata_store()
        for file in files:
            self.saw_rows.append(await store.get_metadata_by_uid(file.document_uid) is not None)
        if self.fails:
            raise RuntimeError("temporal unreachable at 10.0.0.1:7233")
        self.submissions.append(SimpleNamespace(user=user, pipeline_name=pipeline_name, files=list(files), background_tasks=background_tasks))
        if self.complete and background_tasks is None:
            tasks = ApplicationContext.get_instance().get_task_service()
            for file in files:
                await tasks.record(IngestionTaskEvent(task_id=file.task_id, state=TaskState.succeeded, seq=0, timestamp=datetime.now(timezone.utc)))
        return WorkflowHandle(workflow_id=definition.workflow_id)


@pytest.fixture
def scheduler(app_context, monkeypatch) -> Scheduler:
    """Scheduling on, with this stand-in built where the pipeline client would be."""
    stage = Scheduler()
    monkeypatch.setattr(app_context.get_instance().get_config().scheduler, "enabled", True)
    monkeypatch.setattr(service_module, "IngestionTaskService", stage.build)
    return stage


@pytest.fixture
def storage_accounting(app_context, monkeypatch) -> None:
    """Let the quota counters move somewhere inert.

    Removing a document deletes its row and releases its storage in one real
    transaction, so the transaction boundary has to be real — an empty SQLite
    engine provides it. Which counter moves by how much is the storage-release
    tests' subject, not this file's.
    """
    app_context.get_instance()._pg_async_engine = create_async_engine("sqlite+aiosqlite://")

    class _InertTeamStore:
        def __init__(self, engine):
            pass

        async def get_by_team_id(self, team_id):
            return None

        async def increment_current_storage_size(self, team_id, delta, session=None):
            return None

    class _InertUserStore:
        async def increment_current_storage_size(self, user_id, delta, session=None):
            return None

    monkeypatch.setattr(metadata_service_module, "TeamMetadataStore", _InertTeamStore)
    monkeypatch.setattr(metadata_service_module, "get_user_store", lambda: _InertUserStore())


@pytest_asyncio.fixture
async def task_service(app_context, storage_accounting) -> TaskService:
    """A real task ledger over the same inert engine, so a write's task can be read back."""
    ctx = app_context.get_instance()
    engine = ctx.get_pg_async_engine()
    async with engine.begin() as connection:
        await connection.run_sync(KFBase.metadata.create_all)
    service = TaskService.build(engine=engine, tables=TASK_TABLES, backend=SchedulerBackend.MEMORY)
    ctx._task_service_instance = service
    return service


@pytest.fixture
def tag_store(app_context, scheduler, storage_accounting, task_service) -> InMemoryTagStore:
    ctx = app_context.get_instance()
    store = InMemoryTagStore()
    ctx._tag_store_instance = store
    # TagService builds a ResourceService whose store the test configuration
    # cannot construct. Never touched: this surface only writes documents.
    ctx._resource_store_instance = object()
    return store


@pytest.fixture
def kpi_writer(app_context) -> RecordingKpiWriter:
    ctx = app_context.get_instance()
    writer = RecordingKpiWriter()
    ctx._kpi_writer = writer
    return writer


def _service(rebac: GrantedLibraryRebac) -> service_module.LibrarySyncService:
    ApplicationContext.get_instance()._rebac_engine = rebac
    return service_module.LibrarySyncService()


def _metadata_store():
    return ApplicationContext.get_instance().get_metadata_store()


# --------------------------------------------------------------------------
# One document per key
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewriting_a_key_updates_one_document_and_keeps_its_identifier(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    first = await service.write_document(
        caller,
        library_id=lib.id,
        path="readme.md",
        source_key="readme.md",
        document_version="etag-1",
        source_tag="fred",
        upload=upload(content=b"# first\n"),
    )
    assert first.created is True
    original = await _metadata_store().get_metadata_by_source_key(lib.id, "readme.md")
    assert original is not None

    second = await service.write_document(
        caller,
        library_id=lib.id,
        path="readme.md",
        source_key="readme.md",
        document_version="etag-2",
        source_tag="fred",
        upload=upload(content=b"# second\n"),
    )

    assert second.created is False
    assert second.document_version == "etag-2"
    documents = await _metadata_store().get_metadata_in_tag(lib.id)
    assert len(documents) == 1
    assert documents[0].identity.document_uid == original.identity.document_uid
    assert documents[0].source.document_version == "etag-2"


@pytest.mark.asyncio
async def test_a_third_write_still_updates_the_same_document(tag_store):
    """The upload surface refuses a third same-named file; a mirror must not."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    for revision in range(3):
        await service.write_document(
            caller,
            library_id=lib.id,
            path="readme.md",
            source_key="readme.md",
            document_version=f"etag-{revision}",
            source_tag="fred",
            upload=upload(content=f"# revision {revision}\n".encode()),
        )

    assert len(await _metadata_store().get_metadata_in_tag(lib.id)) == 1


@pytest.mark.asyncio
async def test_a_caller_maintains_its_documents_with_its_own_key_alone(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    key = "specs/../odd ?name.md"

    await service.write_document(caller, library_id=lib.id, path="notes.md", source_key=key, document_version=None, source_tag="fred", upload=upload())
    await service.write_document(caller, library_id=lib.id, path="notes.md", source_key=key, document_version=None, source_tag="fred", upload=upload())
    removed = await service.remove_document(caller, library_id=lib.id, source_key=key)

    assert removed.removed is True
    assert await _metadata_store().get_metadata_by_source_key(lib.id, key) is None


@pytest.mark.asyncio
async def test_a_document_uploaded_by_a_person_is_never_adopted_by_a_key(tag_store):
    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging

    lib = library(tag_store)
    await _metadata_store().save_metadata(
        DocumentMetadata(
            identity=Identity(document_name="readme.md", document_uid="uploaded-by-hand"),
            source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred", pull_location=None),
            tags=Tagging(tag_ids=[lib.id]),
        )
    )
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    await service.write_document(pod(), library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    documents = {d.identity.document_uid for d in await _metadata_store().get_metadata_in_tag(lib.id)}
    assert "uploaded-by-hand" in documents
    assert len(documents) == 2


@pytest.mark.asyncio
async def test_two_libraries_use_the_same_key_independently(tag_store):
    first = library(tag_store, name="First")
    second = library(tag_store, name="Second")
    service = _service(GrantedLibraryRebac(tag_store, writable={first.id, second.id}))
    caller = pod()

    await service.write_document(caller, library_id=first.id, path="readme.md", source_key="readme.md", document_version="a", source_tag="fred", upload=upload())
    await service.write_document(caller, library_id=second.id, path="readme.md", source_key="readme.md", document_version="b", source_tag="fred", upload=upload())
    await service.write_document(caller, library_id=first.id, path="readme.md", source_key="readme.md", document_version="a2", source_tag="fred", upload=upload())

    in_first = await _metadata_store().get_metadata_by_source_key(first.id, "readme.md")
    in_second = await _metadata_store().get_metadata_by_source_key(second.id, "readme.md")
    assert in_first is not None and in_first.source.document_version == "a2"
    assert in_second is not None and in_second.source.document_version == "b"


# --------------------------------------------------------------------------
# Where the document goes
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_grant_reaches_the_whole_subtree(tag_store):
    lib = library(tag_store)
    rebac = GrantedLibraryRebac(tag_store, writable={lib.id})
    service = _service(rebac)

    await service.write_document(
        pod(),
        library_id=lib.id,
        path="specs/api/openapi.md",
        source_key="specs/api/openapi.md",
        document_version=None,
        source_tag="fred",
        upload=upload(),
    )

    created = {tag.full_path for tag in tag_store.tags.values()}
    assert created == {"Mirror", "Mirror/specs", "Mirror/specs/api"}
    # The team right was never needed, so it was never asked for.
    assert rebac.team_checked is False
    document = await _metadata_store().get_metadata_by_source_key(lib.id, "specs/api/openapi.md")
    assert document is not None
    leaf = next(tag for tag in tag_store.tags.values() if tag.full_path == "Mirror/specs/api")
    assert document.tags.tag_ids == [leaf.id]


@pytest.mark.asyncio
async def test_a_folder_a_previous_write_made_is_reused(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    for name in ("one.md", "two.md"):
        await service.write_document(
            caller,
            library_id=lib.id,
            path=f"specs/{name}",
            source_key=f"specs/{name}",
            document_version=None,
            source_tag="fred",
            upload=upload(name=name),
        )

    assert sorted(tag.full_path for tag in tag_store.tags.values()) == ["Mirror", "Mirror/specs"]


@pytest.mark.asyncio
async def test_a_folder_carries_the_library_s_owner_not_the_caller_s(tag_store):
    """A folder owned by the pod would sit outside the library's own namespace."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    await service.write_document(pod(), library_id=lib.id, path="specs/api.md", source_key="specs/api.md", document_version=None, source_tag="fred", upload=upload())

    folder = next(tag for tag in tag_store.tags.values() if tag.full_path == "Mirror/specs")
    assert folder.owner_id == lib.owner_id
    assert folder.type == TagType.DOCUMENT


@pytest.mark.asyncio
async def test_a_path_that_would_leave_the_library_creates_nothing(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    with pytest.raises(InvalidSourceRequest):
        await service.write_document(
            pod(),
            library_id=lib.id,
            path="../elsewhere/leak.md",
            source_key="leak.md",
            document_version=None,
            source_tag="fred",
            upload=upload(),
        )

    assert list(tag_store.tags) == [lib.id]
    assert await _metadata_store().get_all_metadata({}) == []


@pytest.mark.asyncio
async def test_a_document_follows_its_source_when_the_source_moves_it(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    await service.write_document(caller, library_id=lib.id, path="draft/spec.md", source_key="spec", document_version=None, source_tag="fred", upload=upload())
    await service.write_document(caller, library_id=lib.id, path="final/spec.md", source_key="spec", document_version=None, source_tag="fred", upload=upload())

    document = await _metadata_store().get_metadata_by_source_key(lib.id, "spec")
    assert document is not None
    final = next(tag for tag in tag_store.tags.values() if tag.full_path == "Mirror/final")
    assert document.tags.tag_ids == [final.id]


# --------------------------------------------------------------------------
# Removal
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_removing_a_document_does_not_disturb_the_library(tag_store):
    lib = library(tag_store)
    before = lib.model_copy(deep=True)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    for key in ("kept.md", "dropped.md"):
        await service.write_document(caller, library_id=lib.id, path=key, source_key=key, document_version=None, source_tag="fred", upload=upload(name=key))

    await service.remove_document(caller, library_id=lib.id, source_key="dropped.md")

    after = tag_store.tags[lib.id]
    assert (after.name, after.path, after.description, after.type) == (before.name, before.path, before.description, before.type)
    remaining = await _metadata_store().get_metadata_in_tag(lib.id)
    assert [d.source.source_key for d in remaining] == ["kept.md"]


@pytest.mark.asyncio
async def test_removing_what_is_already_gone_is_not_an_error(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    outcome = await service.remove_document(pod(), library_id=lib.id, source_key="never-written.md")

    assert outcome.removed is False


@pytest.mark.asyncio
async def test_silence_is_not_a_removal(tag_store):
    """A run that mentions one document leaves every other one where it is."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    for key in ("a.md", "b.md", "c.md"):
        await service.write_document(caller, library_id=lib.id, path=key, source_key=key, document_version=None, source_tag="fred", upload=upload(name=key))

    await service.write_document(caller, library_id=lib.id, path="a.md", source_key="a.md", document_version="again", source_tag="fred", upload=upload(name="a.md"))

    keys = sorted(d.source.source_key or "" for d in await _metadata_store().get_metadata_in_tag(lib.id))
    assert keys == ["a.md", "b.md", "c.md"]


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_service_identity_with_no_grant_over_the_library_is_refused(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable=set()))
    caller = pod()
    assert "service_agent" in caller.roles

    with pytest.raises(AuthorizationError):
        await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())
    with pytest.raises(AuthorizationError):
        await service.remove_document(caller, library_id=lib.id, source_key="readme.md")

    assert await _metadata_store().get_all_metadata({}) == []


@pytest.mark.asyncio
async def test_a_grant_over_one_library_authorizes_nothing_in_another(tag_store):
    mine = library(tag_store, name="Mine")
    theirs = library(tag_store, name="Theirs")
    service = _service(GrantedLibraryRebac(tag_store, writable={mine.id}))

    with pytest.raises(AuthorizationError):
        await service.write_document(pod(), library_id=theirs.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    assert await _metadata_store().get_metadata_in_tag(theirs.id) == []


# --------------------------------------------------------------------------
# The library's own source version
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_library_that_never_recorded_a_source_version_reports_its_absence(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    assert await service.read_source_version(pod(), lib.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["9d2f1a7", "2026-w03", "AAECAwQFBgc=", "r7"])
async def test_a_source_version_comes_back_exactly_as_it_was_given(tag_store, version):
    """Unordered, undated, non-numeric: Fred stores it and reads nothing into it."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    await service.record_source_version(caller, lib.id, version)

    assert await service.read_source_version(caller, lib.id) == version


@pytest.mark.asyncio
async def test_recording_a_source_version_leaves_the_library_otherwise_alone(tag_store):
    lib = library(tag_store)
    before = lib.model_copy(deep=True)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    await service.record_source_version(pod(), lib.id, "cursor-1")

    after = tag_store.tags[lib.id]
    assert (after.name, after.path, after.description, after.updated_at) == (
        before.name,
        before.path,
        before.description,
        before.updated_at,
    )


@pytest.mark.asyncio
async def test_reading_a_source_version_needs_permission_over_that_library(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable=set(), readable=set()))

    with pytest.raises(AuthorizationError):
        await service.read_source_version(pod(), lib.id)


# --------------------------------------------------------------------------
# Which machine fills the library
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recording_the_machine_marks_the_library(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    await service.record_synchronized_by(pod(), lib.id, "knowledge_base:ab12")

    assert tag_store.tags[lib.id].synchronized_by == "knowledge_base:ab12"
    assert tag_store.tags[lib.id].is_synchronized


@pytest.mark.asyncio
async def test_recording_the_same_machine_again_is_not_a_change(tag_store):
    """Creation can be retried after a failure further along, so this must be safe."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    await service.record_synchronized_by(pod(), lib.id, "knowledge_base:ab12")

    assert await service.record_synchronized_by(pod(), lib.id, "knowledge_base:ab12") == "knowledge_base:ab12"


@pytest.mark.asyncio
async def test_moving_a_library_to_another_machine_is_refused(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    await service.record_synchronized_by(pod(), lib.id, "knowledge_base:ab12")

    with pytest.raises(InvalidSourceRequest) as refused:
        await service.record_synchronized_by(pod(), lib.id, "knowledge_base:cd34")

    assert refused.value.code == "synchronized_by_conflict"
    assert tag_store.tags[lib.id].synchronized_by == "knowledge_base:ab12"


@pytest.mark.asyncio
async def test_recording_the_machine_needs_permission_over_that_library(tag_store):
    """The grant comes first, so marking before it exists is refused rather than applied."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable=set(), readable=set()))

    with pytest.raises(AuthorizationError):
        await service.record_synchronized_by(pod(), lib.id, "knowledge_base:ab12")

    assert tag_store.tags[lib.id].synchronized_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "   "])
async def test_a_blank_machine_reference_is_refused(tag_store, blank):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    with pytest.raises(InvalidSourceRequest):
        await service.record_synchronized_by(pod(), lib.id, blank)

    assert tag_store.tags[lib.id].synchronized_by is None


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_write_by_a_service_is_not_recorded_as_a_person_s(tag_store, kpi_writer):
    """Counting scheduled machine volume as human activity is wrong by exactly that volume."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    actors = kpi_writer.actors_for("document.created_total")
    assert actors, "the write emitted no document.created_total to attribute"
    for actor in actors:
        assert actor.type == "system"
        assert actor.user_id == caller.uid


@pytest.mark.asyncio
async def test_a_person_s_write_is_still_recorded_as_a_person_s(tag_store, kpi_writer):
    """Only the actor type moves: a human uploading through this surface is a human."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    person = KeycloakUser(uid="alice", username="alice", roles=["admin"], email=None)

    await service.write_document(person, library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    actors = kpi_writer.actors_for("document.created_total")
    assert actors and all(actor.type == "human" for actor in actors)


# --------------------------------------------------------------------------
# A write is accepted onto the shared pipeline, with a task to follow
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [None, *IngestionProcessingProfile])
async def test_a_write_is_one_task_and_one_push_file_on_the_shared_pipeline(tag_store, scheduler, task_service, monkeypatch, profile):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    config = ApplicationContext.get_instance().get_config()
    monkeypatch.setattr(config.processing, "default_profile", IngestionProcessingProfile.fast)
    extract = AsyncMock(wraps=service._ingestion_service.extract_metadata)
    monkeypatch.setattr(service._ingestion_service, "extract_metadata", extract)
    caller = pod()
    background = BackgroundTasks()

    accepted = await service.write_document(
        caller,
        library_id=lib.id,
        path="specs/api.md",
        source_key="specs/api.md",
        document_version="etag-1",
        source_tag="fred",
        upload=upload(name="api.md"),
        background_tasks=background,
        **({"profile": profile} if profile is not None else {}),
    )

    document = await _metadata_store().get_metadata_by_source_key(lib.id, "specs/api.md")
    assert document is not None
    assert accepted.document_uid == document.document_uid
    folder = next(tag for tag in tag_store.tags.values() if tag.full_path == "Mirror/specs")
    expected_profile = profile or IngestionProcessingProfile.medium
    assert extract.call_args.kwargs["profile"] == expected_profile
    assert document.processing.profile == expected_profile
    assert config.processing.default_profile == IngestionProcessingProfile.fast

    [submission] = scheduler.submissions
    assert (submission.user, submission.pipeline_name, submission.background_tasks) == (caller, "library_sync", background)
    [file] = submission.files
    assert (file.document_uid, file.tags, file.source_tag, file.profile, file.task_id, file.display_name) == (
        document.document_uid,
        [folder.id],
        "fred",
        expected_profile,
        accepted.task_id,
        "api.md",
    )

    run = await task_service.get_run(accepted.task_id)
    assert run is not None
    assert (run.kind, TaskState(run.state), run.created_by, run.team_id, run.execution_id) == ("ingestion", TaskState.pending, caller.uid, TEAM, run.execution_id)
    assert run.execution_id.startswith("ingestion-")
    assert run.target is not None
    assert TaskTarget(**run.target) == TaskTarget(type="document", id=document.document_uid, label="api.md")


@pytest.mark.asyncio
async def test_the_pipeline_client_is_built_the_way_the_upload_surface_builds_it(tag_store, scheduler):
    """Same configuration in, so the two surfaces cannot drift apart on parallelism or profiles."""
    config = ApplicationContext.get_instance().get_config()

    _service(GrantedLibraryRebac(tag_store))

    assert scheduler.built["scheduler_config"] is config.scheduler
    assert scheduler.built["processing_config"] is config.processing
    assert scheduler.built["max_parallelism"] == config.scheduler.temporal.ingestion_workflow_parallelism


@pytest.mark.asyncio
async def test_the_document_exists_before_the_pipeline_is_asked_for_it(tag_store, scheduler):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    await service.write_document(pod(), library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    assert scheduler.saw_rows == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline_refuses", [False, True])
async def test_the_upload_s_copy_is_gone_once_the_write_is_answered(tag_store, scheduler, monkeypatch, pipeline_refuses):
    """The worker restores the input from the content store; nothing waits on this file."""
    written: list[pathlib.Path] = []
    real_uploadfile_to_path = service_module.uploadfile_to_path

    def _recording(upload_file, *, filename=None):
        path = real_uploadfile_to_path(upload_file, filename=filename)
        written.append(path)
        return path

    monkeypatch.setattr(service_module, "uploadfile_to_path", _recording)
    scheduler.fails = pipeline_refuses
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    await service.write_document(pod(), library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    [path] = written
    assert not path.parent.parent.exists()


@pytest.mark.asyncio
async def test_a_stack_that_cannot_schedule_refuses_the_write_before_taking_anything(tag_store, scheduler, task_service, monkeypatch):
    monkeypatch.setattr(ApplicationContext.get_instance().get_config().scheduler, "enabled", False)
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    with pytest.raises(SynchronizationUnavailable):
        await service.write_document(pod(), library_id=lib.id, path="specs/readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())

    assert await _metadata_store().get_all_metadata({}) == []
    assert list(tag_store.tags) == [lib.id]
    assert (await task_service.list_tasks()).tasks == []
    assert scheduler.submissions == []


# --------------------------------------------------------------------------
# A write the pipeline refuses says so, and leaves nothing behind
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_temporal_outage_keeps_an_accepted_write_and_its_pending_task(tag_store, scheduler, task_service):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    scheduler.fails = True
    accepted = await service.write_document(pod(), library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())
    assert await _metadata_store().get_metadata_by_source_key(lib.id, "readme.md") is not None
    run = await task_service.get_run(accepted.task_id)
    assert run.state == TaskState.pending
    assert run.execution_id is not None


@pytest.mark.asyncio
async def test_a_failed_rewrite_does_not_destroy_the_document_it_was_replacing(tag_store, scheduler, task_service):
    """The caller asked to replace a document, not to remove it; its next run converges."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version="etag-1", source_tag="fred", upload=upload())

    scheduler.fails = True
    accepted = await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version="etag-2", source_tag="fred", upload=upload())
    assert await _metadata_store().get_metadata_by_source_key(lib.id, "readme.md") is not None
    assert (await task_service.get_run(accepted.task_id)).state == TaskState.pending


@pytest.mark.asyncio
async def test_rewriting_a_key_takes_the_previous_revision_out_of_the_index(tag_store, scheduler, monkeypatch):
    """A chunk's id comes from where it sits in the content.

    So a new revision's chunks land beside the old ones, not over them, and a
    source watched for months would grow an index of every revision it ever had
    while search kept answering from text the document no longer contains.
    """
    dropped: list[str] = []

    class _VectorStore:
        def delete_vectors_for_document(self, *, document_uid):
            dropped.append(document_uid)

    ctx = ApplicationContext.get_instance()
    monkeypatch.setattr(ctx, "get_create_vector_store", lambda embedder: _VectorStore())
    monkeypatch.setattr(ctx, "get_embedder", object)

    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()

    await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version="1", source_tag="fred", upload=upload())
    # Nothing was there to replace, so nothing was dropped.
    assert dropped == []

    second = await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version="2", source_tag="fred", upload=upload())

    document = await _metadata_store().get_metadata_by_source_key(lib.id, "readme.md")
    assert document is not None
    assert dropped == [document.identity.document_uid]
    # The pipeline is asked for the same document again — not a second one —
    # and each write is its own task.
    submitted = [file.document_uid for submission in scheduler.submissions for file in submission.files]
    assert submitted == [document.identity.document_uid, document.identity.document_uid]
    assert second.document_uid == document.identity.document_uid
    assert len({file.task_id for submission in scheduler.submissions for file in submission.files}) == 2


@pytest.mark.asyncio
async def test_removing_a_keyed_document_that_sits_in_no_folder_still_removes_it(tag_store):
    """A platform import can carry the key without the membership.

    Removing a folder it is not in would report success and leave the document,
    its content, and the key it holds behind — so the next write would collide
    with a document nobody can reach.
    """
    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging

    lib = library(tag_store)
    await _metadata_store().save_metadata(
        DocumentMetadata(
            identity=Identity(document_name="orphan.md", document_uid="imported-orphan"),
            source=SourceInfo(
                source_type=SourceType.PUSH,
                source_tag="fred",
                pull_location=None,
                source_library_id=lib.id,
                source_key="orphan.md",
            ),
            tags=Tagging(tag_ids=[]),
        )
    )
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))

    outcome = await service.remove_document(pod(), library_id=lib.id, source_key="orphan.md")

    assert outcome.removed is True
    assert await _metadata_store().get_metadata_by_source_key(lib.id, "orphan.md") is None
    assert await _metadata_store().get_metadata_by_uid("imported-orphan") is None


# --------------------------------------------------------------------------
# What the library holds, and where each write stands
# --------------------------------------------------------------------------


async def _write(service: service_module.LibrarySyncService, caller: KeycloakUser, lib: Tag, key: str, version: str | None = None):
    return await service.write_document(caller, library_id=lib.id, path=key, source_key=key, document_version=version, source_tag="fred", upload=upload(name=key.rsplit("/", 1)[-1]))


async def _record(document_uid: str, stages: dict[ProcessingStage, ProcessingStatus]) -> None:
    """Move stages the way an activity does: read the row, mark it, persist in place."""
    store = _metadata_store()
    metadata = await store.get_metadata_by_uid(document_uid)
    assert metadata is not None
    for stage, status in stages.items():
        metadata.set_stage_status(stage, status)
    assert await store.update_metadata(metadata) is True


async def _state_of(service: service_module.LibrarySyncService, caller: KeycloakUser, lib: Tag) -> str:
    [item] = (await service.list_documents(caller, library_id=lib.id, limit=10)).items
    return item.state


@pytest.mark.asyncio
async def test_a_library_lists_its_keyed_documents_in_key_order(tag_store):
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    second = await _write(service, caller, lib, "specs/b.md", "etag-b")
    first = await _write(service, caller, lib, "specs/a.md", "etag-a")

    listing = await service.list_documents(caller, library_id=lib.id, limit=100)

    assert [(d.source_key, d.document_uid, d.document_version) for d in listing.items] == [
        ("specs/a.md", first.document_uid, "etag-a"),
        ("specs/b.md", second.document_uid, "etag-b"),
    ]
    assert listing.truncated is False


@pytest.mark.asyncio
async def test_a_write_is_in_progress_until_the_pipeline_s_last_stage_lands(tag_store):
    """Accepted is not done: the bytes are stored, a preview is halfway, vectors are the end."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    accepted = await _write(service, caller, lib, "readme.md")

    assert await _state_of(service, caller, lib) == "in_progress"
    await _record(accepted.document_uid, {ProcessingStage.PREVIEW_READY: ProcessingStatus.DONE})
    assert await _state_of(service, caller, lib) == "in_progress"
    await _record(accepted.document_uid, {ProcessingStage.VECTORIZED: ProcessingStatus.DONE})
    assert await _state_of(service, caller, lib) == "succeeded"


@pytest.mark.asyncio
async def test_a_write_the_pipeline_lost_reads_failed(tag_store):
    """The repair that closes a timed-out run's stages is what this listing then reads."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    accepted = await _write(service, caller, lib, "readme.md")
    await _record(accepted.document_uid, {ProcessingStage.PREVIEW_READY: ProcessingStatus.IN_PROGRESS})

    assert await mark_in_progress_stages_failed(accepted.document_uid, "Execution timed_out") is True

    assert await _state_of(service, caller, lib) == "failed"


@pytest.mark.asyncio
async def test_a_write_no_worker_ever_picked_up_reads_failed(tag_store, task_service, scheduler):
    scheduler.complete = False
    """Reconciliation, not an activity, ends a task the worker fleet never ran — the document must follow."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    accepted = await _write(service, caller, lib, "readme.md")
    assert await _state_of(service, caller, lib) == "in_progress"

    class _TimedOut:
        async def get_status(self, workflow_id):
            return ExecutionStatus.timed_out

        async def cancel(self, workflow_id):
            return None

    reconciler = TaskService(store=task_service.store, bus=MemoryEventBus(), control=_TimedOut(), on_reconciled_terminal=on_reconciled_terminal)
    assert await reconciler.reconcile_task(accepted.task_id) is True

    assert await _state_of(service, caller, lib) == "failed"


@pytest.mark.asyncio
async def test_a_rewritten_key_is_in_progress_again(tag_store):
    """The previous run's stages do not carry over: new bytes are owed a new outcome."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    first = await _write(service, caller, lib, "readme.md", "etag-1")
    await _record(first.document_uid, {ProcessingStage.PREVIEW_READY: ProcessingStatus.DONE, ProcessingStage.VECTORIZED: ProcessingStatus.DONE})
    assert await _state_of(service, caller, lib) == "succeeded"

    await _write(service, caller, lib, "readme.md", "etag-2")

    [item] = (await service.list_documents(caller, library_id=lib.id, limit=10)).items
    assert (item.document_uid, item.document_version, item.state) == (first.document_uid, "etag-2", "in_progress")


@pytest.mark.asyncio
async def test_a_person_s_upload_in_the_library_is_not_listed(tag_store):
    """No key, so the caller could neither address it nor say whether it is in sync."""
    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging

    lib = library(tag_store)
    await _metadata_store().save_metadata(
        DocumentMetadata(
            identity=Identity(document_name="notes.md", document_uid="uploaded-by-hand"),
            source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred", pull_location=None),
            tags=Tagging(tag_ids=[lib.id]),
        )
    )
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    await _write(service, caller, lib, "readme.md")

    listing = await service.list_documents(caller, library_id=lib.id, limit=10)

    assert [d.source_key for d in listing.items] == ["readme.md"]


@pytest.mark.asyncio
async def test_another_library_s_keys_are_not_listed(tag_store):
    mine = library(tag_store, name="Mine")
    theirs = library(tag_store, name="Theirs")
    service = _service(GrantedLibraryRebac(tag_store, writable={mine.id, theirs.id}))
    caller = pod()
    kept = await _write(service, caller, mine, "readme.md", "mine")
    await _write(service, caller, theirs, "readme.md", "theirs")

    listing = await service.list_documents(caller, library_id=mine.id, limit=10)

    assert [(d.document_uid, d.document_version) for d in listing.items] == [(kept.document_uid, "mine")]


@pytest.mark.asyncio
async def test_a_listing_is_bounded_and_says_when_it_is(tag_store):
    """A run reconciling against part of a library must know it is a part."""
    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    for key in ("a.md", "b.md", "c.md"):
        await _write(service, caller, lib, key)

    short = await service.list_documents(caller, library_id=lib.id, limit=2)
    whole = await service.list_documents(caller, library_id=lib.id, limit=3)

    assert ([d.source_key for d in short.items], short.truncated) == (["a.md", "b.md"], True)
    assert ([d.source_key for d in whole.items], whole.truncated) == (["a.md", "b.md", "c.md"], False)


@pytest.mark.asyncio
async def test_listing_a_library_is_a_read_of_it(tag_store):
    """A grant that reads the library lists it; one that holds nothing over it is refused."""
    lib = library(tag_store)
    reader = _service(GrantedLibraryRebac(tag_store, writable=set(), readable={lib.id}))
    stranger = _service(GrantedLibraryRebac(tag_store, writable=set(), readable=set()))

    assert (await reader.list_documents(pod(), library_id=lib.id, limit=10)).items == []
    with pytest.raises(AuthorizationError):
        await stranger.list_documents(pod(), library_id=lib.id, limit=10)


@pytest.mark.asyncio
async def test_owner_resolution_failure_before_admission_does_not_wedge_the_document(tag_store, task_service, monkeypatch):
    from knowledge_flow_backend.features.ingestion import ingestion_controller

    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    caller = pod()
    resolve = ingestion_controller.resolve_tag_owners
    monkeypatch.setattr(ingestion_controller, "resolve_tag_owners", AsyncMock(side_effect=RuntimeError("owner lookup unavailable")))
    with pytest.raises(RuntimeError, match="owner lookup unavailable"):
        await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())
    [failed] = (await task_service.list_tasks()).tasks
    assert failed.state == TaskState.failed
    assert (await task_service.get_run(failed.task_id)).execution_id is None
    monkeypatch.setattr(ingestion_controller, "resolve_tag_owners", resolve)
    accepted = await service.write_document(caller, library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred", upload=upload())
    assert accepted.task_id != failed.task_id


@pytest.mark.asyncio
async def test_active_source_ingestion_is_a_conflict(tag_store, task_service, scheduler):
    from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionAlreadyActive

    lib = library(tag_store)
    service = _service(GrantedLibraryRebac(tag_store, writable={lib.id}))
    scheduler.complete = False
    args = dict(library_id=lib.id, path="readme.md", source_key="readme.md", document_version=None, source_tag="fred")
    accepted = await service.write_document(pod(), **args, upload=upload())
    with pytest.raises(IngestionAlreadyActive):
        await service.write_document(pod(), **args, upload=upload())
    assert not TaskState((await task_service.get_run(accepted.task_id)).state).is_terminal
    assert (await service.list_documents(pod(), library_id=lib.id, limit=10)).items
