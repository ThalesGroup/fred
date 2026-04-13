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

import pytest
from fred_core import M2MSecurity, SecurityConfiguration, UserSecurity
from fred_core.common import DuckdbStoreConfig, ModelConfiguration, PostgresStoreConfig, TemporalSchedulerConfig
from pydantic import AnyHttpUrl, AnyUrl

from knowledge_flow_backend.common.structures import (
    AppConfig,
    Configuration,
    InMemoryVectorStorage,
    LocalContentStorageConfig,
    LocalFilesystemConfig,
    SchedulerConfig,
    StorageConfig,
)


def _build_minimal_configuration(*, storage: StorageConfig) -> Configuration:
    """
    Build one minimal Knowledge Flow configuration for tabular config tests.

    Why this exists:
    - Tabular configuration validation needs a compact but valid
      `Configuration` payload around the storage section.

    How to use:
    - Pass a prepared `StorageConfig`.
    - Override the dumped payload in individual tests when exercising rejected
      old shapes.
    """

    return Configuration(
        app=AppConfig(),
        security=SecurityConfiguration(
            m2m=M2MSecurity(
                enabled=False,
                realm_url=AnyUrl("http://localhost:8080/realms/test-m2m"),
                client_id="m2m-client",
                audience="test-audience",
            ),
            user=UserSecurity(
                enabled=False,
                realm_url=AnyUrl("http://localhost:8080/realms/test-user"),
                client_id="user-client",
            ),
            authorized_origins=[AnyHttpUrl("http://localhost:5173")],
            rebac=None,
        ),
        scheduler=SchedulerConfig(
            enabled=False,
            temporal=TemporalSchedulerConfig(
                host="localhost:7233",
                namespace="default",
                task_queue="ingestion",
                workflow_id_prefix="test",
                connect_timeout_seconds=5,
            ),
        ),
        storage=storage,
        content_storage=LocalContentStorageConfig(type="local", root_path="/tmp/test-content"),
        chat_model=ModelConfiguration(provider="openai", name="gpt-4o", settings={}),
        embedding_model=ModelConfiguration(provider="openai", name="text-embedding-3-large", settings={}),
        filesystem=LocalFilesystemConfig(type="local", root="/tmp/test-fs"),
    )


def _build_minimal_storage(tmp_path) -> StorageConfig:
    """
    Build one minimal storage configuration for tabular tests.

    Why this exists:
    - Tests in this module share the same baseline stores and only vary the
      tabular section.

    How to use:
    - Pass the per-test `tmp_path`.
    - Mutate the dumped payload in the caller when needed.
    """

    return StorageConfig(
        postgres=PostgresStoreConfig(host="localhost", database="fred"),
        resource_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "resource.duckdb")),
        tag_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "tag.duckdb")),
        kpi_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "kpi.duckdb")),
        metadata_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "metadata.duckdb")),
        vector_store=InMemoryVectorStorage(type="in_memory"),
    )


def test_configuration_defaults_to_dataset_tabular_store(tmp_path):
    """
    Ensure the tabular runtime remains available by default.

    Why this exists:
    - New deployments should not need to repeat the default tabular block just
      to enable Parquet artifact storage.

    How to use:
    - Build a minimal configuration without overriding `storage.tabular_store`
      and assert the default values are present.
    """

    config = _build_minimal_configuration(storage=_build_minimal_storage(tmp_path))

    assert config.storage.tabular_store.artifacts_prefix == "tabular/datasets"
    assert config.storage.tabular_store.format == "parquet"
    assert config.storage.tabular_store.query.engine == "duckdb"


def test_configuration_rejects_removed_storage_tabular_stores_field(tmp_path):
    """
    Ensure the removed `storage.tabular_stores` field is rejected.

    Why this exists:
    - Removed configuration keys should fail loudly instead of being silently
      ignored.

    How to use:
    - Dump a valid payload, inject `storage.tabular_stores`, and assert
      validation fails.
    """

    payload = _build_minimal_configuration(storage=_build_minimal_storage(tmp_path)).model_dump(mode="python")
    payload["storage"]["tabular_stores"] = {"base_database": {"type": "sql"}}

    with pytest.raises(ValueError, match="'storage.tabular_stores' is no longer supported"):
        Configuration.model_validate(payload)


def test_configuration_rejects_removed_tabular_query_presigned_ttl_seconds_field(tmp_path):
    """
    Ensure the removed tabular public presigned TTL key is rejected.

    Why this exists:
    - The tabular runtime now uses only backend-internal presigned URLs, so the
      old query TTL key should fail loudly instead of being silently ignored.

    How to use:
    - Dump a valid payload, inject
      `storage.tabular_store.query.presigned_ttl_seconds`, and assert
      validation fails.
    """

    payload = _build_minimal_configuration(storage=_build_minimal_storage(tmp_path)).model_dump(mode="python")
    payload["storage"]["tabular_store"]["query"]["presigned_ttl_seconds"] = 900

    with pytest.raises(ValueError, match="'storage.tabular_store.query.presigned_ttl_seconds' is no longer supported"):
        Configuration.model_validate(payload)
