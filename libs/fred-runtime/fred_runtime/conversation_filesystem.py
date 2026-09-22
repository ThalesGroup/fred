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

"""Conversation-bound text files stored in Fred Runtime's shared filesystem."""

from __future__ import annotations

import asyncio
import logging
import string
import threading
import weakref
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Literal, Protocol

from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_sdk.contracts.runtime import (
    ConversationScratchpadEditConflictError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadInvalidPathError,
    ConversationScratchpadPort,
    ConversationScratchpadQuotaExceededError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)

if TYPE_CHECKING:
    from fred_core.kpi import BaseKPIWriter

ConversationFilesystemNamespace = Literal["scratchpad", ".deep"]

_SAFE_SESSION_ID_FIRST_CHARACTERS = frozenset(string.ascii_letters + string.digits)
_SAFE_SESSION_ID_CHARACTERS = _SAFE_SESSION_ID_FIRST_CHARACTERS | frozenset("._:@+-")
_LOGGER = logging.getLogger(__name__)
_LOCK_REGISTRY_GUARD = threading.Lock()
_STATES_BY_FILESYSTEM: weakref.WeakKeyDictionary[
    object, dict[str, _NamespaceAccounting]
] = weakref.WeakKeyDictionary()


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


class ConversationTextNamespacePort(ConversationScratchpadPort):
    """Runtime-only view that also exposes object-list metadata."""

    @abstractmethod
    async def list_metadata(
        self, path: str = ""
    ) -> tuple[ConversationTextFileMetadata, ...]:
        raise NotImplementedError

    @abstractmethod
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


@dataclass
class _NamespaceAccounting:
    lock: asyncio.Lock
    sizes: dict[str, int] | None = None


_DEFAULT_QUOTAS = _DefaultQuotas()


class ConversationFilesystemService:
    """Bind one pod-wide object filesystem to one trusted conversation id.

    Quota accounting is serialized and shared inside this process. It recounts
    durable storage before the first mutation, but intentionally provides no
    cross-replica transaction; concurrent replicas may briefly overshoot.
    """

    def __init__(
        self,
        filesystem: _ConversationFilesystemStorage,
        session_id: str,
        *,
        quotas: ConversationFilesystemQuotaSettings = _DEFAULT_QUOTAS,
        kpi: BaseKPIWriter | None = None,
    ) -> None:
        if not _is_safe_session_id(session_id):
            raise ConversationScratchpadInvalidPathError(
                "Conversation identifier must be one safe path segment"
            )
        self._filesystem = filesystem
        self._session_id = session_id
        self._quotas = quotas
        self._kpi = kpi

    def scratchpad(self) -> ConversationScratchpadPort:
        """Return the capability-safe view, with no namespace selector exposed."""
        return self.namespace("scratchpad")

    def namespace(
        self, namespace: ConversationFilesystemNamespace
    ) -> ConversationTextNamespacePort:
        """Return a trusted runtime view for one code-owned namespace."""
        if namespace == "scratchpad":
            quota = _NamespaceQuota(
                self._quotas.scratchpad_max_bytes,
                self._quotas.scratchpad_max_files,
            )
        else:
            quota = _NamespaceQuota(
                self._quotas.deep_max_bytes,
                self._quotas.deep_max_files,
            )
        return _ConversationTextNamespace(
            self._filesystem,
            self._session_id,
            namespace,
            quota=quota,
            kpi=self._kpi,
        )


class _ConversationTextNamespace(ConversationTextNamespacePort):
    def __init__(
        self,
        filesystem: _ConversationFilesystemStorage,
        session_id: str,
        namespace: ConversationFilesystemNamespace,
        *,
        quota: _NamespaceQuota,
        kpi: BaseKPIWriter | None,
    ) -> None:
        self._filesystem = filesystem
        self._conversation_id = session_id
        self._namespace = namespace
        self._prefix = f"conversations/{session_id}/{namespace}/"
        self._quota = quota
        self._kpi = kpi
        self._accounting = _namespace_accounting(filesystem, self._prefix)
        self._lock = self._accounting.lock

    async def read_text(self, path: str) -> str:
        relative_path = _normalize_path(path)
        return await self._read_text(relative_path)

    async def _read_text(self, relative_path: str) -> str:
        try:
            content = await self._filesystem.read(self._physical_path(relative_path))
        except FileNotFoundError as exc:
            raise ConversationScratchpadFileNotFoundError(
                "Scratchpad file does not exist"
            ) from exc
        except Exception as exc:
            raise self._storage_error("read", exc) from exc
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConversationScratchpadUnsupportedContentError(
                "Scratchpad supports UTF-8 text only"
            ) from exc

    async def write_text(self, path: str, content: str) -> None:
        relative_path = _normalize_path(path)
        encoded = _encode_text(content)
        async with self._lock:
            await self._ensure_accounting()
            self._check_write_quota(relative_path, len(encoded))
            await self._write_encoded(relative_path, encoded, operation="write")
            assert self._accounting.sizes is not None
            self._accounting.sizes[relative_path] = len(encoded)
            self._emit_usage()

    async def _write_encoded(
        self, relative_path: str, encoded: bytes, *, operation: str
    ) -> None:
        physical_path = self._physical_path(relative_path)
        try:
            await self._filesystem.mkdir(str(PurePosixPath(physical_path).parent))
            await self._filesystem.write(physical_path, encoded)
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
        async with self._lock:
            await self._ensure_accounting()
            current = await self._read_text(relative_path)
            match_count = current.count(old_text)
            if match_count == 0 or (match_count > 1 and not replace_all):
                raise ConversationScratchpadEditConflictError(
                    "Expected text does not uniquely match the latest scratchpad content"
                )
            updated = current.replace(old_text, new_text, -1 if replace_all else 1)
            encoded = _encode_text(updated)
            self._check_write_quota(relative_path, len(encoded))
            await self._write_encoded(relative_path, encoded, operation="edit")
            assert self._accounting.sizes is not None
            self._accounting.sizes[relative_path] = len(encoded)
            self._emit_usage()
            return match_count

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
        async with self._lock:
            await self._ensure_accounting()
            try:
                await self._filesystem.delete(self._physical_path(relative_path))
            except FileNotFoundError:
                self._forget_path(relative_path)
                return
            except Exception as exc:
                raise self._storage_error("delete", exc) from exc
            self._forget_path(relative_path)

    async def purge(self) -> None:
        """Idempotently remove this entire code-owned namespace."""
        async with self._lock:
            try:
                await self._filesystem.delete(self._prefix.rstrip("/"))
            except FileNotFoundError:
                self._accounting.sizes = {}
                self._emit_usage()
                return
            except Exception as exc:
                raise self._storage_error("purge", exc) from exc
            self._accounting.sizes = {}
            self._emit_usage()

    def _physical_path(self, relative_path: str) -> str:
        return f"{self._prefix}{relative_path}"

    def _forget_path(self, relative_path: str) -> None:
        assert self._accounting.sizes is not None
        prefix = f"{relative_path.rstrip('/')}/"
        self._accounting.sizes = {
            candidate: size
            for candidate, size in self._accounting.sizes.items()
            if candidate != relative_path and not candidate.startswith(prefix)
        }
        self._emit_usage()

    async def _ensure_accounting(self) -> None:
        if self._accounting.sizes is not None:
            return
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
        self._accounting.sizes = sizes
        self._emit_usage()

    def _check_write_quota(self, relative_path: str, new_size: int) -> None:
        assert self._accounting.sizes is not None
        old_size = self._accounting.sizes.get(relative_path)
        attempted_files = len(self._accounting.sizes) + (old_size is None)
        attempted_bytes = (
            sum(self._accounting.sizes.values()) - (old_size or 0) + new_size
        )
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

    def _emit_usage(self) -> None:
        if self._accounting.sizes is None:
            return
        _LOGGER.info(
            "Conversation filesystem namespace usage",
            extra={
                "conversation_filesystem": {
                    "conversation_id": self._conversation_id,
                    "namespace": self._namespace,
                    "usage_bytes": sum(self._accounting.sizes.values()),
                    "usage_files": len(self._accounting.sizes),
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
    if not isinstance(path, str):
        raise ConversationScratchpadInvalidPathError(
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
    if (
        any(segment in {"", ".", ".."} for segment in segments)
        or segments[0] == ".deep"
    ):
        raise ConversationScratchpadInvalidPathError(
            "Scratchpad path contains an unsafe segment"
        )
    return str(PurePosixPath(*segments))


def _encode_text(content: str) -> bytes:
    if not isinstance(content, str):
        raise ConversationScratchpadUnsupportedContentError(
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


def _namespace_accounting(
    filesystem: _ConversationFilesystemStorage, prefix: str
) -> _NamespaceAccounting:
    with _LOCK_REGISTRY_GUARD:
        states = _STATES_BY_FILESYSTEM.setdefault(filesystem, {})
        return states.setdefault(prefix, _NamespaceAccounting(lock=asyncio.Lock()))
