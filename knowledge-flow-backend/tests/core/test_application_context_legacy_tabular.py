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

from types import SimpleNamespace

import pytest
from fred_core import M2MSecurity, SecurityConfiguration, UserSecurity
from fred_core.common import DuckdbStoreConfig, ModelConfiguration, PostgresStoreConfig, SQLStorageConfig, TemporalSchedulerConfig
from pydantic import AnyHttpUrl, AnyUrl

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import (
    AppConfig,
    Configuration,
    InMemoryVectorStorage,
    LocalContentStorageConfig,
    LocalFilesystemConfig,
    SchedulerConfig,
    StorageConfig,
    TabularConfig,
)


def _build_minimal_configuration(*, storage: StorageConfig, include_tabular: bool) -> Configuration:
    """
    Build a minimal Knowledge Flow configuration for tabular mode validation.

    Why this exists:
    - Tests in this module need a compact but valid `Configuration` object to
      exercise the mutual-exclusion rule between legacy and recommended
      tabular modes.

    How to use:
    - Pass a prepared `StorageConfig`.
    - Set `include_tabular=True` when you want to declare the recommended
      dataset-centric mode explicitly in the input payload.
    """

    kwargs = {}
    if include_tabular:
        kwargs["tabular"] = TabularConfig()

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
        **kwargs,
    )


def test_storage_config_accepts_legacy_tabular_stores(tmp_path):
    """
    Ensure old `storage.tabular_stores` configuration still parses.

    Why this exists:
    - Older deployments may still pass the legacy tabular SQL-store section in
      YAML even though the default runtime is now dataset-centric.

    How to use:
    - Build a `StorageConfig` with `tabular_stores` and assert the field is
      preserved.
    """

    legacy_path = tmp_path / "legacy-tabular.duckdb"

    storage = StorageConfig(
        postgres=PostgresStoreConfig(host="localhost", database="fred"),
        resource_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "resource.duckdb")),
        tag_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "tag.duckdb")),
        kpi_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "kpi.duckdb")),
        metadata_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "metadata.duckdb")),
        vector_store=InMemoryVectorStorage(type="in_memory"),
        tabular_stores={
            "legacy": SQLStorageConfig(
                type="sql",
                driver="duckdb",
                mode="read_and_write",
                database="base_database",
                path=str(legacy_path),
            )
        },
    )

    assert storage.tabular_stores is not None
    assert "legacy" in storage.tabular_stores


def test_configuration_rejects_explicit_mixed_tabular_modes(tmp_path):
    """
    Ensure recommended and legacy tabular modes cannot be declared together.

    Why this exists:
    - The configuration contract must force users to choose a single tabular
      SQL mode at a time.

    How to use:
    - Build a `StorageConfig` with legacy `tabular_stores`, then explicitly
      provide top-level `tabular` and assert validation fails.
    """

    storage = StorageConfig(
        postgres=PostgresStoreConfig(host="localhost", database="fred"),
        resource_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "resource.duckdb")),
        tag_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "tag.duckdb")),
        kpi_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "kpi.duckdb")),
        metadata_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "metadata.duckdb")),
        vector_store=InMemoryVectorStorage(type="in_memory"),
        tabular_stores={
            "legacy": SQLStorageConfig(
                type="sql",
                driver="duckdb",
                mode="read_and_write",
                database="base_database",
                path=str(tmp_path / "legacy-tabular.duckdb"),
            )
        },
    )

    with pytest.raises(ValueError, match="Choose exactly one tabular SQL mode"):
        _build_minimal_configuration(storage=storage, include_tabular=True)


def test_configuration_accepts_legacy_tabular_mode_without_explicit_tabular(tmp_path):
    """
    Ensure the legacy tabular mode still works when used on its own.

    Why this exists:
    - The new mutual-exclusion validator must not break older deployments that
      declare only `storage.tabular_stores`.

    How to use:
    - Build a `StorageConfig` with legacy stores and omit the explicit
      top-level `tabular` payload.
    """

    storage = StorageConfig(
        postgres=PostgresStoreConfig(host="localhost", database="fred"),
        resource_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "resource.duckdb")),
        tag_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "tag.duckdb")),
        kpi_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "kpi.duckdb")),
        metadata_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "metadata.duckdb")),
        vector_store=InMemoryVectorStorage(type="in_memory"),
        tabular_stores={
            "legacy": SQLStorageConfig(
                type="sql",
                driver="duckdb",
                mode="read_and_write",
                database="base_database",
                path=str(tmp_path / "legacy-tabular.duckdb"),
            )
        },
    )

    config = _build_minimal_configuration(storage=storage, include_tabular=False)

    assert config.storage.tabular_stores is not None
    assert "legacy" in config.storage.tabular_stores


def test_application_context_builds_legacy_tabular_stores_and_csv_input_store(tmp_path):
    """
    Ensure ApplicationContext still exposes the legacy tabular SQL-store helpers.

    Why this exists:
    - The compatibility layer should keep older callers working even after the
      dataset-centric tabular runtime became the default.

    How to use:
    - Build a lightweight `ApplicationContext` shell with one legacy
      `storage.tabular_stores` entry and call the compatibility helpers.
    """

    legacy_path = tmp_path / "base_database.duckdb"
    ctx = ApplicationContext.__new__(ApplicationContext)
    ctx.configuration = SimpleNamespace(
        storage=SimpleNamespace(
            tabular_stores={
                "legacy": SQLStorageConfig(
                    type="sql",
                    driver="duckdb",
                    mode="read_and_write",
                    database="base_database",
                    path=str(legacy_path),
                )
            }
        )
    )
    ctx._tabular_stores = None

    stores = ApplicationContext.get_tabular_stores(ctx)

    assert list(stores) == ["base_database"]
    assert ApplicationContext.get_csv_input_store(ctx) is stores["base_database"].store
