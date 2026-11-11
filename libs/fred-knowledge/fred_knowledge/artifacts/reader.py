# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import hashlib
import os
from io import BytesIO
from typing import BinaryIO
from urllib.parse import urlsplit

import urllib3
from fred_core.common.platform_failure import object_storage_failure
from minio import Minio

from fred_knowledge.artifacts.contracts import Artifact
from fred_knowledge.artifacts.errors import ManagerError
from fred_knowledge.configuration import ArtifactStorageConfig


def safe_path(path: str) -> bool:
    return 0 < len(path.encode("utf-8")) <= 255 and all(c.isalnum() or c in "-_. /" for c in path) and all(part not in ("", ".", "..") for part in path.split("/"))


class ArtifactReader:
    def __init__(self, config: ArtifactStorageConfig):
        endpoint = urlsplit(config.endpoint)
        self.bucket = config.bucket
        self._access_key_setting = config.access_key_env
        self._secret_key_setting = config.secret_key_env
        self.client = Minio(
            endpoint.netloc,
            access_key=os.environ[config.access_key_env],
            secret_key=os.environ[config.secret_key_env],
            secure=endpoint.scheme == "https",
            region=config.region,
            http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=30), retries=False),
        )

    def read_verified(self, prefix: str, artifact: Artifact, output: BinaryIO | None = None) -> None:
        if not safe_path(artifact.path):
            raise ManagerError("integrity_failure", permanent=True)
        try:
            response = self.client.get_object(self.bucket, prefix + artifact.path)
            try:
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
                response.close()
                response.release_conn()
        except Exception as error:
            # This client read the keys, so it alone knows which setting supplied them.
            failure = object_storage_failure(error, access_key_setting=self._access_key_setting, secret_key_setting=self._secret_key_setting)
            if failure is None:
                raise
            raise failure from error

    def read_bytes(self, prefix: str, artifact: Artifact) -> bytes:
        with BytesIO() as output:
            self.read_verified(prefix, artifact, output)
            return output.getvalue()
