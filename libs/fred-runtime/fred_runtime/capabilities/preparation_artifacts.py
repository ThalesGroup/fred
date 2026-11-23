# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Read published, current preparation artifacts from the runtime object store."""

from __future__ import annotations

from collections.abc import Mapping

from fred_core.filesystem.structures import BaseFilesystem


class BoundPreparationArtifacts:
    def __init__(
        self,
        filesystem: BaseFilesystem,
        references: Mapping[str, str],
        settings: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self._filesystem = filesystem
        self._references = dict(references)
        self._settings = {key: dict(value) for key, value in (settings or {}).items()}

    def has_result(self, capability_id: str) -> bool:
        return capability_id in self._references

    def settings(self, capability_id: str) -> Mapping[str, object]:
        return self._settings.get(capability_id, {})

    async def read_result(self, capability_id: str) -> bytes | None:
        reference = self._references.get(capability_id)
        if reference is None:
            return None
        self._check_reference(reference)
        return await self._filesystem.read(reference)

    async def read_sibling(self, capability_id: str, filename: str) -> bytes | None:
        reference = self._references.get(capability_id)
        if reference is None:
            return None
        self._check_reference(reference)
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or filename in (".", "..")
        ):
            raise ValueError("Invalid preparation artifact filename")
        path = reference.rpartition("/")[0] + "/" + filename
        return await self._filesystem.read(path)

    @staticmethod
    def _check_reference(reference: str) -> None:
        parts = reference.split("/")
        if (
            len(parts) < 4
            or parts[0] != "capability-results"
            or any(not part or part in (".", "..") for part in parts)
        ):
            raise ValueError("Invalid preparation result reference")
