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

"""#2149 — permanently deleting a document must give its storage quota back.

Usage is charged on save (`_persist_metadata_and_follow_up` →
`_adjust_team_storage`), but both hard-delete paths used to drop the metadata
row without ever releasing it. Normal upload/delete cycles therefore drifted
`current_resources_storage_size` upward until valid uploads were rejected by a
phantom quota exhaustion.

These tests drive the two real delete entry points against fake stores and
assert on the deltas that reach the team/user counters, rather than asserting
that some helper was called — the counter is what the bug was about.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    AccessInfo,
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
    Tagging,
)
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.metadata import service as service_module
from knowledge_flow_backend.features.metadata.service import MetadataService

DOC_SIZE = 4096


def _make_metadata(
    uid: str,
    *,
    tag_ids: list[str],
    size: int | None = DOC_SIZE,
    author: str | None = None,
) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(
            document_name=f"{uid}.pdf",
            document_uid=uid,
            title=uid,
            author=author,
            modified=datetime.now(timezone.utc),
        ),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads", pull_location=None, date_added_to_kb=datetime.now(timezone.utc)),
        file=FileInfo(file_size_bytes=size),
        tags=Tagging(tag_ids=tag_ids),
        processing=Processing(),
        access=AccessInfo(),
    )


class _PermissiveRebac:
    """Grants every permission; `lookup_subjects` returns the team owners the
    test wants `_adjust_team_storage` to resolve for a tag."""

    def __init__(self, team_owners: list[str] | None = None):
        self._team_owners = team_owners or []

    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        return None

    async def lookup_subjects(self, reference, relation, resource):
        return [SimpleNamespace(id=team_id) for team_id in self._team_owners]


class _FakeMetadataStore:
    """Emulates the store contract: `delete_metadata` reports whether *this*
    call removed the row. `row_already_deleted` simulates the concurrent loser —
    it still holds the metadata it loaded, but the row is gone by the time its
    conditional DELETE runs."""

    def __init__(
        self,
        metadata: DocumentMetadata | None,
        *,
        delete_raises: Exception | None = None,
        row_already_deleted: bool = False,
    ):
        self._metadata = metadata
        self._delete_raises = delete_raises
        self.row_already_deleted = row_already_deleted
        self.deleted: list[str] = []
        self.save_sessions: list[object] = []

    async def get_metadata_by_uid(self, uid: str) -> DocumentMetadata | None:
        return self._metadata

    async def delete_metadata(self, uid: str, session=None) -> bool:
        if self._delete_raises is not None:
            raise self._delete_raises
        if self._metadata is None or self.row_already_deleted:
            return False
        self.deleted.append(uid)
        self._metadata = None
        return True

    async def save_metadata(self, metadata: DocumentMetadata, session=None) -> None:
        self._metadata = metadata
        self.save_sessions.append(session)


def _install_fakes(monkeypatch, *, tag_owner: str, known_teams: set[str]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Wire the ambient singletons `_adjust_team_storage` reaches for.

    Returns the two recording lists: team increments and user increments, each
    as (id, delta) — the deltas are the assertion surface for every test here.
    """
    team_increments: list[tuple[str, int]] = []
    user_increments: list[tuple[str, int]] = []

    class _FakeTeamStore:
        def __init__(self, engine):
            pass

        async def get_by_team_id(self, team_id):
            return SimpleNamespace(id=str(team_id)) if str(team_id) in known_teams else None

        async def increment_current_storage_size(self, team_id, delta, session=None):
            team_increments.append((str(team_id), delta))

    class _FakeUserStore:
        async def increment_current_storage_size(self, user_id, delta, session=None):
            user_increments.append((str(user_id), delta))

    monkeypatch.setattr(service_module, "TeamMetadataStore", _FakeTeamStore)
    monkeypatch.setattr(service_module, "get_user_store", lambda: _FakeUserStore())

    # A real (empty) SQLite engine: the delete+release path now opens a genuine
    # transaction, and the fakes assert on the deltas that reach it. Nothing is
    # written to this database — it exists so the transaction boundary is real.
    engine = create_async_engine("sqlite+aiosqlite://")

    fake_context = SimpleNamespace(
        get_tag_store=lambda: SimpleNamespace(
            get_tag_by_id=_make_async(SimpleNamespace(id="tag-1", owner_id=tag_owner)),
        ),
        get_pg_async_engine=lambda: engine,
        get_kpi_writer=lambda: SimpleNamespace(count=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        service_module.ApplicationContext,
        "get_instance",
        staticmethod(lambda: fake_context),
    )

    return team_increments, user_increments


def _make_async(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


def _build_service(metadata_store: _FakeMetadataStore, rebac: _PermissiveRebac) -> MetadataService:
    service = MetadataService.__new__(MetadataService)
    service.rebac = rebac  # type: ignore[assignment]
    service.metadata_store = metadata_store  # type: ignore[assignment]
    service.vector_store = None
    service.content_store = None  # type: ignore[assignment]
    service._remove_tag_as_parent_in_rebac = _make_async(None)  # type: ignore[method-assign]
    return service


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=f"{uid}@localhost", roles=["admin"])


@pytest.mark.asyncio
async def test_deleting_a_team_document_releases_the_team_counter(monkeypatch) -> None:
    """AC1 — a team-owned document's bytes come off every applicable team counter."""
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-1", tag_ids=["tag-1"])
    service = _build_service(_FakeMetadataStore(metadata), _PermissiveRebac(team_owners=["team-a"]))

    await service.delete_document_and_artifacts(_user(str(uuid4())), "doc-1")

    assert team_increments == [("team-a", -DOC_SIZE)]


@pytest.mark.asyncio
async def test_deleting_a_personal_document_releases_the_owning_users_counter(monkeypatch) -> None:
    """AC2 — the bytes come off the counter of the user who OWNS the tag.

    A real personal tag carries the owner's uid, not the literal "personal":
    `TagService` sets `owner_id = team_id or user.uid` (tag_service.py:208). The
    acting user differs from the owner here on purpose — the charge side bills the
    tag owner, so the release has to bill the same account, or deleting someone
    else's document would credit the wrong personal space.
    """
    owner_uid = str(uuid4())
    deleter_uid = str(uuid4())
    team_increments, user_increments = _install_fakes(monkeypatch, tag_owner=owner_uid, known_teams=set())
    metadata = _make_metadata("doc-2", tag_ids=["tag-1"])
    service = _build_service(_FakeMetadataStore(metadata), _PermissiveRebac(team_owners=[]))

    await service.delete_document_and_artifacts(_user(deleter_uid), "doc-2")

    assert user_increments == [(owner_uid, -DOC_SIZE)]
    assert team_increments == []


@pytest.mark.asyncio
async def test_removing_the_last_tag_releases_using_the_pre_removal_tags(monkeypatch) -> None:
    """AC3 — and the regression this path is most likely to hit again.

    `remove_tag_id_from_document` empties `metadata.tags.tag_ids` *before* it
    deletes the row. Resolving ownership from the mutated (empty) list makes
    `_adjust_team_storage` bail at its `if not all_tags` guard and release
    nothing at all — silently, since it swallows its own errors.
    """
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-3", tag_ids=["tag-1"])
    service = _build_service(_FakeMetadataStore(metadata), _PermissiveRebac(team_owners=["team-a"]))
    service._promote_alternate_version = _make_async(None)

    await service.remove_tag_id_from_document(_user(str(uuid4())), metadata, "tag-1")

    assert team_increments == [("team-a", -DOC_SIZE)]


@pytest.mark.asyncio
async def test_repeated_delete_does_not_decrement_twice(monkeypatch) -> None:
    """AC4 — the second delete finds no metadata row and must release nothing;
    a retried delete would otherwise hand back the same bytes on every attempt."""
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-4", tag_ids=["tag-1"])
    store = _FakeMetadataStore(metadata)
    service = _build_service(store, _PermissiveRebac(team_owners=["team-a"]))
    user = _user(str(uuid4()))

    await service.delete_document_and_artifacts(user, "doc-4")
    with pytest.raises(service_module.MetadataNotFound):
        await service.delete_document_and_artifacts(user, "doc-4")

    assert team_increments == [("team-a", -DOC_SIZE)]


@pytest.mark.asyncio
async def test_a_concurrent_loser_does_not_release_the_same_bytes(monkeypatch) -> None:
    """#2149 review finding — the delete is the exactly-once gate.

    `DocumentMetadataRow` has no `version_id_col`, so before the store used a
    conditional DELETE two requests could both load the row, both "succeed", and
    both credit the same bytes — letting a team member zero a counter with N
    concurrent tag removals and then re-upload to the full limit. The store now
    reports whether *this* call removed the row; the loser must release nothing.
    """
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-7", tag_ids=["tag-1"])
    store = _FakeMetadataStore(metadata)
    service = _build_service(store, _PermissiveRebac(team_owners=["team-a"]))

    # Winner removes the row and releases.
    await service.delete_document_and_artifacts(_user(str(uuid4())), "doc-7")

    # Loser still holds the metadata it loaded, but its DELETE matches nothing.
    loser_store = _FakeMetadataStore(metadata, row_already_deleted=True)
    loser = _build_service(loser_store, _PermissiveRebac(team_owners=["team-a"]))
    await loser.delete_document_and_artifacts(_user(str(uuid4())), "doc-7")

    assert team_increments == [("team-a", -DOC_SIZE)]


@pytest.mark.asyncio
async def test_a_failed_metadata_delete_releases_nothing(monkeypatch) -> None:
    """AC5 — the row is still there, so the bytes are still occupied. Releasing
    them here would credit quota for a document that was never removed."""
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-5", tag_ids=["tag-1"])
    store = _FakeMetadataStore(metadata, delete_raises=RuntimeError("postgres is down"))
    service = _build_service(store, _PermissiveRebac(team_owners=["team-a"]))

    with pytest.raises(service_module.MetadataUpdateError):
        await service.delete_document_and_artifacts(_user(str(uuid4())), "doc-5")

    assert team_increments == []


@pytest.mark.asyncio
async def test_deleting_a_document_with_no_recorded_size_is_a_no_op(monkeypatch) -> None:
    """A document ingested before size tracking has `file_size_bytes=None`.
    Releasing `None` as 0 keeps the counter untouched instead of crashing the
    delete or writing a bogus delta."""
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-6", tag_ids=["tag-1"], size=None)
    service = _build_service(_FakeMetadataStore(metadata), _PermissiveRebac(team_owners=["team-a"]))

    await service.delete_document_and_artifacts(_user(str(uuid4())), "doc-6")

    assert team_increments == []


@pytest.mark.asyncio
async def test_a_tag_change_commits_the_save_and_the_charge_together(monkeypatch) -> None:
    """#2149 review — the tag move and the quota move must be one transaction.

    They used to be two: `save_metadata` committed first, and `_adjust_team_storage`
    swallows its own errors, so a failed counter update left the tag moved and the
    charge behind with no signal. Asserting both receive the *same* live session is
    what proves they share a transaction.
    """
    team_increments, _ = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-tagmove", tag_ids=["tag-1"])
    store = _FakeMetadataStore(metadata)
    service = _build_service(store, _PermissiveRebac(team_owners=["team-a"]))

    seen_sessions: list[object] = []

    class _RecordingTeamStore:
        def __init__(self, engine):
            pass

        async def get_by_team_id(self, team_id):
            return SimpleNamespace(id=str(team_id))

        async def increment_current_storage_size(self, team_id, delta, session=None):
            seen_sessions.append(session)
            team_increments.append((str(team_id), delta))

    monkeypatch.setattr(service_module, "TeamMetadataStore", _RecordingTeamStore)

    await service._save_and_move_storage(metadata, old_tags=set(), new_tags={"tag-1"}, user=_user(str(uuid4())))

    assert store.save_sessions and store.save_sessions[0] is not None
    assert seen_sessions and seen_sessions[0] is not None
    assert store.save_sessions[0] is seen_sessions[0], "save and counter update must share one session"
    assert team_increments == [("team-a", DOC_SIZE)]


@pytest.mark.asyncio
async def test_adding_a_tag_still_persists_the_document(monkeypatch) -> None:
    """Caller wiring, not just the helper: `add_tag_id_to_document` must still save.

    The previous test called `_save_and_move_storage` directly, so deleting the
    `save_metadata` call inside it would not have failed anything (#2149 review).
    """
    _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-add", tag_ids=[])
    store = _FakeMetadataStore(metadata)
    service = _build_service(store, _PermissiveRebac(team_owners=["team-a"]))
    service._set_tag_as_parent_in_rebac = _make_async(None)  # type: ignore[method-assign]

    await service.add_tag_id_to_document(_user(str(uuid4())), metadata, "tag-1")

    assert store.save_sessions, "the document must be persisted"
    assert metadata.tags is not None and "tag-1" in metadata.tags.tag_ids


@pytest.mark.asyncio
async def test_a_no_op_tag_change_still_persists_the_document(monkeypatch) -> None:
    """Early-return branch: identical tag sets, or a document with no recorded
    size, must still save the metadata — sessionless, since no counter moves."""
    team_increments, user_increments = _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-noop", tag_ids=["tag-1"], size=None)
    store = _FakeMetadataStore(metadata)
    service = _build_service(store, _PermissiveRebac(team_owners=["team-a"]))

    await service._save_and_move_storage(metadata, old_tags={"tag-1"}, new_tags={"tag-1"}, user=_user(str(uuid4())))

    assert store.save_sessions == [None], "no counter moves, so no transaction is needed"
    assert team_increments == [] and user_increments == []


@pytest.mark.asyncio
async def test_re_adding_a_present_tag_reasserts_its_rebac_parent(monkeypatch) -> None:
    """A retry after a failed ReBAC write must converge.

    The ReBAC parent write runs after the metadata+quota commit, so a failure
    leaves the tag stored with no relation — inaccessible and charged. The retry
    lands on the "already present" branch, which used to short-circuit and make
    that state permanent (#2149 review finding).
    """
    _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-retry", tag_ids=["tag-1"])
    service = _build_service(_FakeMetadataStore(metadata), _PermissiveRebac(team_owners=["team-a"]))

    reasserted: list[str] = []

    async def _record_parent(tag_id, document_uid, actor_uid=None):
        reasserted.append(tag_id)

    service._set_tag_as_parent_in_rebac = _record_parent  # type: ignore[method-assign]

    await service.add_tag_id_to_document(_user(str(uuid4())), metadata, "tag-1")

    assert reasserted == ["tag-1"], "the retry must re-write the parent relation"


@pytest.mark.asyncio
async def test_a_counter_failure_aborts_the_tag_change_instead_of_being_swallowed(monkeypatch) -> None:
    """The load-bearing behaviour change, and previously untested.

    `_save_and_move_storage` no longer routes through `_adjust_team_storage`, which
    logs and swallows. A counter failure must now abort the tag change and surface,
    rather than committing the tag and losing the charge in a log line
    (#2149 review finding).
    """
    _install_fakes(monkeypatch, tag_owner="team-a", known_teams={"team-a"})
    metadata = _make_metadata("doc-fail", tag_ids=[])
    service = _build_service(_FakeMetadataStore(metadata), _PermissiveRebac(team_owners=["team-a"]))
    service._set_tag_as_parent_in_rebac = _make_async(None)  # type: ignore[method-assign]

    async def _boom(*_a, **_k):
        raise RuntimeError("deadlock detected")

    service._apply_storage_deltas = _boom  # type: ignore[method-assign]

    with pytest.raises(service_module.MetadataUpdateError):
        await service.add_tag_id_to_document(_user(str(uuid4())), metadata, "tag-1")
