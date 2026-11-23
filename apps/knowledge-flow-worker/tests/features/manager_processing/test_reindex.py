# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fred_knowledge.artifacts.errors import ManagerError
from temporalio.exceptions import ApplicationError

from knowledge_flow_worker.features.manager_processing import reindex
from tests.model_admissions import admission


@pytest.fixture
def rebuilding(monkeypatch):
    organization, document, generation, operation, session = (uuid4() for _ in range(5))
    admitted = admission().model_copy(update={"corpus_generation": operation})
    records = [
        {"id": str(uuid4()), "text": f"chunk {i}", "metadata": {"document_uid": str(document), "embedding_model": "old-model", "vector_index": "old-index", "folder_path": "old-folder"}}
        for i in range(70)
    ]
    for record in records:
        record["metadata"]["chunk_uid"] = record["id"]
    work = reindex.VectorReindexWork.model_validate(
        {
            "id": operation,
            "execution_id": uuid4(),
            "organization_id": organization,
            "lease": uuid4(),
            "admission": admitted,
            "offset": 0,
            "document": {
                "document_id": document,
                "generation": generation,
                "prefix": "published/",
                "artifact": {"path": "chunks.jsonl", "size": 100, "sha256": "0" * 64},
                "space_id": uuid4(),
                "session_id": session,
                "retrievable": False,
                "folder_path": None,
            },
        }
    )
    storage = Mock()
    storage.read.side_effect = lambda _prefix, _artifact, path: path.write_text("".join(json.dumps(record) + "\n" for record in records))
    monkeypatch.setattr(reindex, "Artifacts", lambda _settings: storage)
    store = Mock()
    writes = []

    def write(documents, *, ids):
        writes.append((list(documents), list(ids)))
        return list(ids)

    store.add_documents.side_effect = write
    context = SimpleNamespace(configuration=SimpleNamespace(manager_processing=SimpleNamespace(temporary_bytes=10000)), admit_models=Mock(), get_corpus_store=Mock(return_value=store))
    return SimpleNamespace(work=work, records=records, store=store, writes=writes, context=context, client=Mock(post=Mock(return_value=True)))


def test_rebuild_covers_attachments_preserves_ids_and_checkpoints_batches(rebuilding):
    p = rebuilding
    reindex.rebuild(p.context, p.client, p.work)
    assert [call.args[1].offset for call in p.client.post.call_args_list] == [64, 70]
    assert [call.args[1].finished for call in p.client.post.call_args_list] == [False, True]
    ids = [identifier for _, identifiers in p.writes for identifier in identifiers]
    assert ids == [record["id"] for record in p.records]
    for documents, _ in p.writes:
        for doc in documents:
            assert doc.metadata["organization_id"] == str(p.work.organization_id)
            assert doc.metadata["session_id"] == str(p.work.document.session_id)
            assert doc.metadata["retrievable"] is False
            assert doc.metadata["folder_path"] == ""
            assert "embedding_model" not in doc.metadata and "vector_index" not in doc.metadata


def test_resume_writes_only_unacknowledged_chunks(rebuilding):
    p = rebuilding
    reindex.rebuild(p.context, p.client, p.work.model_copy(update={"offset": 64}))
    assert p.store.add_documents.call_count == 1
    assert p.store.add_documents.call_args.kwargs["ids"] == [record["id"] for record in p.records[64:]]
    assert p.client.post.call_args.args[1].finished


def test_incomplete_remote_write_never_acknowledges_success(rebuilding):
    p = rebuilding
    p.store.add_documents.side_effect = lambda _documents, *, ids: ids[:-1]
    with pytest.raises(ManagerError, match="indexing_failed"):
        reindex.rebuild(p.context, p.client, p.work)
    p.client.post.assert_not_called()


def test_corrupt_artifact_cannot_index_another_document(rebuilding):
    p = rebuilding
    p.records[0]["metadata"]["document_uid"] = str(uuid4())
    with pytest.raises(ManagerError, match="integrity_failure"):
        reindex.rebuild(p.context, p.client, p.work)
    p.store.add_documents.assert_not_called()


def test_activity_reports_failure_for_explicit_resume(rebuilding):
    p = rebuilding
    p.client.post.side_effect = [p.work.model_dump(mode="json"), False]
    p.store.add_documents.side_effect = RuntimeError("provider unavailable")
    claim = reindex.ClaimVectorReindex(execution_id=p.work.execution_id)
    with pytest.raises(ApplicationError, match="Corpus reconstruction failed"):
        reindex.step(p.context, p.client, p.work.id, claim)
    assert p.client.post.call_args_list[0].args[0].endswith(f"/{p.work.id}/claim")
    assert not p.client.post.call_args.args[1].succeeded
