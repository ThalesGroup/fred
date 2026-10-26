# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Child-process execution using the existing extractors, splitter and output processors."""

from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from uuid import uuid5

from langchain_core.documents import Document
from pydantic_core import to_json

from knowledge_flow_backend.features.manager_processing.artifacts import Artifacts, adopt_output
from knowledge_flow_backend.features.manager_processing.client import ManagerError
from knowledge_flow_backend.features.manager_processing.contracts import Descriptor


def _placement(descriptor: Descriptor) -> dict[str, str]:
    """Placement is immutable in Control Plane SQL, so values written here stay true."""
    return {
        "organization_id": str(descriptor.organization_id),
        "space_id": str(descriptor.space_id),
        "folder_path": descriptor.folder_path,
    }


class ScopedVectors:
    """Journal bounded deterministic IDs before writes, including adaptive retry splits."""

    def __init__(self, underlying, descriptor: Descriptor, artifacts: Artifacts, directory: Path, splitter):
        self.underlying = underlying
        self.descriptor = descriptor
        self.artifacts = artifacts
        self.directory = directory
        self.splitter = splitter
        self.count = 0
        self.ordinals = []
        self.aliases = {}
        self.documents = {}
        self.bytes = 0
        self.started = False

    def before_write(self, documents, ids):
        from knowledge_flow_backend.application_context import ApplicationContext
        from knowledge_flow_backend.features.manager_processing.client import ManagerClient
        from knowledge_flow_backend.features.manager_processing.contracts import VectorPlan

        d = self.descriptor
        placement = _placement(d)
        previous = len(self.documents)
        identifiers = []
        for document, logical_id in zip(documents, ids, strict=True):
            # Descriptor placement wins over extractor metadata of the same name.
            document.metadata.update(placement)
            if logical_id not in self.aliases:
                ordinal = len(self.documents)
                if ordinal >= d.max_chunks:
                    raise ManagerError("capacity_exceeded", permanent=True)
                identifier = str(uuid5(d.generation, str(ordinal)))
                self.aliases[logical_id] = ordinal
                self.aliases[identifier] = ordinal
                document.metadata.update(
                    document_uid=str(d.work.document_id),
                    chunk_uid=identifier,
                )
                self.bytes += len(to_json({"text": document.page_content, "metadata": document.metadata}))
                if self.bytes > d.max_output_bytes:
                    raise ManagerError("capacity_exceeded", permanent=True)
                self.documents[ordinal] = document
            ordinal = self.aliases[logical_id]
            identifier = str(uuid5(d.generation, str(ordinal)))
            document.metadata["chunk_uid"] = identifier
            identifiers.append(identifier)
        if len(self.documents) != previous:
            settings = ApplicationContext.get_instance().configuration.manager_processing
            if settings is None or not settings.enabled:
                raise ManagerError("worker_failed", permanent=True)
            with ManagerClient(settings) as client:
                client.post(f"/document-processing/{d.work.processing_id}/vectors", VectorPlan(work=d.work, generation=d.generation, count=len(self.documents)))
        return identifiers

    def add_documents(self, documents: list[Document], ids=None):
        from knowledge_flow_backend.core.stores.vector.base_vector_store import vector_write_observer

        if self.started or not documents:
            raise ManagerError("capacity_exceeded", permanent=True)
        self.started = True
        identifiers = self.before_write(documents, [str(i) for i in range(len(documents))])
        token = vector_write_observer.set(self)
        try:
            written = self.underlying.add_documents(documents, ids=identifiers)
        finally:
            vector_write_observer.reset(token)
        d = self.descriptor
        placement = _placement(d)
        records = []
        ordinals = []
        for identifier in written:
            ordinal = self.aliases[identifier]
            document = self.documents[ordinal]
            stored = self.underlying.get_chunk(str(d.work.document_id), identifier)
            metadata = stored.get("metadata", {})
            if (
                metadata.get("retrievable") is not True
                or stored.get("text") != document.page_content
                or metadata.get("document_uid") != str(d.work.document_id)
                or metadata.get("chunk_uid") != identifier
                or any(metadata.get(key) != value for key, value in placement.items())
            ):
                raise ManagerError("indexing_failed")
            records.append(to_json({"id": identifier, "text": document.page_content, "metadata": document.metadata}).decode("utf-8"))
            ordinals.append(ordinal)
        (self.directory / "chunks.jsonl").write_text("\n".join(records) + "\n")
        self.ordinals = sorted(set(ordinals))
        self.count = len(self.ordinals)
        return written

    def delete_vectors_for_document(self, *, document_uid: str):
        for ordinal in self.documents:
            self.underlying.delete_chunk(document_uid, str(uuid5(self.descriptor.generation, str(ordinal))))


class LocalTabularArtifacts:
    """TabularProcessor writes only inside this attempt; publication owns remote persistence."""

    def __init__(self, directory: Path, descriptor: Descriptor, temporary_bytes: int):
        self.temporary_bytes = temporary_bytes
        self.directory = directory
        self.descriptor = descriptor
        self.temporary_directory = directory.parent / "scratch"
        self.temporary_directory.mkdir(exist_ok=True)

    def check_workspace(self):
        total = count = 0
        for path in self.directory.parent.rglob("*"):
            count += 1
            try:
                total += path.stat().st_size if path.is_file() else 0
            except FileNotFoundError:
                continue
            if total > self.temporary_bytes or count > self.descriptor.max_artifacts * 2:
                raise ManagerError("capacity_exceeded", permanent=True)

    @contextmanager
    def watch_conversion(self, connection):
        # DuckDB owns this connection; interrupt its COPY before runaway scratch exhausts the pod.
        self.check_workspace()
        stopped = Event()
        errors = []

        def watch():
            while not stopped.wait(0.05):
                try:
                    self.check_workspace()
                except Exception as error:
                    errors.append(error)
                    connection.interrupt()
                    return

        monitor = Thread(target=watch, name="manager-parquet-capacity", daemon=True)
        monitor.start()
        try:
            yield
        finally:
            stopped.set()
            monitor.join()
            if errors:
                raise errors[0]
            self.check_workspace()

    def put_file(self, key: str, file_path: Path, *, content_type: str):
        import hashlib

        from knowledge_flow_backend.core.stores.content.base_content_store import StoredObjectInfo

        name = "datasets/" + hashlib.sha256(key.encode()).hexdigest() + ".parquet"
        target = adopt_output(self.descriptor, self.directory, file_path, name)
        return StoredObjectInfo(key=name, size=target.stat().st_size, file_name=target.name, content_type=content_type)


def scoped_pipeline(context, descriptor: Descriptor, output: Path, artifacts: Artifacts, *, include_output: bool):
    """Instance-local dependencies; configured processor selection remains in the shared pipeline."""
    import copy

    from knowledge_flow_backend.common.structures import ProcessingConfig
    from knowledge_flow_backend.core.processing_pipeline_manager import ProcessingPipelineManager
    from knowledge_flow_backend.core.processors.input.excel_processor.excel_processor import ExcelProcessor

    scoped = copy.copy(context)
    scoped.configuration = context.configuration.model_copy(deep=True)
    profile = ProcessingConfig.ProfileConfig.model_validate_json((output / "policy.json").read_text())
    setattr(scoped.configuration.processing.profiles, descriptor.work.profile, profile)
    scoped.input_processor_registry = scoped._load_input_processor_registry()
    scoped._input_processor_instances = {}
    scoped._output_processor_instances = {}
    scoped._inject_processor_context = True
    scoped.configuration.library_output_processors = []
    settings = scoped.configuration.manager_processing
    if settings is None:
        raise ManagerError("worker_failed", permanent=True)
    scoped._content_store_instance = LocalTabularArtifacts(output, descriptor, settings.temporary_bytes)
    vectors = None
    if include_output:
        underlying = context.get_manager_vector_store()
        vectors = ScopedVectors(underlying, descriptor, artifacts, output, scoped.get_text_splitter())
        scoped._vector_store_instance = vectors
    pipeline = ProcessingPipelineManager.create_with_default(scoped, include_output=include_output)
    for item in pipeline.pipelines.values():
        for processor in item.input_processors.values():
            if isinstance(processor, ExcelProcessor):
                processor.put_file_override = scoped._content_store_instance.put_file
    return pipeline, vectors
