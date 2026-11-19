# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Dedicated, deadline-aware private trace object I/O."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from contextvars import ContextVar
from io import BytesIO
from time import monotonic
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

import anyio
import certifi
from fred_core.common.gcs_client import build_gcs_client
from google.auth.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request
from google.cloud.exceptions import NotFound
from google.cloud.storage.blob import Blob
from minio import Minio
from minio.datatypes import Object
from minio.deleteobjects import DeleteObject
from minio.error import S3Error
from urllib3 import PoolManager, Timeout
from urllib3.response import BaseHTTPResponse

from fred_runtime.app.config import (
    GcsRuntimeFilesystemConfig,
    MinioRuntimeFilesystemConfig,
)

# Two publishers, eight inspector reads and one maintenance slot per pod.
_STORAGE_WORKERS = 11
_CONNECT_TIMEOUT = 1.0
_READ_TIMEOUT = 2.0
_DEFAULT_OPERATION_SECONDS = 5.0
_MAX_OBJECT_BYTES = 2 * 1024 * 1024
# The GCS SDK supports retry=None, though some releases infer a non-null type.
_GCS_NO_RETRY: dict[str, Any] = {"retry": None}
_T = TypeVar("_T")
storage_deadline: ContextVar[float | None] = ContextVar(
    "trace_object_deadline", default=None
)


def _remaining() -> float:
    deadline = storage_deadline.get()
    assert deadline is not None
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("trace object deadline exceeded")
    return remaining


def _timeouts() -> tuple[float, float]:
    remaining = _remaining()
    return min(remaining, _CONNECT_TIMEOUT), min(remaining, _READ_TIMEOUT)


class _TraceS3Pool(PoolManager):
    def urlopen(
        self, method: str, url: str, redirect: bool = True, **kwargs: Any
    ) -> BaseHTTPResponse:
        connect, read = _timeouts()
        return super().urlopen(
            method,
            url,
            redirect=False,
            **{
                **kwargs,
                "timeout": Timeout(total=_remaining(), connect=connect, read=read),
                "pool_timeout": _remaining(),
                "retries": False,
            },
        )


class _TraceGcsAuthRequest(Request):
    def __call__(
        self,
        url: str,
        method: str = "GET",
        body=None,
        headers=None,
        timeout=120,
        **kwargs: Any,
    ):
        return super().__call__(
            url, method, body, headers, **{**kwargs, "timeout": _timeouts()}
        )


class _TraceGcsSession(AuthorizedSession):
    def __init__(self, credentials: Credentials) -> None:
        self._auth_transport = _TraceGcsAuthRequest()
        super().__init__(
            credentials,
            auth_request=self._auth_transport,
            max_refresh_attempts=0,
        )
        self.configure_mtls_channel()

    def request(
        self,
        method,
        url,
        data=None,
        headers=None,
        max_allowed_time=None,
        timeout=120,
        **kwargs: Any,
    ):
        # Disable redirects and SDK retries; all GCS calls share the same absolute budget.
        return super().request(
            method,
            url,
            data,
            headers,
            **{
                **kwargs,
                "allow_redirects": False,
                "max_allowed_time": _remaining(),
                "timeout": _timeouts(),
            },
        )

    def close(self) -> None:
        self._auth_transport.session.close()
        super().close()


class _TraceObjects(Protocol):
    def read(self, path: str) -> bytes: ...
    def write(self, path: str, data: bytes) -> None: ...
    def erase(self, path: str) -> None: ...
    def measure(self, path: str) -> int: ...
    def close(self) -> None: ...


class _S3Objects:
    def __init__(self, config: MinioRuntimeFilesystemConfig) -> None:
        self._pool = _TraceS3Pool(
            maxsize=_STORAGE_WORKERS,
            block=True,
            cert_reqs="CERT_REQUIRED",
            ca_certs=os.environ.get("SSL_CERT_FILE") or certifi.where(),
        )
        parsed = urlparse(config.endpoint)
        endpoint = parsed.netloc or config.endpoint
        self._client = Minio(
            endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.secure,
            http_client=self._pool,
        )
        self._bucket = config.bucket_name

    def read(self, path: str) -> bytes:
        try:
            response = self._client.get_object(self._bucket, path)
            try:
                body = bytearray()
                while True:
                    _remaining()
                    chunk = response.read1(
                        min(64 * 1024, _MAX_OBJECT_BYTES + 1 - len(body)),
                        decode_content=False,
                    )
                    if not chunk:
                        return bytes(body)
                    body.extend(chunk)
                    if len(body) > _MAX_OBJECT_BYTES:
                        raise ValueError("Oversized trace object")
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise FileNotFoundError("Trace object unavailable") from exc
            raise

    def write(self, path: str, data: bytes) -> None:
        self._client.put_object(self._bucket, path, BytesIO(data), len(data))

    def _list(self, path: str) -> Iterator[Object]:
        return self._client.list_objects(
            self._bucket, prefix=f"{path}/", recursive=True
        )

    def erase(self, path: str) -> None:
        keys = (
            DeleteObject(obj.object_name)
            for obj in self._list(path)
            if obj.object_name is not None
        )
        if any(self._client.remove_objects(self._bucket, keys)):
            raise RuntimeError("Failed to erase trace objects")
        self._client.remove_object(self._bucket, path)

    def measure(self, path: str) -> int:
        return sum(
            obj.size or 0
            for obj in self._list(path)
            if obj.object_name and not obj.object_name.endswith("/")
        )

    def close(self) -> None:
        self._pool.clear()


class _GcsObjects:
    def __init__(self, config: GcsRuntimeFilesystemConfig) -> None:
        self._client = build_gcs_client(
            config.project_id, session_factory=_TraceGcsSession
        )
        self._bucket = self._client.bucket(config.bucket_name)

    def read(self, path: str) -> bytes:
        try:
            data = self._bucket.blob(path).download_as_bytes(
                end=_MAX_OBJECT_BYTES,
                raw_download=True,
                **_GCS_NO_RETRY,
            )
        except NotFound as exc:
            raise FileNotFoundError("Trace object unavailable") from exc
        if len(data) > _MAX_OBJECT_BYTES:
            raise ValueError("Oversized trace object")
        return data

    def write(self, path: str, data: bytes) -> None:
        self._bucket.blob(path).upload_from_string(
            data,
            content_type="application/octet-stream",
            **_GCS_NO_RETRY,
        )

    def _list(self, path: str) -> Iterator[Blob]:
        return iter(
            self._client.list_blobs(self._bucket, prefix=f"{path}/", **_GCS_NO_RETRY)
        )

    def erase(self, path: str) -> None:
        for blob in self._list(path):
            with suppress(NotFound):
                blob.delete(**_GCS_NO_RETRY)
        with suppress(NotFound):
            self._bucket.blob(path).delete(**_GCS_NO_RETRY)

    def measure(self, path: str) -> int:
        return sum(
            blob.size or 0
            for blob in self._list(path)
            if blob.name and not blob.name.endswith("/")
        )

    def close(self) -> None:
        self._client.close()


class TraceObjectIO:
    """Hold capacity until the synchronous SDK call actually ends."""

    def __init__(self, backend: _TraceObjects) -> None:
        self._backend = backend
        self._slots = asyncio.Semaphore(_STORAGE_WORKERS)
        self._pool = ThreadPoolExecutor(
            max_workers=_STORAGE_WORKERS, thread_name_prefix="fred-trace-io"
        )
        self._inflight: set[asyncio.Future[Any]] = set()
        self._closed = False

    @classmethod
    async def build(
        cls, config: MinioRuntimeFilesystemConfig | GcsRuntimeFilesystemConfig
    ) -> TraceObjectIO:
        if isinstance(config, MinioRuntimeFilesystemConfig):
            return cls(await asyncio.to_thread(_S3Objects, config))
        return cls(await asyncio.to_thread(_GcsObjects, config))

    async def read(self, path: str) -> bytes:
        return await self._run(self._backend.read, path)

    async def write(self, path: str, data: bytes) -> None:
        await self._run(self._backend.write, path, data)

    async def mkdir(self, path: str) -> None:
        # Cloud keys have implicit directories; neither client needs marker PUTs.
        return None

    async def erase(self, path: str) -> None:
        await self._run(self._backend.erase, path)

    async def measure(self, path: str) -> int:
        return await self._run(self._backend.measure, path)

    async def _run(self, call: Callable[..., _T], *args: object) -> _T:
        deadline = storage_deadline.get() or monotonic() + _DEFAULT_OPERATION_SECONDS
        async with asyncio.timeout(max(0, deadline - monotonic())):
            await self._slots.acquire()
        try:
            if self._closed or deadline <= monotonic():
                raise TimeoutError("trace object deadline exceeded")

            def run() -> _T:
                token = storage_deadline.set(deadline)
                try:
                    _remaining()
                    return call(*args)
                finally:
                    storage_deadline.reset(token)

            future = asyncio.get_running_loop().run_in_executor(self._pool, run)
        except BaseException:
            self._slots.release()
            raise
        self._inflight.add(future)
        future.add_done_callback(self._settled)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # The worker owns its slot even if the caller is canceled again.
            with anyio.CancelScope(shield=True), suppress(Exception):
                await asyncio.shield(future)
            raise

    def _settled(self, future: asyncio.Future[Any]) -> None:
        self._inflight.discard(future)
        self._slots.release()
        if not future.cancelled():
            future.exception()

    async def close(self) -> None:
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
        if not self._inflight:
            self._backend.close()
            return
        _, pending = await asyncio.wait(self._inflight, timeout=2)
        if not pending:
            self._backend.close()
            return

        # Leave socket ownership with this backend until the last issued call ends.
        def finish(future: asyncio.Future[Any]) -> None:
            pending.discard(future)
            if not pending:
                self._backend.close()

        for future in pending:
            future.add_done_callback(finish)
