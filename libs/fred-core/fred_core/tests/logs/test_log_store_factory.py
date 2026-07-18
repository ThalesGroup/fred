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

import pytest
from fred_core.common.structures import OpenSearchIndexConfig, OpenSearchStoreConfig
from fred_core.logs.log_store_factory import build_log_store
from fred_core.logs.log_structures import InMemoryLogStorageConfig
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.logs.opensearch_log_store import OpenSearchLogStore


def _fake_opensearch_client(*args: object, **kwargs: object) -> object:
    class _Indices:
        def exists(self, index: str) -> bool:
            return True

    class _Client:
        indices = _Indices()

    return _Client()


def test_build_log_store_defaults_to_ram_when_no_config() -> None:
    store = build_log_store(log_store_config=None, opensearch_config=None)
    assert isinstance(store, RamLogStore)


def test_build_log_store_returns_ram_for_explicit_in_memory_config() -> None:
    store = build_log_store(
        log_store_config=InMemoryLogStorageConfig(type="in_memory"),
        opensearch_config=OpenSearchStoreConfig(
            host="http://opensearch:9200",
            username="admin",
            password="admin",  # nosec B106
        ),
    )
    assert isinstance(store, RamLogStore)


def test_build_log_store_opensearch_without_connection_config_raises() -> None:
    with pytest.raises(ValueError, match="storage.opensearch is not configured"):
        build_log_store(
            log_store_config=OpenSearchIndexConfig(type="opensearch", index="logs"),
            opensearch_config=None,
        )


def test_build_log_store_builds_opensearch_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "fred_core.logs.opensearch_log_store.OpenSearch",
        _fake_opensearch_client,
    )
    store = build_log_store(
        log_store_config=OpenSearchIndexConfig(type="opensearch", index="logs-index"),
        opensearch_config=OpenSearchStoreConfig(
            host="http://opensearch:9200",
            username="admin",
            password="admin",  # nosec B106
        ),
    )
    assert isinstance(store, OpenSearchLogStore)
    assert store.index == "logs-index"
