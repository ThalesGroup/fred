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

"""`MetadataService`'s descriptive-label surface — `mutate_document_labels`
(the single canonical mutation method), `get_documents_with_label`, and
`list_document_labels`. Runs against a real SQLite-backed
`PostgresDocumentMetadataStore` (not a fake): the invariants under test
(concurrent adds not clobbering each other, a concurrent unrelated save not
erasing a label, non-disclosure of unreadable documents) are properties of
real transactions and real ReBAC-narrowed queries, not something a fully
fake store could prove.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fred_core import RebacDisabledResult
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from knowledge_flow_backend.features.metadata import service as service_module
from knowledge_flow_backend.features.metadata.service import (
    InvalidMetadataRequest,
    MetadataNotFound,
    MetadataService,
)


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / filename}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(uid: str, *, tag_ids: list[str] | None = None) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(
            document_name=f"{uid}.pdf",
            document_uid=uid,
            title=uid,
            modified=datetime.now(timezone.utc),
        ),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred"),
        tags=Tagging(tag_ids=tag_ids or []),
    )


class _FakeRebac:
    """`check_user_permission_or_raise` denies only uids in `denied`;
    `lookup_user_resources` returns `readable_uids` (or `RebacDisabledResult`
    when `disabled=True`, which the service must treat as "everything")."""

    def __init__(self, *, readable_uids: set[str] | None = None, denied: set[str] | None = None, disabled: bool = False):
        self._readable_uids = readable_uids or set()
        self._denied = denied or set()
        self._disabled = disabled

    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        if resource_id in self._denied:
            raise PermissionError(f"denied: {resource_id}")

    async def lookup_user_resources(self, user, permission):
        if self._disabled:
            return RebacDisabledResult()
        return [SimpleNamespace(id=uid) for uid in self._readable_uids]


def _user(uid: str = "u-1") -> SimpleNamespace:
    return SimpleNamespace(uid=uid, username=uid, email=f"{uid}@localhost", roles=["admin"])


def _build_service(engine: AsyncEngine, rebac: _FakeRebac, monkeypatch: pytest.MonkeyPatch) -> MetadataService:
    service = MetadataService.__new__(MetadataService)
    service.metadata_store = PostgresDocumentMetadataStore(engine)  # type: ignore[assignment]
    service.rebac = rebac  # type: ignore[assignment]
    service.vector_store = None
    service.content_store = None  # type: ignore[assignment]

    fake_context = SimpleNamespace(get_pg_async_engine=lambda: engine)
    monkeypatch.setattr(service_module.ApplicationContext, "get_instance", staticmethod(lambda: fake_context))
    return service


@pytest.mark.asyncio
async def test_add_then_remove_returns_the_canonical_stored_set(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "basic.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    added = await service.add_label_to_document(_user(), "doc-1", "DAT", "u-1")
    assert added == ["DAT"]

    removed = await service.remove_label_from_document(_user(), "doc-1", "DAT", "u-1")
    assert removed == []


@pytest.mark.asyncio
async def test_add_updates_modified_and_last_modified_by(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "audit_add.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    doc = _doc("doc-1")
    await service.metadata_store.save_metadata(doc)
    before = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert before is not None

    await service.add_label_to_document(_user(), "doc-1", "DAT", "actor-1")

    after = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.identity.modified is not None
    assert before.identity.modified is not None
    assert after.identity.modified > before.identity.modified
    assert after.identity.last_modified_by == "actor-1"


@pytest.mark.asyncio
async def test_remove_of_an_absent_label_still_updates_the_audit_trail(tmp_path, monkeypatch) -> None:
    """Idempotent at the label-set level, but the request was real: the
    pre-relational-table behavior always touched the audit trail on a
    requested remove, even a no-op one."""
    engine = await _make_sqlite_engine(tmp_path, "audit_remove.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    doc = _doc("doc-1")
    await service.metadata_store.save_metadata(doc)
    before = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert before is not None

    result = await service.remove_label_from_document(_user(), "doc-1", "never-there", "actor-2")

    assert result == []
    after = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.identity.last_modified_by == "actor-2"
    assert before.identity.modified is not None
    assert after.identity.modified is not None
    assert after.identity.modified > before.identity.modified


@pytest.mark.asyncio
async def test_a_genuinely_empty_patch_does_not_touch_the_audit_trail(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "audit_noop.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    doc = _doc("doc-1")
    await service.metadata_store.save_metadata(doc)
    before = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert before is not None

    await service.mutate_document_labels(_user(), "doc-1", modified_by="actor-3")

    after = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.identity.modified == before.identity.modified
    assert after.identity.last_modified_by != "actor-3"


@pytest.mark.asyncio
async def test_add_is_idempotent_through_the_service(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "idempotent.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    await service.add_label_to_document(_user(), "doc-1", "DAT", "u-1")
    result = await service.add_label_to_document(_user(), "doc-1", "DAT", "u-1")

    assert result == ["DAT"]


@pytest.mark.asyncio
async def test_remove_is_idempotent_through_the_service(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "idempotent_remove.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    result = await service.remove_label_from_document(_user(), "doc-1", "never-there", "u-1")

    assert result == []


@pytest.mark.asyncio
async def test_mutation_refused_without_document_update_permission(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "denied.sqlite3")
    service = _build_service(engine, _FakeRebac(denied={"doc-1"}), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    with pytest.raises(PermissionError):
        await service.add_label_to_document(_user(), "doc-1", "DAT", "u-1")

    assert await service.metadata_store.get_labels_for_document("doc-1") == []


@pytest.mark.asyncio
async def test_mutation_on_a_missing_document_raises_not_found(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "missing.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)

    with pytest.raises(MetadataNotFound):
        await service.add_label_to_document(_user(), "does-not-exist", "DAT", "u-1")


@pytest.mark.asyncio
async def test_empty_document_uid_is_rejected(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "empty_uid.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)

    with pytest.raises(InvalidMetadataRequest):
        await service.mutate_document_labels(_user(), "", add=["DAT"], modified_by="u-1")


@pytest.mark.asyncio
async def test_a_label_in_both_add_and_remove_ends_up_absent(tmp_path, monkeypatch) -> None:
    """Documented conflict rule: remove wins."""
    engine = await _make_sqlite_engine(tmp_path, "conflict.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    result = await service.mutate_document_labels(_user(), "doc-1", add=["DAT", "MEX"], remove=["DAT"], modified_by="u-1")

    assert result == ["MEX"]


@pytest.mark.asyncio
async def test_an_empty_request_is_an_idempotent_no_op(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "empty_request.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.add_label_to_document(_user(), "doc-1", "DAT", "u-1")

    result = await service.mutate_document_labels(_user(), "doc-1", modified_by="u-1")

    assert result == ["DAT"]


@pytest.mark.asyncio
async def test_labels_are_an_unordered_set_represented_alphabetically(tmp_path, monkeypatch) -> None:
    """Contract: `document_labels` has no insertion-order column by design —
    labels form a set, and every read path (this mutation response,
    hydration, vocabulary, resolution) renders that set in a deterministic
    alphabetical order, never first-added-first-out. No known consumer
    (frontend chip list, the document_label_search capability's
    list_documents_by_label tool) depends on insertion order — see
    FILESYSTEM.md 'Business labels vs. scope tags'."""
    engine = await _make_sqlite_engine(tmp_path, "ordering_contract.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    result = await service.mutate_document_labels(_user(), "doc-1", add=["Zephyr", "Alpha", "Mike"], modified_by="u-1")

    assert result == ["Alpha", "Mike", "Zephyr"]


@pytest.mark.asyncio
async def test_two_concurrent_adds_of_different_labels_both_survive(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "concurrent.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    await asyncio.gather(
        service.add_label_to_document(_user(), "doc-1", "DAT", "u-1"),
        service.add_label_to_document(_user(), "doc-1", "MEX", "u-1"),
    )

    assert await service.metadata_store.get_labels_for_document("doc-1") == ["DAT", "MEX"]


@pytest.mark.asyncio
async def test_concurrent_retrievable_toggle_does_not_erase_a_label(tmp_path, monkeypatch) -> None:
    """A label add racing an unrelated metadata field's own read-modify-write
    save (`update_document_retrievable`) must not lose the label — the two no
    longer touch the same storage at all."""
    engine = await _make_sqlite_engine(tmp_path, "concurrent_other_field.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    await asyncio.gather(
        service.add_label_to_document(_user(), "doc-1", "DAT", "u-1"),
        service.update_document_retrievable(_user(), "doc-1", False, "u-1"),
    )

    assert await service.metadata_store.get_labels_for_document("doc-1") == ["DAT"]
    hydrated = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert hydrated is not None
    assert hydrated.source.retrievable is False


@pytest.mark.asyncio
async def test_get_documents_with_label_only_returns_readable_documents(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "search_scoped.sqlite3")
    service = _build_service(engine, _FakeRebac(readable_uids={"doc-1"}), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.save_metadata(_doc("doc-2"))  # not readable by this user
    await service.metadata_store.add_label("doc-1", "DAT")
    await service.metadata_store.add_label("doc-2", "DAT")

    results = await service.get_documents_with_label(_user(), "DAT")

    assert [d.identity.document_uid for d in results] == ["doc-1"]


@pytest.mark.asyncio
async def test_get_documents_with_label_returns_everything_when_rebac_disabled(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "search_disabled.sqlite3")
    service = _build_service(engine, _FakeRebac(disabled=True), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.add_label("doc-1", "DAT")

    results = await service.get_documents_with_label(_user(), "DAT")

    assert [d.identity.document_uid for d in results] == ["doc-1"]


@pytest.mark.asyncio
async def test_get_document_uids_with_any_label_unions_multiple_labels(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "any_label_union.sqlite3")
    service = _build_service(engine, _FakeRebac(readable_uids={"doc-1", "doc-2", "doc-3"}), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.save_metadata(_doc("doc-2"))
    await service.metadata_store.save_metadata(_doc("doc-3"))
    await service.metadata_store.add_label("doc-1", "DAT")
    await service.metadata_store.add_label("doc-2", "MEX")
    await service.metadata_store.add_label("doc-3", "OTHER")

    uids = await service.get_document_uids_with_any_label(_user(), ["DAT", "MEX"])

    assert uids == {"doc-1", "doc-2"}


@pytest.mark.asyncio
async def test_get_document_uids_with_any_label_only_returns_readable_documents(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "any_label_scoped.sqlite3")
    service = _build_service(engine, _FakeRebac(readable_uids={"doc-1"}), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.save_metadata(_doc("doc-2"))  # not readable by this user
    await service.metadata_store.add_label("doc-1", "DAT")
    await service.metadata_store.add_label("doc-2", "DAT")

    assert await service.get_document_uids_with_any_label(_user(), ["DAT"]) == {"doc-1"}


@pytest.mark.asyncio
async def test_get_document_uids_with_any_label_returns_empty_set_for_no_labels(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "any_label_empty.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.add_label("doc-1", "DAT")

    assert await service.get_document_uids_with_any_label(_user(), []) == set()
    assert await service.get_document_uids_with_any_label(_user(), ["", "  "]) == set()


@pytest.mark.asyncio
async def test_get_documents_by_uids_only_returns_readable_documents(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "by_uids_scoped.sqlite3")
    service = _build_service(engine, _FakeRebac(readable_uids={"doc-1"}), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.save_metadata(_doc("doc-2"))  # not readable by this user

    results = await service.get_documents_by_uids(_user(), ["doc-1", "doc-2"])

    assert [d.identity.document_uid for d in results] == ["doc-1"]


@pytest.mark.asyncio
async def test_get_documents_by_uids_returns_everything_when_rebac_disabled(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "by_uids_disabled.sqlite3")
    service = _build_service(engine, _FakeRebac(disabled=True), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    results = await service.get_documents_by_uids(_user(), ["doc-1"])

    assert [d.identity.document_uid for d in results] == ["doc-1"]


@pytest.mark.asyncio
async def test_get_documents_by_uids_returns_empty_for_empty_input(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "by_uids_empty.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)

    assert await service.get_documents_by_uids(_user(), []) == []


@pytest.mark.asyncio
async def test_list_document_labels_never_reveals_a_label_only_on_unreadable_documents(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "vocab_scoped.sqlite3")
    service = _build_service(engine, _FakeRebac(readable_uids={"doc-1"}), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.save_metadata(_doc("doc-2"))
    await service.metadata_store.add_label("doc-1", "VISIBLE")
    await service.metadata_store.add_label("doc-2", "SECRET-ON-UNREADABLE-DOC")

    labels = await service.list_document_labels(_user())

    assert labels == ["VISIBLE"]


@pytest.mark.asyncio
async def test_list_document_labels_returns_empty_when_the_user_can_read_nothing(tmp_path, monkeypatch) -> None:
    engine = await _make_sqlite_engine(tmp_path, "vocab_none.sqlite3")
    service = _build_service(engine, _FakeRebac(readable_uids=set()), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.metadata_store.add_label("doc-1", "DAT")

    assert await service.list_document_labels(_user()) == []


@pytest.mark.asyncio
async def test_a_stale_trusted_save_cannot_reintroduce_a_label_removed_after_the_snapshot(tmp_path, monkeypatch) -> None:
    """Reproduces the exact lost-update scenario `_persist_metadata_and_follow_up`
    used to allow: a long-running activity (corpus revectorize, via
    `save_document_metadata_trusted`) loads a `DocumentMetadata` snapshot while
    it still carries 'DAT', the user removes 'DAT' through the canonical
    mutator in the meantime, and the activity's later save of its now-stale
    snapshot must not resurrect 'DAT'."""
    engine = await _make_sqlite_engine(tmp_path, "stale_snapshot.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))
    await service.add_label_to_document(_user(), "doc-1", "DAT", "u-1")

    # The activity's snapshot: hydrated while 'DAT' was still present.
    stale_snapshot = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert stale_snapshot is not None
    assert stale_snapshot.labels == ["DAT"]

    # The user removes 'DAT' through the canonical mutator before the activity saves.
    await service.remove_label_from_document(_user(), "doc-1", "DAT", "u-1")

    # The activity now saves its stale, pre-removal snapshot.
    await service.save_document_metadata_trusted(_user(), stale_snapshot)

    assert await service.metadata_store.get_labels_for_document("doc-1") == []
    hydrated = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert hydrated is not None
    assert hydrated.labels == []


@pytest.mark.asyncio
async def test_a_stale_trusted_save_does_not_erase_a_label_added_after_the_snapshot(tmp_path, monkeypatch) -> None:
    """Symmetric case: a label added AFTER a stale snapshot was taken must
    survive a later trusted save of that (label-less) snapshot."""
    engine = await _make_sqlite_engine(tmp_path, "stale_snapshot_add.sqlite3")
    service = _build_service(engine, _FakeRebac(), monkeypatch)
    await service.metadata_store.save_metadata(_doc("doc-1"))

    stale_snapshot = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert stale_snapshot is not None
    assert stale_snapshot.labels == []

    await service.add_label_to_document(_user(), "doc-1", "MEX", "u-1")

    await service.save_document_metadata_trusted(_user(), stale_snapshot)

    assert await service.metadata_store.get_labels_for_document("doc-1") == ["MEX"]
