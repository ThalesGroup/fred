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

from pathlib import Path
from types import SimpleNamespace

from fred_core.common import DuckdbStoreConfig, PostgresStoreConfig, SQLStorageConfig

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import InMemoryVectorStorage, StorageConfig


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


def test_application_context_builds_legacy_remote_tabular_store(monkeypatch):
    """
    Ensure legacy remote SQL stores are passed as DSN targets, not file paths.

    Why this exists:
    - `storage.tabular_stores` historically accepted remote SQL engines such as
      PostgreSQL or MySQL/MariaDB.
    - The compatibility path must not treat those DSN fragments like local
      filesystem paths.

    How to use:
    - Patch `SQLTableStore` with a tiny fake, then build a remote
      `SQLStorageConfig` and assert the connection target is forwarded as a
      string.
    """

    captured: dict[str, object] = {}

    class FakeSQLTableStore:
        def __init__(self, driver: str, path: str | Path):
            captured["driver"] = driver
            captured["path"] = path

    monkeypatch.setattr("knowledge_flow_backend.application_context.SQLTableStore", FakeSQLTableStore)

    ctx = ApplicationContext.__new__(ApplicationContext)
    ctx.configuration = SimpleNamespace(
        storage=SimpleNamespace(
            tabular_stores={
                "legacy_remote": SQLStorageConfig(
                    type="sql",
                    driver="postgresql+psycopg2",
                    mode="read_only",
                    host="db.example",
                    port=5432,
                    database="analytics",
                    username="reader",
                    password="pwd",  # pragma: allowlist secret
                )
            }
        )
    )
    ctx._tabular_stores = None

    stores = ApplicationContext.get_tabular_stores(ctx)

    assert list(stores) == ["analytics"]
    assert captured["driver"] == "postgresql+psycopg2"
    assert captured["path"] == "reader:pwd@db.example:5432/analytics"
    assert isinstance(captured["path"], str)
