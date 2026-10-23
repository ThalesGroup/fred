# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4, uuid5

import pytest
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.worker import Worker

from knowledge_flow_backend.features.manager_processing import retrievable
from knowledge_flow_backend.features.manager_processing.retrievable_workflow import SetDocumentRetrievable


@pytest.fixture
def projection(monkeypatch):
    from knowledge_flow_backend.application_context import ApplicationContext

    document, operation, generation = uuid4(), uuid4(), uuid4()
    ids = [str(uuid5(generation, str(i))) for i in (0, 2)]
    vectors = Mock()
    state = {
        "document_id": str(document),
        "operation_id": str(operation),
        "retrievable": False,
        "restore": False,
        "confirmed": False,
        "phase": "ready",
        "manifest": {"generation": str(generation), "artifacts": [], "chunks": 2, "vectors": 2, "vector_ordinals": [0, 2], "rows": None},
    }
    failures = {"confirm": 0, "lost": False}
    client = Mock()
    client.get.side_effect = lambda _: dict(state)

    def post(_path, body):
        assert str(body.operation_id) == state["operation_id"]
        if body.step == "claim":
            if state["phase"] != "ready":
                raise retrievable.ManagerError("retrieval_projection_uncertain", permanent=True)
            state["phase"] = "writing"
        elif body.step == "applied":
            assert state["phase"] in ("writing", "applied")
            state["phase"] = "applied"
        else:
            assert state["phase"] == "applied"
            if failures["confirm"]:
                failures["confirm"] -= 1
                raise retrievable.ManagerError("worker_failed")
            state["confirmed"] = True
            if failures["lost"]:
                failures["lost"] = False
                raise retrievable.ManagerError("worker_failed")

    client.post.side_effect = post
    manager = Mock()
    manager.__enter__ = Mock(return_value=client)
    manager.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(retrievable, "ManagerClient", lambda _: manager)
    context = SimpleNamespace(configuration=SimpleNamespace(manager_processing=SimpleNamespace(enabled=True)), get_manager_vector_store=lambda: vectors)
    monkeypatch.setattr(ApplicationContext, "get_instance", lambda: context)
    return SimpleNamespace(command={"document_id": str(document), "operation_id": str(operation)}, state=state, ids=ids, vectors=vectors, client=client, failures=failures)


@pytest.mark.parametrize("restore,value", [(False, False), (False, True), (True, True), (True, False)])
def test_projection_and_read_only_restore(projection, restore, value):
    p = projection
    p.state.update(restore=restore, retrievable=value)
    assert retrievable.set_document_retrievable(p.command)
    retrievable.record_retrievable_applied(p.command)
    retrievable.confirm_document_retrievable(p.command)
    if restore:
        p.vectors.set_chunks_retrievable.assert_not_called()
    else:
        p.vectors.set_chunks_retrievable.assert_called_once_with(document_uid=p.command["document_id"], chunk_ids=p.ids, value=value)
    p.vectors.verify_chunks_retrievable.assert_called_once_with(document_uid=p.command["document_id"], chunk_ids=p.ids, value=value)
    assert p.state["confirmed"]
    assert not retrievable.set_document_retrievable(p.command)
    retrievable.confirm_document_retrievable(p.command)
    assert p.vectors.verify_chunks_retrievable.call_count == 1


def test_unknown_writer_and_legacy_command_cannot_be_confirmed_or_rewritten(projection):
    for phase in ("writing", "uncertain"):
        projection.state["phase"] = phase
        for action in (retrievable.set_document_retrievable, retrievable.confirm_document_retrievable):
            with pytest.raises(ApplicationError, match="retrieval_projection_uncertain"):
                action(projection.command)
    projection.vectors.set_chunks_retrievable.assert_not_called()
    projection.client.post.assert_not_called()


def test_verification_failure_never_confirms(projection):
    projection.state["phase"] = "applied"
    projection.vectors.verify_chunks_retrievable.side_effect = RuntimeError("partial")
    with pytest.raises(RuntimeError):
        retrievable.confirm_document_retrievable(projection.command)
    projection.client.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["temporary", "closed", "lost", "uncertain"])
async def test_temporal_recovery(projection, failure):
    host = os.environ.get("CONTROL_PLANE_IT_TEMPORAL")
    if not host:
        pytest.skip("requires disposable Temporal via CONTROL_PLANE_IT_TEMPORAL")
    p = projection
    client = await Client.connect(host)
    queue, workflow_id = str(uuid4()), str(uuid4())
    p.failures["confirm"] = 5 if failure == "closed" else int(failure == "temporary")
    p.failures["lost"] = failure == "lost"
    if failure == "uncertain":
        p.vectors.set_chunks_retrievable.side_effect = RuntimeError("remote writer outcome unknown")
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(
            client,
            task_queue=queue,
            workflows=[SetDocumentRetrievable],
            activities=[retrievable.set_document_retrievable, retrievable.record_retrievable_applied, retrievable.confirm_document_retrievable],
            activity_executor=executor,
        ):

            async def run():
                return await client.execute_workflow(SetDocumentRetrievable.run, p.command, id=workflow_id, task_queue=queue, id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY)

            if failure in ("closed", "uncertain"):
                with pytest.raises(WorkflowFailureError):
                    await run()
                if failure == "uncertain":
                    with pytest.raises(WorkflowFailureError):
                        await run()
                    assert not p.state["confirmed"]
                else:
                    await run()
            else:
                await run()
            assert p.vectors.set_chunks_retrievable.call_count == 1
            if failure != "uncertain":
                assert p.state["confirmed"]
                with pytest.raises(WorkflowAlreadyStartedError):
                    await run()


def test_opensearch_partial_projection_is_not_a_success():
    from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter

    store = object.__new__(OpenSearchVectorStoreAdapter)
    store._index = "manager-vectors"
    store.client = Mock()
    for result in ({"updated": 1}, {"updated": 2, "timed_out": True}, {"updated": 2, "version_conflicts": 1}, {"updated": 2, "failures": [{"reason": "failed"}]}):
        store._client.update_by_query.return_value = result
        with pytest.raises(RuntimeError):
            store.set_chunks_retrievable(document_uid="doc", chunk_ids=["published-1", "published-2"], value=False)
    body = store._client.update_by_query.call_args.kwargs["body"]
    assert body["query"]["bool"]["filter"] == [{"ids": {"values": ["published-1", "published-2"]}}, {"term": {"metadata.document_uid": "doc"}}]


def vector_store():
    from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter

    store = object.__new__(OpenSearchVectorStoreAdapter)
    store._index = "manager-vectors"
    store.client = Mock()
    return store


def chunk(identifier):
    return {"_id": identifier, "found": True, "_source": {"metadata": {"document_uid": "doc", "retrievable": False}}}


@pytest.mark.parametrize("fault", ["missing", "partial", "wrong_id", "duplicate", "wrong_document", "wrong_bool", "non_bool", "error"])
def test_grouped_verification_rejects_invalid_elements(fault):
    store = vector_store()
    docs = [chunk("a"), chunk("b")]
    if fault == "missing":
        docs[0]["found"] = False
    elif fault == "partial":
        docs.pop()
    elif fault == "wrong_id":
        docs[0]["_id"] = "other"
    elif fault == "duplicate":
        docs[0]["_id"] = "b"
    elif fault == "wrong_document":
        docs[0]["_source"]["metadata"]["document_uid"] = "other"
    elif fault == "wrong_bool":
        docs[0]["_source"]["metadata"]["retrievable"] = True
    elif fault == "non_bool":
        docs[0]["_source"]["metadata"]["retrievable"] = 0
    else:
        docs[0]["error"] = {"reason": "failed shard"}
    store._client.mget.return_value = {"docs": docs}
    with pytest.raises(RuntimeError):
        store.verify_chunks_retrievable(document_uid="doc", chunk_ids=["a", "b"], value=False)


def test_grouped_verification_bounds_requests_and_source_fields():
    store = vector_store()
    ids = [str(i) for i in range(1001)]

    def response(**kwargs):
        assert len(kwargs["body"]["ids"]) <= 500
        assert kwargs["params"] == {"_source_includes": "metadata.document_uid,metadata.retrievable"}
        return {"docs": [chunk(i) for i in reversed(kwargs["body"]["ids"])]}

    store._client.mget.side_effect = response
    store.verify_chunks_retrievable(document_uid="doc", chunk_ids=ids, value=False)
    assert store._client.mget.call_count == 3
    assert [i for call in store._client.mget.call_args_list for i in call.kwargs["body"]["ids"]] == ids


def test_unsupported_store_rejects_verification():
    from knowledge_flow_backend.core.stores.vector.base_vector_store import BaseVectorStore

    with pytest.raises(NotImplementedError):
        BaseVectorStore.verify_chunks_retrievable(None, document_uid="doc", chunk_ids=["a"], value=False)


@pytest.mark.asyncio
async def test_terminated_workflow_cannot_overlap_a_live_writer(projection):
    host = os.environ.get("CONTROL_PLANE_IT_TEMPORAL")
    if not host:
        pytest.skip("requires disposable Temporal via CONTROL_PLANE_IT_TEMPORAL")
    p = projection
    entered, release = threading.Event(), threading.Event()

    def slow_write(**_kwargs):
        entered.set()
        assert release.wait(30)

    p.vectors.set_chunks_retrievable.side_effect = slow_write
    client = await Client.connect(host)
    queue, workflow_id = str(uuid4()), str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as executor:
        async with Worker(
            client,
            task_queue=queue,
            workflows=[SetDocumentRetrievable],
            activities=[retrievable.set_document_retrievable, retrievable.record_retrievable_applied, retrievable.confirm_document_retrievable],
            activity_executor=executor,
        ):
            handle = await client.start_workflow(SetDocumentRetrievable.run, p.command, id=workflow_id, task_queue=queue)
            try:
                assert await asyncio.to_thread(entered.wait, 10)
                await handle.terminate("fixture: writer thread remains alive")
                with pytest.raises(WorkflowFailureError):
                    await client.execute_workflow(SetDocumentRetrievable.run, p.command, id=workflow_id, task_queue=queue, id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY)
                assert p.vectors.set_chunks_retrievable.call_count == 1
                assert p.state["phase"] == "writing" and not p.state["confirmed"]
            finally:
                release.set()
