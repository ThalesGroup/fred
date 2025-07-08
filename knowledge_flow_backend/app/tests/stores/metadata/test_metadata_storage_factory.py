# Copyright Thales 2025
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

"""
Test suite for metadata_storage_factory.py

Covers:
- Correct instantiation of LocalMetadataStore and OpenSearchMetadataStore
- Error handling for unknown storage types
- Use of monkeypatching to simulate ApplicationContext and config
"""

# pylint: disable=too-few-public-methods,redefined-outer-name,missing-function-docstring,missing-class-docstring

import pytest

from app.core.stores.metadata.local_metadata_store import LocalMetadataStore
from app.core.stores.metadata.metadata_storage_factory import get_metadata_store
from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore
import app.core.stores.metadata.opensearch_metadata_store as oms

class DummyConfig:
    """Mock config with configurable metadata storage type."""

    def __init__(self, store_type):
        self.metadata_storage = type("MetaCfg", (), {"type": store_type})()


class DummyAppContext:
    """Mock ApplicationContext that returns dummy config."""

    def __init__(self, config):
        self._config = config

    def get_config(self):
        return self._config


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def patch_context(monkeypatch):
    """Patch ApplicationContext.get_instance to return controlled config."""

    def _patch(store_type):
        dummy = DummyAppContext(DummyConfig(store_type))
        monkeypatch.setattr("app.core.stores.metadata.metadata_storage_factory.ApplicationContext.get_instance", lambda: dummy)

    return _patch


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_get_local_metadata_store(monkeypatch, patch_context):
    """Test: get_metadata_store returns LocalMetadataStore when type='local'."""
    patch_context("local")
    monkeypatch.setattr(
        "app.core.stores.metadata.metadata_storage_factory.MetadataStoreLocalSettings",
        lambda: type("Cfg", (), {"metadata_file": "/tmp/test.json", "root_path": "/tmp"}),
    )
    store = get_metadata_store()
    assert isinstance(store, LocalMetadataStore)


# ----------------------------
# ❌ Error Cases
# ----------------------------


def test_get_opensearch_metadata_store(monkeypatch, patch_context):
    """Test: get_metadata_store returns OpenSearchMetadataStore when type='opensearch'."""
    patch_context("opensearch")
    monkeypatch.setattr(
        "app.core.stores.metadata.metadata_storage_factory.validate_settings_or_exit",
        lambda cls, name: type(
            "Cfg",
            (),
            {
                "opensearch_host": "localhost",
                "opensearch_metadata_index": "meta",
                "opensearch_vector_index": "vec",
                "opensearch_user": "user",
                "opensearch_password": "",
                "opensearch_secure": False,
                "opensearch_verify_certs": False,
            },
        )(),
    )

    class DummyIndices:
        def exists(self, index=None, **kwargs):
            return False

        def create(self, index):
            return {"acknowledged": True}

    class DummyOpenSearch:
        def __init__(self, *args, **kwargs):
            self.indices = DummyIndices()

    monkeypatch.setattr(oms, "OpenSearch", DummyOpenSearch)
    store = get_metadata_store()
    assert isinstance(store, OpenSearchMetadataStore)


def test_get_metadata_store_invalid_type(patch_context):
    """Test: get_metadata_store raises ValueError for unknown type."""
    patch_context("invalid")
    with pytest.raises(ValueError, match="Unsupported metadata storage backend"):
        get_metadata_store()
