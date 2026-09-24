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

from __future__ import annotations

import secrets
import threading
from pathlib import Path

import pytest
from fred_core.filesystem.gcs_filesystem import GcsFilesystem
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.filesystem.minio_filesystem import MinioFilesystem
from fred_runtime.app import AgentPodConfig, build_runtime_filesystem
from fred_runtime.app.config import (
    GcsRuntimeFilesystemConfig,
    MinioRuntimeFilesystemConfig,
)
from fred_runtime.app.context import PodApplicationContext
from pydantic import ValidationError


def _config(filesystem: dict[str, object]) -> AgentPodConfig:
    return AgentPodConfig.model_validate(
        {
            "app": {"runtime_id": "test-pod"},
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost/realms/fred",
                    "client_id": "test-m2m",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost/realms/fred",
                    "client_id": "test-user",
                },
            },
            "storage": {"object_store": filesystem},
        }
    )


def test_conversation_filesystem_quotas_use_code_defaults() -> None:
    quotas = _config({"type": "local"}).storage.conversation_filesystem

    assert quotas.scratchpad_max_bytes == 100 * 1024 * 1024
    assert quotas.scratchpad_max_files == 1_000
    assert quotas.deep_max_bytes == 1024 * 1024 * 1024
    assert quotas.deep_max_files == 10_000


def test_minio_runtime_filesystem_reads_secret_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("MINIO_SECRET_KEY", secret)

    config = MinioRuntimeFilesystemConfig.model_validate(
        {
            "type": "minio",
            "endpoint": "http://localhost:8333",
            "access_key": "runtime",
            "bucket_name": "fred-runtime-conversations",
        }
    )

    assert config.secret_key == secret


def test_runtime_object_store_uses_shared_default_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINIO_SECRET_KEY", secrets.token_urlsafe(32))
    minio = _config(
        {"type": "minio", "endpoint": "http://localhost:8333", "access_key": "runtime"}
    ).storage.object_store
    gcs = GcsRuntimeFilesystemConfig()

    assert isinstance(minio, MinioRuntimeFilesystemConfig)
    assert minio.bucket_name == "fred-runtime"
    assert gcs.bucket_name == "fred-runtime"


def test_legacy_filesystem_key_fails_instead_of_falling_back_to_local() -> None:
    config = _config({"type": "local"})
    values = config.model_dump()
    values["storage"]["filesystem"] = values["storage"].pop("object_store")

    with pytest.raises(ValidationError, match="storage.filesystem was renamed"):
        AgentPodConfig.model_validate(values)


def test_minio_runtime_filesystem_requires_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="Missing MINIO_SECRET_KEY"):
        MinioRuntimeFilesystemConfig.model_validate(
            {
                "type": "minio",
                "endpoint": "http://localhost:8333",
                "access_key": "runtime",
                "bucket_name": "fred-runtime-conversations",
            }
        )


def test_conversation_filesystem_quotas_allow_partial_and_complete_overrides() -> None:
    partial = _config({"type": "local"}).model_copy(
        update={
            "storage": _config({"type": "local"}).storage.model_copy(
                update={
                    "conversation_filesystem": {
                        "scratchpad_max_files": 7,
                    }
                }
            )
        }
    )
    # Validate through the public configuration boundary, rather than relying
    # on model_copy's deliberately non-validating update semantics.
    partial = AgentPodConfig.model_validate(partial.model_dump())
    complete = AgentPodConfig.model_validate(
        {
            **_config({"type": "local"}).model_dump(),
            "storage": {
                **_config({"type": "local"}).storage.model_dump(),
                "conversation_filesystem": {
                    "scratchpad_max_bytes": 11,
                    "scratchpad_max_files": 12,
                    "deep_max_bytes": 13,
                    "deep_max_files": 14,
                },
            },
        }
    )

    assert partial.storage.conversation_filesystem.scratchpad_max_files == 7
    assert (
        partial.storage.conversation_filesystem.scratchpad_max_bytes
        == 100 * 1024 * 1024
    )
    assert partial.storage.conversation_filesystem.deep_max_bytes == 1024 * 1024 * 1024
    assert partial.storage.conversation_filesystem.deep_max_files == 10_000
    assert complete.storage.conversation_filesystem.model_dump() == {
        "scratchpad_max_bytes": 11,
        "scratchpad_max_files": 12,
        "deep_max_bytes": 13,
        "deep_max_files": 14,
    }


@pytest.mark.asyncio
async def test_local_runtime_filesystem_round_trips_text(tmp_path: Path) -> None:
    filesystem = await build_runtime_filesystem(
        _config({"type": "local", "root": str(tmp_path)}).storage.object_store
    )

    assert isinstance(filesystem, LocalFilesystem)
    await filesystem.write("note.txt", "hello")
    assert await filesystem.cat("note.txt") == "hello"


@pytest.mark.asyncio
async def test_local_runtime_filesystem_initializes_outside_event_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fred_runtime.app import filesystem_factory

    event_loop_thread = threading.get_ident()
    local_filesystem = filesystem_factory.LocalFilesystem

    def _build(*, root: str) -> LocalFilesystem:
        assert threading.get_ident() != event_loop_thread
        return local_filesystem(root=root)

    monkeypatch.setattr(filesystem_factory, "LocalFilesystem", _build)

    filesystem = await build_runtime_filesystem(
        _config({"type": "local", "root": str(tmp_path)}).storage.object_store
    )

    assert isinstance(filesystem, LocalFilesystem)


@pytest.mark.asyncio
async def test_minio_runtime_filesystem_uses_configured_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_core.filesystem import minio_filesystem

    class _Client:
        def bucket_exists(self, bucket_name: str) -> bool:
            assert bucket_name == "runtime-files"
            return True

    monkeypatch.setattr(minio_filesystem, "Minio", lambda *args, **kwargs: _Client())

    filesystem = await build_runtime_filesystem(
        _config(
            {
                "type": "minio",
                "endpoint": "http://minio:9000",
                "access_key": "developer",
                "secret_key": "generated-test-secret",
                "bucket_name": "runtime-files",
            }
        ).storage.object_store
    )

    assert isinstance(filesystem, MinioFilesystem)
    assert filesystem.bucket_name == "runtime-files"
    assert filesystem.prefix is None


@pytest.mark.asyncio
async def test_gcs_runtime_filesystem_uses_workload_identity_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_core.filesystem import gcs_filesystem

    class _Client:
        def bucket(self, name: str) -> object:
            assert name == "runtime-files"
            return object()

    monkeypatch.setattr(
        gcs_filesystem, "build_gcs_client", lambda project_id=None: _Client()
    )

    filesystem = await build_runtime_filesystem(
        _config(
            {
                "type": "gcs",
                "bucket_name": "runtime-files",
                "project_id": "fred-dev",
            }
        ).storage.object_store
    )

    assert isinstance(filesystem, GcsFilesystem)
    assert filesystem.bucket_name == "runtime-files"
    assert filesystem.base_prefix == ""


@pytest.mark.asyncio
async def test_pod_context_keeps_one_filesystem_instance(tmp_path: Path) -> None:
    context = PodApplicationContext(_config({"type": "local", "root": str(tmp_path)}))

    await context.initialize_filesystem()

    assert context.get_filesystem() is context.get_filesystem()
    assert isinstance(context.get_filesystem(), LocalFilesystem)
