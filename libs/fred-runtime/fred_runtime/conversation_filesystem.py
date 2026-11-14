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

"""Conversation-bound files stored in Fred Runtime's shared filesystem."""

from __future__ import annotations

import asyncio
import logging
import string
import threading
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_sdk.contracts.runtime import (
    ConversationScratchpadEditConflictError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadInvalidPathError,
    ConversationScratchpadQuotaExceededError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)

if TYPE_CHECKING:
    from fred_core.kpi import BaseKPIWriter

    from fred_runtime.runtime_support.session_fence import SessionFence

_SAFE_SESSION_ID_FIRST_CHARACTERS = frozenset(string.ascii_letters + string.digits)
_SAFE_SESSION_ID_CHARACTERS = _SAFE_SESSION_ID_FIRST_CHARACTERS | frozenset("._:@+-")
_LOGGER = logging.getLogger(__name__)
_LOCK_REGISTRY_GUARD = threading.Lock()
_FILESYSTEM_WRITES: set[asyncio.Task[Any]] = set()
_LOCKS_BY_FILESYSTEM: weakref.WeakKeyDictionary[object, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)


async def _run_filesystem_operation[T](
    operation: Callable[[], Awaitable[T]],
    *,
    lock: asyncio.Lock | None = None,
) -> T:
    # Waiting callers remain cancellable. Once admitted, the task owns the lock
    # until the real operation ends, even if its caller disconnects.
    if lock is not None:
        await lock.acquire()

    async def persist() -> T:
        try:
            return await operation()
        finally:
            if lock is not None:
                lock.release()

    # Keep the task alive after caller cancellation. A to_thread SDK operation or
    # converter must really finish before its intent can be acknowledged.
    task = asyncio.create_task(persist())
    _FILESYSTEM_WRITES.add(task)
    task.add_done_callback(_finish_filesystem_write)
    return await asyncio.shield(task)


async def _record_filesystem_write[T](
    session_id: str,
    fence: SessionFence | None,
    operation: Callable[[], Awaitable[T]],
) -> T:
    # Called inside a protected operation, after validation. A failure leaves
    # the intent pending: an uncertain object write cannot be acknowledged.
    token = await fence.begin_filesystem_write(session_id) if fence else None
    result = await operation()
    if token is not None and fence is not None:
        await fence.end_filesystem_write(token)
    return result


class ConversationFilesystemQuotaSettings(Protocol):
    @property
    def scratchpad_max_bytes(self) -> int:
        raise NotImplementedError

    @property
    def scratchpad_max_files(self) -> int:
        raise NotImplementedError

    @property
    def deep_max_bytes(self) -> int:
        raise NotImplementedError

    @property
    def deep_max_files(self) -> int:
        raise NotImplementedError


class _ConversationFilesystemStorage(Protocol):
    async def read(self, path: str) -> bytes:
        raise NotImplementedError

    async def write(self, path: str, data: bytes | str) -> None:
        raise NotImplementedError

    async def list(self, prefix: str = "") -> list[FilesystemResourceInfoResult]:
        raise NotImplementedError

    async def delete(self, path: str) -> None:
        raise NotImplementedError

    async def mkdir(self, path: str) -> None:
        raise NotImplementedError

    async def exists(self, path: str) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ConversationTextFileMetadata:
    """Stable runtime metadata for one file in a conversation namespace."""

    path: str
    size: int
    modified: datetime | None = None


class ConversationTextNamespacePort(Protocol):
    """Runtime-only view that also exposes object-list metadata."""

    async def read_bytes(self, path: str) -> bytes:
        raise NotImplementedError

    async def read_text(self, path: str) -> str:
        raise NotImplementedError

    async def write_text(self, path: str, content: str) -> None:
        raise NotImplementedError

    async def write_bytes(self, path: str, content: bytes) -> None:
        raise NotImplementedError

    async def edit_text(
        self, path: str, old_text: str, new_text: str, *, replace_all: bool = False
    ) -> int:
        raise NotImplementedError

    async def list(self, path: str = "") -> tuple[str, ...]:
        raise NotImplementedError

    async def exists(self, path: str) -> bool:
        raise NotImplementedError

    async def delete(self, path: str) -> None:
        raise NotImplementedError

    async def list_metadata(
        self, path: str = ""
    ) -> tuple[ConversationTextFileMetadata, ...]:
        raise NotImplementedError

    async def purge(self) -> None:
        """Remove the complete trusted runtime namespace."""
        raise NotImplementedError


@dataclass(frozen=True)
class _DefaultQuotas:
    scratchpad_max_bytes: int = 100 * 1024 * 1024
    scratchpad_max_files: int = 1_000
    deep_max_bytes: int = 1024 * 1024 * 1024
    deep_max_files: int = 10_000


@dataclass(frozen=True)
class _NamespaceQuota:
    max_bytes: int
    max_files: int


_DEFAULT_QUOTAS = _DefaultQuotas()


class ConversationFilesystemService:
    """Bind one pod-wide object filesystem to one trusted conversation id.

    Each mutation observes durable storage without retaining accounting state.
    Local mutations are serialized through actual completion, but these soft
    limits provide no cross-replica reservation; overlapping writes may overshoot.
    """

    def __init__(
        self,
        filesystem: _ConversationFilesystemStorage,
        session_id: str,
        *,
        quotas: ConversationFilesystemQuotaSettings = _DEFAULT_QUOTAS,
        kpi: BaseKPIWriter | None = None,
        fence: SessionFence | None = None,
    ) -> None:
        # PostgreSQL UUID ownership treats case, compact and braced forms as
        # one identity. Physical keys must use that same identity for every
        # read, write and purge. Standalone non-UUID SDK sessions stay valid.
        if isinstance(session_id, str):
            try:
                session_id = str(UUID(session_id))
            except ValueError:
                pass
        if not _is_safe_session_id(session_id):
            raise ConversationScratchpadInvalidPathError(
                "Conversation identifier must be one safe path segment"
            )
        self._filesystem = filesystem
        self._session_id = session_id
        self._quotas = quotas
        self._kpi = kpi
        self._fence = fence

    @property
    def session_id(self) -> str:
        """Canonical identity used by physical paths and published artifact URLs."""
        return self._session_id

    def scratchpad(self) -> ConversationTextNamespacePort:
        """Return the trusted physical default namespace for runtime maintenance."""
        return self.namespace(
            "scratchpad",
            max_bytes=self._quotas.scratchpad_max_bytes,
            max_files=self._quotas.scratchpad_max_files,
        )

    def namespace(
        self, namespace_id: str, *, max_bytes: int, max_files: int
    ) -> ConversationTextNamespacePort:
        """Bind an explicit quota to a safe physical namespace."""
        return _ConversationTextNamespace(
            self._filesystem,
            self._session_id,
            namespace_id,
            quota=_NamespaceQuota(max_bytes, max_files),
            kpi=self._kpi,
            fence=self._fence,
        )

    async def convert_office_to_pdf(
        self, content: bytes, *, suffix: str
    ) -> bytes | None:
        from fred_core.conversion.office_pdf import convert_office_bytes_to_pdf

        async def convert() -> bytes | None:
            return await convert_office_bytes_to_pdf(
                content, suffix=suffix, strict_cleanup=True
            )

        return await _run_filesystem_operation(
            lambda: _record_filesystem_write(self._session_id, self._fence, convert)
        )

    @property
    def quotas(self) -> ConversationFilesystemQuotaSettings:
        return self._quotas

    async def purge(self) -> None:
        """Erase every namespace after the durable fence has closed its writers."""
        try:
            await self._filesystem.delete(f"conversations/{self._session_id}")
        except FileNotFoundError:
            pass

    async def purge_namespace(self, namespace_id: str) -> None:
        await self.namespace(namespace_id, max_bytes=0, max_files=0).purge()


class _ConversationTextNamespace:
    def __init__(
        self,
        filesystem: _ConversationFilesystemStorage,
        session_id: str,
        namespace: str,
        *,
        quota: _NamespaceQuota,
        kpi: BaseKPIWriter | None,
        fence: SessionFence | None,
    ) -> None:
        if not _is_safe_namespace_id(namespace):
            raise ConversationScratchpadInvalidPathError(
                "Namespace identifier must be one safe path segment"
            )
        self._filesystem = filesystem
        self._fence = fence
        self._conversation_id = session_id
        self._namespace = namespace
        self._prefix = f"conversations/{session_id}/{namespace}/"
        self._quota = quota
        self._kpi = kpi
        self._lock = _namespace_lock(filesystem, self._prefix)

    async def read_text(self, path: str) -> str:
        relative_path = _normalize_path(path)
        return await self._read_text(relative_path)

    async def read_bytes(self, path: str) -> bytes:
        relative_path = _normalize_path(path)
        try:
            return await self._filesystem.read(self._physical_path(relative_path))
        except FileNotFoundError as exc:
            raise ConversationScratchpadFileNotFoundError(
                "Scratchpad file does not exist"
            ) from exc
        except Exception as exc:
            raise self._storage_error("read", exc) from exc

    async def _read_text(self, relative_path: str) -> str:
        content = await self.read_bytes(relative_path)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConversationScratchpadUnsupportedContentError(
                "Scratchpad supports UTF-8 text only"
            ) from exc

    async def write_text(self, path: str, content: str) -> None:
        await self.write_bytes(path, _encode_text(content))

    async def write_bytes(self, path: str, content: bytes) -> None:
        encoded = content
        relative_path = _normalize_path(path)

        async def write() -> None:
            sizes = await self._recount()
            self._check_write_quota(sizes, relative_path, len(encoded))
            await self._write_encoded(relative_path, encoded, operation="write")
            sizes[relative_path] = len(encoded)
            self._emit_usage(sizes)

        await _run_filesystem_operation(write, lock=self._lock)

    async def _write_encoded(
        self, relative_path: str, encoded: bytes, *, operation: str
    ) -> None:
        physical_path = self._physical_path(relative_path)

        async def persist() -> None:
            await self._filesystem.mkdir(str(PurePosixPath(physical_path).parent))
            await self._filesystem.write(physical_path, encoded)

        try:
            await _record_filesystem_write(self._conversation_id, self._fence, persist)
        except Exception as exc:
            raise self._storage_error(operation, exc) from exc

    async def edit_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
        *,
        replace_all: bool = False,
    ) -> int:
        relative_path = _normalize_path(path)
        _encode_text(old_text)
        _encode_text(new_text)  # validation precedes any storage operation

        async def edit() -> int:
            sizes = await self._recount()
            current = await self._read_text(relative_path)
            match_count = current.count(old_text)
            if match_count == 0 or (match_count > 1 and not replace_all):
                raise ConversationScratchpadEditConflictError(
                    "Expected text does not uniquely match the latest scratchpad content"
                )
            updated = current.replace(old_text, new_text, -1 if replace_all else 1)
            encoded = _encode_text(updated)
            self._check_write_quota(sizes, relative_path, len(encoded))
            await self._write_encoded(relative_path, encoded, operation="edit")
            sizes[relative_path] = len(encoded)
            self._emit_usage(sizes)
            return match_count

        return await _run_filesystem_operation(edit, lock=self._lock)

    async def list(self, path: str = "") -> tuple[str, ...]:
        return tuple(metadata.path for metadata in await self.list_metadata(path))

    async def list_metadata(
        self, path: str = ""
    ) -> tuple[ConversationTextFileMetadata, ...]:
        relative_path = _normalize_path(path, allow_root=True)
        physical_prefix = self._prefix
        if relative_path:
            physical_prefix += f"{relative_path}/"
        try:
            entries = await self._filesystem.list(physical_prefix)
            metadata = []
            for entry in entries:
                if (
                    entry.type != FilesystemResourceInfo.FILE
                    or not entry.path.startswith(self._prefix)
                    or entry.path == physical_prefix.rstrip("/")
                ):
                    continue
                if entry.size is None:
                    raise ValueError("Filesystem listing omitted file size")
                metadata.append(
                    ConversationTextFileMetadata(
                        path=entry.path.removeprefix(self._prefix),
                        size=entry.size,
                        modified=entry.modified,
                    )
                )
        except Exception as exc:
            raise self._storage_error("list", exc) from exc
        return tuple(sorted(metadata, key=lambda entry: entry.path))

    async def exists(self, path: str) -> bool:
        relative_path = _normalize_path(path)
        try:
            return await self._filesystem.exists(self._physical_path(relative_path))
        except Exception as exc:
            raise self._storage_error("exists", exc) from exc

    async def delete(self, path: str) -> None:
        relative_path = _normalize_path(path)

        async def remove() -> None:
            sizes = await self._recount()
            try:
                await self._filesystem.delete(self._physical_path(relative_path))
            except FileNotFoundError:
                pass
            except Exception as exc:
                raise self._storage_error("delete", exc) from exc
            prefix = f"{relative_path}/"
            self._emit_usage(
                {
                    candidate: size
                    for candidate, size in sizes.items()
                    if candidate != relative_path and not candidate.startswith(prefix)
                }
            )

        await _run_filesystem_operation(remove, lock=self._lock)

    async def purge(self) -> None:
        """Idempotently remove this entire code-owned namespace."""

        async def remove() -> None:
            try:
                await self._filesystem.delete(self._prefix.rstrip("/"))
            except FileNotFoundError:
                pass
            except Exception as exc:
                raise self._storage_error("purge", exc) from exc
            self._emit_usage({})

        await _run_filesystem_operation(remove, lock=self._lock)

    def _physical_path(self, relative_path: str) -> str:
        return f"{self._prefix}{relative_path}"

    async def _recount(self) -> dict[str, int]:
        try:
            entries = await self._filesystem.list(self._prefix)
            sizes: dict[str, int] = {}
            for entry in entries:
                if (
                    entry.type != FilesystemResourceInfo.FILE
                    or not entry.path.startswith(self._prefix)
                ):
                    continue
                size = entry.size
                if size is None:
                    size = len(await self._filesystem.read(entry.path))
                sizes[entry.path.removeprefix(self._prefix)] = size
        except Exception as exc:
            raise self._storage_error("recount", exc) from exc
        self._emit_usage(sizes)
        return sizes

    def _check_write_quota(
        self, sizes: dict[str, int], relative_path: str, new_size: int
    ) -> None:
        old_size = sizes.get(relative_path)
        attempted_files = len(sizes) + (old_size is None)
        attempted_bytes = sum(sizes.values()) - (old_size or 0) + new_size
        if attempted_files > self._quota.max_files:
            self._reject_quota("files", self._quota.max_files, attempted_files)
        if attempted_bytes > self._quota.max_bytes:
            self._reject_quota("bytes", self._quota.max_bytes, attempted_bytes)

    def _reject_quota(self, resource: str, limit: int, attempted: int) -> None:
        _LOGGER.warning(
            "Conversation filesystem quota rejected mutation",
            extra={
                "conversation_filesystem": {
                    "conversation_id": self._conversation_id,
                    "namespace": self._namespace,
                    "resource": resource,
                    "limit": limit,
                    "attempted": attempted,
                }
            },
        )
        if self._kpi is not None:
            try:
                self._kpi.count(
                    "conversation.filesystem.quota_rejected_total",
                    dims={
                        "conversation_fs_namespace": self._namespace,
                        "conversation_fs_resource": resource,
                    },
                    actor=KPIActor(type="system"),
                )
            except Exception:
                _LOGGER.exception("Conversation filesystem quota KPI emission failed")
        raise ConversationScratchpadQuotaExceededError(
            resource=resource,
            limit=limit,
            attempted=attempted,
        )

    def _emit_usage(self, sizes: dict[str, int]) -> None:
        _LOGGER.info(
            "Conversation filesystem namespace usage",
            extra={
                "conversation_filesystem": {
                    "conversation_id": self._conversation_id,
                    "namespace": self._namespace,
                    "usage_bytes": sum(sizes.values()),
                    "usage_files": len(sizes),
                }
            },
        )

    def _storage_error(
        self, operation: str, error: Exception
    ) -> ConversationScratchpadStorageError:
        _LOGGER.warning(
            "Conversation filesystem storage operation failed",
            extra={
                "conversation_filesystem": {
                    "conversation_id": self._conversation_id,
                    "operation": operation,
                    "namespace": self._namespace,
                    "error_category": type(error).__name__,
                }
            },
        )
        return ConversationScratchpadStorageError("Shared scratchpad storage failed")


def _normalize_path(path: str, *, allow_root: bool = False) -> str:
    # Python callers can bypass the str annotation; retain runtime validation.
    if not isinstance(path, str):
        raise ConversationScratchpadInvalidPathError(  # pyright: ignore[reportUnreachable]
            "Scratchpad path must be relative POSIX text"
        )
    if path == "" and allow_root:
        return ""
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or any(ord(character) < 32 for character in path)
    ):
        raise ConversationScratchpadInvalidPathError(
            "Scratchpad path must be a non-empty relative POSIX path"
        )
    segments = path.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ConversationScratchpadInvalidPathError(
            "Scratchpad path contains an unsafe segment"
        )
    return str(PurePosixPath(*segments))


def _encode_text(content: str) -> bytes:
    # Python callers can bypass the str annotation; retain runtime validation.
    if not isinstance(content, str):
        raise ConversationScratchpadUnsupportedContentError(  # pyright: ignore[reportUnreachable]
            "Scratchpad supports UTF-8 text only"
        )
    try:
        return content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ConversationScratchpadUnsupportedContentError(
            "Scratchpad supports UTF-8 text only"
        ) from exc


def _is_safe_session_id(session_id: str) -> bool:
    return (
        isinstance(session_id, str)
        and session_id not in {"", ".", ".."}
        and session_id[0] in _SAFE_SESSION_ID_FIRST_CHARACTERS
        and all(character in _SAFE_SESSION_ID_CHARACTERS for character in session_id)
    )


def _is_safe_namespace_id(namespace: str) -> bool:
    return (
        isinstance(namespace, str)
        and namespace not in {"", ".", ".."}
        and all(character in _SAFE_SESSION_ID_CHARACTERS for character in namespace)
    )


def _namespace_lock(
    filesystem: _ConversationFilesystemStorage, prefix: str
) -> asyncio.Lock:
    with _LOCK_REGISTRY_GUARD:
        locks = _LOCKS_BY_FILESYSTEM.setdefault(filesystem, {})
        return locks.setdefault(prefix, asyncio.Lock())


def _finish_filesystem_write(task: asyncio.Task[Any]) -> None:
    _FILESYSTEM_WRITES.discard(task)
    if not task.cancelled():
        task.exception()  # Observe failures even when the caller disconnected.
