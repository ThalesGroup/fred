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

"""Construct the pod-wide object filesystem selected by runtime config."""

from __future__ import annotations

import asyncio

from fred_core.filesystem.gcs_filesystem import GcsFilesystem
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.filesystem.minio_filesystem import MinioFilesystem
from fred_core.filesystem.structures import BaseFilesystem

from .config import (
    GcsRuntimeFilesystemConfig,
    LocalRuntimeFilesystemConfig,
    MinioRuntimeFilesystemConfig,
    RuntimeFilesystemConfig,
)


async def build_runtime_filesystem(
    config: RuntimeFilesystemConfig,
) -> BaseFilesystem:
    """Build one filesystem without blocking startup's event loop on cloud SDKs."""
    if isinstance(config, LocalRuntimeFilesystemConfig):
        return await asyncio.to_thread(LocalFilesystem, root=config.root)
    if isinstance(config, MinioRuntimeFilesystemConfig):
        return await asyncio.to_thread(
            MinioFilesystem,
            endpoint=config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            bucket_name=config.bucket_name,
            secure=config.secure,
        )
    if isinstance(config, GcsRuntimeFilesystemConfig):
        return await asyncio.to_thread(
            GcsFilesystem,
            bucket_name=config.bucket_name,
            project_id=config.project_id,
        )
    raise TypeError(f"Unsupported runtime filesystem config: {type(config).__name__}")
