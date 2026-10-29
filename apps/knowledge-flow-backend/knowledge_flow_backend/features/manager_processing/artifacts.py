# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Immutable generation-scoped objects, shared by execution and cleanup."""

import hashlib
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests
import urllib3
from minio import Minio

from knowledge_flow_backend.common.structures import ManagerProcessingConfig
from knowledge_flow_backend.features.manager_processing.client import ManagerError
from knowledge_flow_backend.features.manager_processing.contracts import Artifact, Descriptor, Manifest


def safe_path(path: str) -> bool:
    return 0 < len(path.encode("utf-8")) <= 255 and all(c.isalnum() or c in "-_. /" for c in path) and all(part not in ("", ".", "..") for part in path.split("/"))


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


class Artifacts:
    def __init__(self, config: ManagerProcessingConfig):
        endpoint = urlsplit(config.endpoint)
        self.bucket = config.bucket
        self.client = Minio(
            endpoint.netloc,
            access_key=os.environ[config.access_key_env],
            secret_key=os.environ[config.secret_key_env],
            secure=endpoint.scheme == "https",
            region=config.region,
            http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=30), retries=False),
        )

    def put(self, prefix: str, path: Path, artifact: Artifact):
        # A retried write can only confirm identical bytes, never overwrite a published object.
        url = self.client.presigned_put_object(self.bucket, prefix + artifact.path, expires=timedelta(minutes=5))
        try:
            with path.open("rb") as body, requests.put(url, data=body, headers={"If-None-Match": "*", "Content-Type": "application/octet-stream"}, timeout=(5, 30), allow_redirects=False) as response:
                if response.status_code not in (200, 201, 412):
                    raise ManagerError("worker_failed")
        except requests.RequestException:
            # The acknowledgment can be lost after S3 accepted the object.
            pass
        self.read(prefix, artifact)

    def read(self, prefix: str, artifact: Artifact, destination: Path | None = None):
        if not safe_path(artifact.path):
            raise ManagerError("integrity_failure", permanent=True)
        response = self.client.get_object(self.bucket, prefix + artifact.path)
        output = None
        try:
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                output = destination.open("xb")
            total = 0
            digest = hashlib.sha256()
            for chunk in response.stream(64 * 1024):
                total += len(chunk)
                if total > artifact.size:
                    raise ManagerError("integrity_failure", permanent=True)
                digest.update(chunk)
                if output:
                    output.write(chunk)
            if total != artifact.size or digest.hexdigest() != artifact.sha256:
                raise ManagerError("integrity_failure", permanent=True)
        finally:
            if output:
                output.close()
            response.close()
            response.release_conn()

    def publish(self, descriptor: Descriptor, directory: Path, *, chunks: int = 0, vectors: int = 0, rows: int | None = None) -> Manifest:
        files = sorted(path for path in directory.rglob("*") if path.is_file() or path.is_symlink())
        if len(files) > descriptor.max_artifacts:
            raise ManagerError("capacity_exceeded", permanent=True)
        artifacts = [describe(path, path.relative_to(directory).as_posix()) for path in files]
        if sum(a.size for a in artifacts) > descriptor.max_output_bytes:
            raise ManagerError("capacity_exceeded", permanent=True)
        for artifact in artifacts:
            self.put(descriptor.output_prefix, directory / artifact.path, artifact)
        return Manifest(generation=descriptor.generation, artifacts=artifacts, chunks=chunks, vectors=vectors, rows=rows)

    def restore(self, descriptor: Descriptor, directory: Path):
        predecessor = descriptor.predecessor
        if predecessor is None:
            raise ManagerError("integrity_failure", permanent=True)
        for artifact in predecessor.manifest.artifacts:
            self.read(predecessor.prefix, artifact, directory / artifact.path)
