# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4, uuid5

import pytest
from langchain_core.documents import Document

from knowledge_flow_backend.features.manager_processing.contracts import Descriptor, Work
from knowledge_flow_backend.features.manager_processing.persistence import ScopedVectors
from knowledge_flow_backend.features.scheduler.scheduler_structures import PipelineDefinition


@pytest.fixture
def descriptor():
    return Descriptor(
        work=Work(contract_version=1, installation_id=uuid4(), processing_id=uuid4(), document_id=uuid4(), original_sha256="a" * 64, profile="fast"),
        organization_id=uuid4(),
        space_id=uuid4(),
        folder_id=uuid4(),
        folder_path="/folder",
        name="test.txt",
        mime="text/plain",
        size=10,
        actor="writer",
        stage="indexing",
        generation=uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        output_prefix="installation/generation/",
        max_output_bytes=100000,
        max_artifacts=100,
        max_chunks=100,
        file={},
        profile_settings={},
        predecessor=None,
        committed=None,
    )


@pytest.fixture
def journal(monkeypatch):
    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.features.manager_processing import client

    writes = []

    class FakeClient:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, path, body):
            writes.append(body.count)

    monkeypatch.setattr(client, "ManagerClient", FakeClient)
    monkeypatch.setattr(ApplicationContext, "get_instance", lambda: SimpleNamespace(configuration=SimpleNamespace(manager_processing=SimpleNamespace(enabled=True))))
    return writes


def test_export_uses_the_existing_temporal_models():
    fixture = Path(__file__).resolve().parents[4] / "control-plane/tests/fixtures/processing/worker-contract.json"
    contract = json.loads(fixture.read_text())
    assert contract["workflow"] == "ProcessPush"
    assert contract["schema"] == PipelineDefinition.model_json_schema()
    submissions = json.loads(fixture.with_name("submissions.json").read_text())
    for submitted in submissions:
        parsed = PipelineDefinition.model_validate(submitted)
        file = parsed.files[0]
        assert file.is_push() and file.task_id is None
        assert file.processed_by.roles == []
        from fred_core.logs.propagation import decode_log_context

        context, error = decode_log_context(file.logging_context)
        assert error is None
        assert context["workflow_id"] == parsed.workflow_id
        assert context["user_id"] == file.processed_by.uid
        assert file.logging_context == parsed.logging_context
        for key, value in contract["profiles"][file.profile.value].items():
            assert getattr(file, key) == value


def test_adaptive_retry_ids_are_fenced_before_writes(descriptor, tmp_path, journal):
    from knowledge_flow_backend.core.stores.vector.base_vector_store import vector_write_observer

    store = SimpleNamespace()

    def add(documents, ids):
        # The existing OpenSearch adaptive retry splits after a provider rejection.
        observer = vector_write_observer.get()
        parts = [Document(page_content="first", metadata=dict(documents[0].metadata)), Document(page_content="second", metadata=dict(documents[0].metadata))]
        assigned = observer.before_write(parts, [f"{ids[0]}::part::{i}" for i in range(2)])
        assert journal == [1, 3]
        store.saved = dict(zip(assigned, parts, strict=True))
        return assigned

    store.add_documents = add
    store.get_chunk = lambda document, identifier: {"text": store.saved[identifier].page_content, "metadata": store.saved[identifier].metadata}
    vectors = ScopedVectors(store, descriptor, None, tmp_path, None)
    written = vectors.add_documents([Document(page_content="first second", metadata={"date_added": datetime.now(timezone.utc), "retrievable": True})])
    assert vectors.ordinals == [1, 2]
    assert vectors.count == 2
    assert written == [str(uuid5(descriptor.generation, str(i))) for i in (1, 2)]
    assert len((tmp_path / "chunks.jsonl").read_text().splitlines()) == 2
    assert vector_write_observer.get() is None


def test_optional_pointer_failure_keeps_cleanup_journal_separate(descriptor, tmp_path, journal):
    def fail(*_, **__):
        raise RuntimeError("provider unavailable")

    vectors = ScopedVectors(SimpleNamespace(add_documents=fail), descriptor, None, tmp_path, None)
    with pytest.raises(RuntimeError):
        vectors.add_documents([Document(page_content="dataset pointer")])
    assert journal == [1]
    assert vectors.count == 0
    assert vectors.ordinals == []


def test_partial_store_success_cannot_publish_a_success_count(descriptor, tmp_path, journal):
    store = SimpleNamespace(add_documents=lambda documents, ids: ids, get_chunk=lambda *_: {})
    vectors = ScopedVectors(store, descriptor, None, tmp_path, None)
    with pytest.raises(RuntimeError, match="indexing_failed"):
        vectors.add_documents([Document(page_content="lost")])
    assert vectors.count == 0


def test_actual_opensearch_resplit_preserves_concurrent_generation_scopes(descriptor, tmp_path, journal):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from knowledge_flow_backend.core.processors.output.vectorization_processor.semantic_splitter import SemanticSplitter
    from knowledge_flow_backend.core.stores.vector.base_vector_store import vector_write_observer
    from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter

    rendezvous = Barrier(2)
    saved = {}
    initial = set()

    class ProviderLimit(RuntimeError):
        status_code = 400
        code = "3210"
        type = "invalid_request_prompt"
        body = {"code": "3210", "type": "invalid_request_prompt", "raw_status_code": 400}

    def write(documents, ids):
        observer = vector_write_observer.get()
        scope = str(observer.descriptor.generation)
        assert all(not any(key.startswith("manager_") for key in doc.metadata) for doc in documents)
        if scope not in initial:
            initial.add(scope)
            rendezvous.wait(timeout=5)
        if len(documents) > 1 or any(len(doc.page_content) > 400 for doc in documents):
            raise ProviderLimit("provider input limit")
        for identifier, doc in zip(ids, documents, strict=True):
            assert identifier in observer.aliases
            saved[identifier] = doc
        return ids

    # Real adapter algorithm, with only the remote model/index write replaced.
    store = object.__new__(OpenSearchVectorStoreAdapter)
    store._index = "manager-fixture"
    store._bulk_size = 100
    store._learned_embedding_batch_cap = None
    store._cap_success_streak = 0
    store._embedding_model_name = "fixture"
    store._vs = SimpleNamespace(add_documents=write)
    store.get_chunk = lambda _, identifier: {"text": saved[identifier].page_content, "metadata": saved[identifier].metadata}

    def ingest(index):
        scoped = descriptor.model_copy(update={"generation": uuid4()})
        directory = tmp_path / str(index)
        directory.mkdir()
        vectors = ScopedVectors(store, scoped, None, directory, SemanticSplitter(chunk_size=800, chunk_overlap=0))
        ids = vectors.add_documents([Document(page_content="long content " * 80, metadata={"retrievable": True}), Document(page_content="short", metadata={"retrievable": True})])
        assert str(uuid5(scoped.generation, "0")) not in ids
        assert str(uuid5(scoped.generation, "1")) in ids
        assert vectors.count == len(ids) > 2
        assert len(vectors.documents) == vectors.count + 1
        assert vector_write_observer.get() is None
        return set(ids)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(ingest, (1, 2)))
    assert first.isdisjoint(second)


@pytest.mark.parametrize("failure", ["authority", "delete", "read", "ack", None])
def test_cleanup_preserves_published_ordinals_and_does_not_ack_remote_failure(monkeypatch, descriptor, failure):
    from knowledge_flow_backend.features.manager_processing import cleanup

    candidate = {
        "work": descriptor.work.model_dump(mode="json"),
        "generation": str(descriptor.generation),
        "cursor": 0,
        "chunks": 4,
        "batch": 200,
        "preserve_objects": True,
        "protected_ordinals": [1, 3],
    }
    acknowledgments = []
    deleted = []

    class Client:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, _):
            if failure == "authority":
                raise RuntimeError("manager SQL unavailable")
            return [candidate]

        def post(self, _, body):
            if failure == "ack":
                raise RuntimeError("manager SQL unavailable")
            acknowledgments.append(body)

    def delete(_, identifier):
        if failure == "delete":
            raise RuntimeError("store unavailable")
        deleted.append(identifier)

    def read(*_):
        if failure == "read":
            raise RuntimeError("store unavailable")
        return {}

    vectors = SimpleNamespace(delete_chunk=delete, get_chunk=read)
    monkeypatch.setattr(cleanup, "ManagerClient", Client)
    monkeypatch.setattr(cleanup, "Artifacts", lambda _: SimpleNamespace())
    context = SimpleNamespace(configuration=SimpleNamespace(manager_processing=SimpleNamespace(enabled=True)), get_manager_vector_store=lambda: vectors)
    if failure:
        with pytest.raises(RuntimeError):
            cleanup.sweep(context)
        assert not acknowledgments
        if failure == "authority":
            assert not deleted
        failure = None
        cleanup.sweep(context)
        assert len(acknowledgments) == 1
    else:
        cleanup.sweep(context)
        cleanup.sweep(context)  # A late write is included in the repeated sweep.
        assert deleted == [str(uuid5(descriptor.generation, str(i))) for i in (0, 2, 0, 2)]
        assert len(acknowledgments) == 2
        assert all(not ack.objects_empty for ack in acknowledgments)


@pytest.mark.parametrize("rendered", [True, False])
def test_extraction_child_freezes_profile_before_context_and_requires_office_preview(monkeypatch, descriptor, tmp_path, rendered):
    import tempfile
    from unittest.mock import Mock

    import fred_core

    monkeypatch.setattr(tempfile, "tempdir", None)
    from knowledge_flow_backend import application_context
    from knowledge_flow_backend.common import config_loader
    from knowledge_flow_backend.features.manager_processing import artifacts, persistence
    from knowledge_flow_backend.features.scheduler import extraction_process

    fixture = Path(__file__).resolve().parents[4] / "control-plane/tests/fixtures/processing/worker-contract.json"
    profile = json.loads(fixture.read_text())["processor_profiles"]["fast"]
    descriptor = descriptor.model_copy(update={"profile_settings": profile, "file": {"input_activity_timeout_seconds": 60}})
    configuration = SimpleNamespace(processing=SimpleNamespace(profiles=SimpleNamespace(fast=None)), manager_processing=SimpleNamespace(enabled=True))
    context = SimpleNamespace(configuration=configuration)

    def build(received):
        assert received.processing.profiles.fast == type(received.processing.profiles.fast).model_validate(profile)
        return context

    monkeypatch.setattr(config_loader, "load_configuration", lambda: configuration)
    monkeypatch.setattr(application_context, "ApplicationContext", build)
    monkeypatch.setattr(artifacts, "Artifacts", lambda _: object())
    pipeline = Mock()
    monkeypatch.setattr(persistence, "scoped_pipeline", lambda *_args, **_kwargs: (pipeline, None))
    monkeypatch.setattr(extraction_process.os, "setsid", lambda: None)
    monkeypatch.setattr(extraction_process, "_install_parent_death_signal", lambda _: None)
    monkeypatch.setattr(extraction_process.DocumentMetadata, "model_validate_json", lambda _: "metadata")
    pdf = tmp_path / "original.pdf"
    pdf.write_bytes(b"%PDF-fixture")
    monkeypatch.setattr(fred_core, "convert_office_file_to_pdf", lambda *_args, **_kwargs: pdf if rendered else None)
    results = []
    causes = []
    monkeypatch.setattr(extraction_process, "_is_permanent", lambda exc: causes.append(repr(exc)) or False)
    monkeypatch.setattr(extraction_process, "_send_outcome", lambda _, result: results.append(result))

    class Exited(BaseException):
        pass

    def exit_process(code):
        raise Exited(code)

    monkeypatch.setattr(extraction_process.os, "_exit", exit_process)
    request = SimpleNamespace(manager_job_json=descriptor.model_dump_json(), config_file=None, input_path=str(tmp_path / "original.docx"), output_dir=str(tmp_path), metadata_json="{}", profile="fast")
    with pytest.raises(Exited):
        extraction_process._child_main(request, None, 1)
    assert pipeline.run_input.call_count == 1, (results, causes)
    expected = {"error": None if rendered else "preview_failed", "permanent": False}
    assert results == [expected]
    assert (tmp_path / "native.pdf").exists() is rendered


@pytest.mark.parametrize("kind", ["native.pdf", "datasets/table.parquet"])
def test_adopt_output_moves_once_and_rejects_excess_before_move(descriptor, tmp_path, kind):
    from knowledge_flow_backend.features.manager_processing.artifacts import adopt_output
    from knowledge_flow_backend.features.manager_processing.client import ManagerError

    output = tmp_path / "output"
    output.mkdir()
    (output / "metadata.json").write_bytes(b"{}")
    source = tmp_path / "scratch.bin"
    source.write_bytes(b"x" * 98)
    bounded = descriptor.model_copy(update={"max_output_bytes": 100})
    inode = source.stat().st_ino
    target = adopt_output(bounded, output, source, kind)
    assert not source.exists()
    assert target.stat().st_ino == inode
    source.write_bytes(b"y" * 99)
    with pytest.raises(ManagerError, match="capacity_exceeded"):
        adopt_output(bounded, output, source, kind)
    assert target.read_bytes() == b"x" * 98
    assert source.exists()


def test_excel_recalculation_scratch_is_removed_on_failed_load(monkeypatch, tmp_path):
    from knowledge_flow_backend.core.processors.input.excel_processor import excel_processor as excel

    scratch = tmp_path / "recalculation"
    scratch.mkdir()
    result = scratch / "input.xlsx"
    result.write_bytes(b"bad workbook")
    monkeypatch.setattr(excel, "recalc_with_libreoffice", lambda _: str(result))
    processor = excel.ExcelProcessor()
    processor.recalc = True
    with pytest.raises(Exception):
        processor._build_extractor("input.xlsx")
    assert not scratch.exists()


def test_excel_converter_scratch_is_removed_on_interruption(monkeypatch, tmp_path):
    from knowledge_flow_backend.core.processors.input.excel_processor import excel_processor as excel

    scratch = tmp_path / "converter"
    scratch.mkdir()
    monkeypatch.setattr(excel.tempfile, "mkdtemp", lambda: str(scratch))
    monkeypatch.setattr(excel.shutil, "which", lambda _: "/fixture/soffice")

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(excel.subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        excel.recalc_with_libreoffice("input.xlsx")
    assert not scratch.exists()


@pytest.mark.parametrize("code", ["preview_failed", "capacity_exceeded", "integrity_failure", "unsupported_input"])
def test_failure_callbacks_preserve_safe_child_codes(code):
    from knowledge_flow_backend.features.manager_processing.service import ManagedIngestionService
    from knowledge_flow_backend.features.scheduler.extraction_process import ExtractionProcessError

    service = object.__new__(ManagedIngestionService)
    service.failure_code = "extraction_failed"
    wrapped = RuntimeError("private provider diagnostic")
    wrapped.__cause__ = ExtractionProcessError(code, permanent=False)
    service.record_failure(wrapped)
    assert service.failure_code == code
    service.record_failure(RuntimeError("secret diagnostic"))
    assert service.failure_code == code


def test_tabular_conversion_interrupts_while_scratch_grows(descriptor, tmp_path):
    import threading

    from knowledge_flow_backend.features.manager_processing.client import ManagerError
    from knowledge_flow_backend.features.manager_processing.persistence import LocalTabularArtifacts

    output = tmp_path / "output"
    output.mkdir()
    store = LocalTabularArtifacts(output, descriptor, temporary_bytes=100)
    interrupted = threading.Event()
    connection = SimpleNamespace(interrupt=interrupted.set)
    with pytest.raises(ManagerError, match="capacity_exceeded"):
        with store.watch_conversion(connection):
            scratch = store.temporary_directory / "growing.parquet"
            with scratch.open("wb") as file:
                for _ in range(100):
                    file.write(b"x" * 30)
                    file.flush()
                    if interrupted.wait(0.01):
                        break
            assert interrupted.is_set()
            assert scratch.stat().st_size < 3000
    assert not any(t.name == "manager-parquet-capacity" for t in threading.enumerate())


@pytest.mark.parametrize("wrapped", [False, True])
def test_parent_capacity_failure_is_non_retryable_even_with_worker_retry_policy(wrapped):
    from temporalio.exceptions import ApplicationError

    from knowledge_flow_backend.features.manager_processing.client import ManagerError, raise_permanent_failure

    error = ManagerError("capacity_exceeded", permanent=True)
    if wrapped:
        wrapper = RuntimeError("output conversion failed")
        wrapper.__cause__ = error
        error = wrapper
    contract = json.loads((Path(__file__).resolve().parents[4] / "control-plane/tests/fixtures/processing/worker-contract.json").read_text())
    assert contract["profiles"]["fast"]["retry_maximum_attempts"] > 1
    with pytest.raises(ApplicationError) as caught:
        raise_permanent_failure(error)
    assert caught.value.non_retryable
    assert caught.value.message == "capacity_exceeded"
    assert raise_permanent_failure(ManagerError("worker_failed")) is None


@pytest.mark.parametrize("received", [b"original", b"origina", b"original!", b"modified"])
def test_original_stream_checks_size_and_digest(descriptor, tmp_path, received):
    import hashlib
    from contextlib import nullcontext

    from knowledge_flow_backend.features.manager_processing.client import ManagerClient, ManagerError

    descriptor.size = len(b"original")
    descriptor.work.original_sha256 = hashlib.sha256(b"original").hexdigest()
    client = ManagerClient.__new__(ManagerClient)
    client.request = lambda *args, **kwargs: nullcontext(SimpleNamespace(iter_content=lambda _: iter([received[:3], received[3:]])))
    target = tmp_path / "original"
    if received == b"original":
        client.original(descriptor, target)
        assert target.read_bytes() == received
    else:
        with pytest.raises(ManagerError, match="integrity_failure") as error:
            client.original(descriptor, target)
        assert error.value.permanent


@pytest.mark.parametrize("fault", ["lost_ack", "conflict", "unavailable"])
def test_artifact_write_reconciles_remote_ack_and_verifies_bytes(monkeypatch, tmp_path, fault):
    import hashlib

    import requests

    from knowledge_flow_backend.features.manager_processing.artifacts import Artifacts
    from knowledge_flow_backend.features.manager_processing.client import ManagerError
    from knowledge_flow_backend.features.manager_processing.contracts import Artifact

    source = tmp_path / "output.md"
    source.write_bytes(b"original")
    artifact = Artifact(path="output.md", size=8, sha256=hashlib.sha256(b"original").hexdigest())
    stored = []
    released = []

    class Response:
        status_code = 412 if fault == "conflict" else 503

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def put(*args, **kwargs):
        assert kwargs["headers"]["If-None-Match"] == "*"
        if fault == "lost_ack":
            raise requests.ConnectionError("lost response")
        return Response()

    def get(*_):
        stored.append(True)
        return SimpleNamespace(stream=lambda _: iter([b"original"]), close=lambda: released.append("close"), release_conn=lambda: released.append("release"))

    service = Artifacts.__new__(Artifacts)
    service.bucket = "derived"
    service.client = SimpleNamespace(presigned_put_object=lambda *args, **kwargs: "https://fixture.invalid", get_object=get)
    monkeypatch.setattr(requests, "put", put)
    if fault == "unavailable":
        with pytest.raises(ManagerError):
            service.put("generation/", source, artifact)
        assert not stored
    else:
        service.put("generation/", source, artifact)
        assert released == ["close", "release"]
        artifact.sha256 = "0" * 64
        with pytest.raises(ManagerError, match="integrity_failure"):
            service.put("generation/", source, artifact)


def test_manager_http_transient_failure_is_retryable_and_refreshes_auth():
    from knowledge_flow_backend.features.manager_processing.client import ManagerClient, ManagerError

    client = ManagerClient.__new__(ManagerClient)
    client.url = "https://manager.invalid"
    refreshed = []

    class Tokens:
        def __call__(self):
            return "fixture"

        def force_refresh(self):
            refreshed.append(True)

    client.tokens = Tokens()
    closed = []
    status = iter([503, 401, 200])
    client.session = SimpleNamespace(request=lambda *args, **kwargs: SimpleNamespace(status_code=next(status), close=lambda: closed.append(True)))
    for code in ("worker_failed", "access_changed"):
        with pytest.raises(ManagerError, match=code) as error:
            client.request("GET", "/document-processing/fixture/work")
        assert not error.value.permanent
    assert client.request("GET", "/document-processing/fixture/work").status_code == 200
    assert closed == [True, True] and refreshed == [True]


@pytest.mark.parametrize("kind, field", [("opensearch", "index"), ("pgvector", "collection_name"), ("chroma", "collection_name"), ("clickhouse", "table")])
def test_configuration_refuses_shared_vector_and_content_namespaces(kind, field):
    from knowledge_flow_backend.common.structures import Configuration, MinioFilesystemConfig, MinioStorageConfig

    legacy = SimpleNamespace(type=kind, **{field: "legacy"})
    manager = SimpleNamespace(enabled=True, vector_store=SimpleNamespace(type=kind, **{field: "derived"}), bucket="derived")
    content = MinioStorageConfig(type="minio", endpoint="localhost:9000", access_key="fixture", secret_key="fixture", bucket_name="legacy")
    filesystem = MinioFilesystemConfig(endpoint="localhost:9000", access_key="fixture", secret_key="fixture", bucket_name="legacy-files")
    config = Configuration.model_construct(storage=SimpleNamespace(vector_store=legacy), manager_processing=manager, content_storage=content, filesystem=filesystem)
    assert config.isolate_manager_processing() is config
    setattr(manager.vector_store, field, "legacy")
    with pytest.raises(ValueError, match="vector namespaces must differ"):
        config.isolate_manager_processing()
    setattr(manager.vector_store, field, "derived")
    manager.bucket = "legacy-documents"
    assert config.isolate_manager_processing() is config
    for bucket in ("legacy", "legacy-objects"):
        manager.bucket = bucket
        with pytest.raises(ValueError, match="content buckets must differ"):
            config.isolate_manager_processing()
    manager.bucket = "legacy-files"
    with pytest.raises(ValueError, match="filesystem buckets must differ"):
        config.isolate_manager_processing()


def test_legacy_listing_preview_expiry_and_clear_do_not_touch_derived_bucket(monkeypatch):
    import asyncio

    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.core.stores.content.minio_content_store import MinioStorageBackend
    from knowledge_flow_backend.features.scheduler.pdf_render_expiry_activities import expire_pdf_renders

    key = "legacy-document/output/render.pdf"
    derived = "manager/document/attempt/generation/native.pdf"
    buckets = {"legacy": {key: b"legacy"}, "objects": {}, "derived": {derived: b"manager"}}
    calls = []

    def objects(bucket, **_):
        calls.append(bucket)
        return [SimpleNamespace(object_name=name, size=len(body), last_modified=datetime.now(timezone.utc) - timedelta(days=90), etag="fixture") for name, body in buckets[bucket].items()]

    def get(bucket, name):
        calls.append(bucket)
        return SimpleNamespace(read=lambda: buckets[bucket][name], close=lambda: None, release_conn=lambda: None)

    def remove(bucket, name):
        calls.append(bucket)
        buckets[bucket].pop(name, None)

    store = MinioStorageBackend.__new__(MinioStorageBackend)
    store.document_bucket = "legacy"
    store.object_bucket = "objects"
    store.buckets = {"legacy", "objects"}
    store.client = SimpleNamespace(list_objects=objects, get_object=get, remove_object=remove)
    context = SimpleNamespace(get_config=lambda: SimpleNamespace(app=SimpleNamespace(pdf_render_ttl_days=30)), get_content_store=lambda: store)
    monkeypatch.setattr(ApplicationContext, "get_instance", lambda: context)
    assert store.list_document_uids(strict=True) == ["legacy-document"]
    assert store.get_output_artifact(key) == b"legacy"
    assert asyncio.run(expire_pdf_renders())["expired"] == 1
    store.clear()
    assert buckets["legacy"] == {}
    assert buckets["derived"] == {derived: b"manager"}
    assert "derived" not in calls
