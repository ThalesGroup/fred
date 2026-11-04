# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Immutable generation-scoped objects, shared by execution and cleanup."""

import hashlib
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import requests
from fred_knowledge.artifacts.reader import ArtifactReader, safe_path

from knowledge_flow_worker.features.manager_processing.client import ManagerClient, ManagerError
from knowledge_flow_worker.features.manager_processing.contracts import Artifact, Descriptor, Manifest, WriteReceipt


def describe(path: Path, name: str) -> Artifact:
    if not safe_path(name) or path.is_symlink() or not path.is_file():
        raise ManagerError("integrity_failure", permanent=True)
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return Artifact(path=name, size=path.stat().st_size, sha256=digest)


def adopt_output(descriptor: Descriptor, directory: Path, source: Path, name: str) -> Path:
    """Move an activity-owned intermediate without a second full copy."""
    if not safe_path(name) or source.is_symlink() or not source.is_file():
        raise ManagerError("integrity_failure", permanent=True)
    target = directory / name
    total = source.stat().st_size
    count = 1
    for path in directory.rglob("*"):
        if path.is_file() and path != source and path != target:
            total += path.stat().st_size
            count += 1
        if total > descriptor.max_output_bytes or count > descriptor.max_artifacts:
            raise ManagerError("capacity_exceeded", permanent=True)
    if total > descriptor.max_output_bytes:
        raise ManagerError("capacity_exceeded", permanent=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)
    return target


class Artifacts(ArtifactReader):
    def __init__(self, settings):
        super().__init__(settings)
        self.settings = settings

    @contextmanager
    def writing(self, descriptor: Descriptor):
        """Only the thread that observes a terminal remote response acknowledges.

        Never acknowledge in finally: cancellation, timeout and process loss leave
        durable uncertainty, even if a subsequent GET sees the requested bytes.
        """
        receipt = WriteReceipt(work=descriptor.work, generation=descriptor.generation, write_id=uuid4(), completed=False)
        path = f"/document-processing/{descriptor.work.processing_id}/writes"
        with ManagerClient(self.settings) as client:
            client.post(path, receipt)
            yield
            client.post(path, receipt.model_copy(update={"completed": True}))

    def put(self, descriptor: Descriptor, path: Path, artifact: Artifact):
        url = self.client.presigned_put_object(self.bucket, descriptor.output_prefix + artifact.path, expires=timedelta(minutes=5))
        with path.open("rb") as body, self.writing(descriptor):
            with requests.put(url, data=body, headers={"If-None-Match": "*", "Content-Type": "application/octet-stream"}, timeout=(5, 30), allow_redirects=False) as response:
                status = response.status_code
                if status >= 500:
                    raise ManagerError("write_outcome_unknown")
        if status not in (200, 201, 412):
            raise ManagerError("worker_failed")
        self.read(descriptor.output_prefix, artifact)

    def read(self, prefix: str, artifact: Artifact, destination: Path | None = None):
        if destination is None:
            self.read_verified(prefix, artifact)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as output:
                self.read_verified(prefix, artifact, output)

    def publish(self, descriptor: Descriptor, directory: Path, *, chunks: int = 0, vectors: int = 0, rows: int | None = None) -> Manifest:
        files = sorted(path for path in directory.rglob("*") if path.is_file() or path.is_symlink())
        if len(files) > descriptor.max_artifacts:
            raise ManagerError("capacity_exceeded", permanent=True)
        artifacts = [describe(path, path.relative_to(directory).as_posix()) for path in files]
        if sum(a.size for a in artifacts) > descriptor.max_output_bytes:
            raise ManagerError("capacity_exceeded", permanent=True)
        for artifact in artifacts:
            self.put(descriptor, directory / artifact.path, artifact)
        return Manifest(generation=descriptor.generation, artifacts=artifacts, chunks=chunks, vectors=vectors, rows=rows)

    def restore(self, descriptor: Descriptor, directory: Path):
        predecessor = descriptor.predecessor
        if predecessor is None:
            raise ManagerError("integrity_failure", permanent=True)
        for artifact in predecessor.manifest.artifacts:
            self.read(predecessor.prefix, artifact, directory / artifact.path)
