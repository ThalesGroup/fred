# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Confine the pod's object store to one capability's own namespace."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from fred_core.filesystem.structures import BaseFilesystem

from fred_runtime.capabilities.registry import CapabilityRegistry

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ScopedCapabilityObjects:
    """`CapabilityObjects`: no key can leave ``capabilities/<id>/``, and the bucket
    can neither be listed nor reached under a conversation's or another capability's key."""

    def __init__(self, filesystem: BaseFilesystem, capability_id: str) -> None:
        self._filesystem = filesystem
        self._root = f"capabilities/{capability_id}"

    def _key(self, path: str) -> str:
        if not all(_SEGMENT.fullmatch(segment) for segment in path.split("/")):
            raise ValueError("Invalid capability object path")
        return f"{self._root}/{path}"

    async def check(self) -> None:
        await self._filesystem.exists(self._root)

    async def read(self, path: str) -> bytes:
        return await self._filesystem.read(self._key(path))

    async def write(self, path: str, data: bytes) -> None:
        key = self._key(path)
        await self._filesystem.mkdir(str(PurePosixPath(key).parent))
        await self._filesystem.write(key, data)

    async def delete(self, path: str) -> None:
        await self._filesystem.delete(self._key(path))


def bind_capability_objects(
    registry: CapabilityRegistry, filesystem: BaseFilesystem
) -> None:
    """Give every installed capability its namespace, once, at process startup."""
    for capability_id in registry.ids():
        registry.capability(capability_id).bind_objects(
            ScopedCapabilityObjects(filesystem, capability_id)
        )
