# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded authenticated worker calls. Responses and credentials never enter history."""

import hashlib
import json
import os
from pathlib import Path

import requests
from fred_core.security.outbound import ClientCredentialsProvider

from knowledge_flow_backend.common.structures import ManagerProcessingConfig
from knowledge_flow_backend.features.manager_processing.contracts import Contract, Descriptor


class ManagerError(RuntimeError):
    def __init__(self, code: str, *, permanent: bool = False):
        super().__init__(code)
        self.code = code
        self.permanent = permanent


def raise_permanent_failure(error: BaseException | None):
    from temporalio.exceptions import ApplicationError

    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ManagerError) and error.permanent:
            raise ApplicationError(error.code, type="ManagerProcessingError", non_retryable=True) from error
        error = error.__cause__ or error.__context__


class ManagerClient:
    def __init__(self, config: ManagerProcessingConfig):
        self.url = config.url.rstrip("/")
        self.tokens = ClientCredentialsProvider(
            keycloak_base="",
            realm="",
            token_url=f"{config.issuer.rstrip('/')}/protocol/openid-connect/token",
            client_id=config.client_id,
            client_secret=os.environ[config.client_secret_env],
            audience=config.audience,
        )
        self.session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def request(self, method: str, path: str, *, body: Contract | None = None, stream: bool = True):
        try:
            headers = {"Authorization": f"Bearer {self.tokens()}"}
            response = self.session.request(method, self.url + path, json=body.model_dump(mode="json") if body else None, headers=headers, stream=stream, timeout=(5, 30), allow_redirects=False)
        except Exception:
            raise ManagerError("worker_failed") from None
        if response.status_code == 401:
            self.tokens.force_refresh()
        if response.status_code >= 300:
            response.close()
            raise ManagerError("access_changed" if response.status_code in (401, 403) else "worker_failed", permanent=response.status_code in (403, 404, 409, 422))
        return response

    @staticmethod
    def decode(response):
        blocks = []
        size = 0
        for block in response.iter_content(65536):
            size += len(block)
            if size > 2_097_152:
                raise ManagerError("capacity_exceeded", permanent=True)
            blocks.append(block)
        return json.loads(b"".join(blocks)) if size else {}

    def get(self, path):
        with self.request("GET", path) as response:
            return self.decode(response)

    def post(self, path: str, body: Contract) -> dict:
        with self.request("POST", path, body=body) as response:
            return self.decode(response)

    def original(self, descriptor: Descriptor, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        digest = hashlib.sha256()
        with self.request("GET", f"/document-processing/{descriptor.work.processing_id}/original?generation={descriptor.generation}", stream=True) as response, path.open("xb") as output:
            for chunk in response.iter_content(64 * 1024):
                total += len(chunk)
                if total > descriptor.size:
                    raise ManagerError("integrity_failure", permanent=True)
                digest.update(chunk)
                output.write(chunk)
        if total != descriptor.size or digest.hexdigest() != descriptor.work.original_sha256:
            raise ManagerError("integrity_failure", permanent=True)
