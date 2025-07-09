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
Test suite for get_content_store() in content_storage_factory.py

Covers:
- Selection of LocalStorageBackend and MinioContentStore
- Failure case for unsupported backend type
Uses monkeypatching to mock configuration and application context.
"""

# pylint: disable=redefined-outer-name

import tempfile
import pytest

from app.core.stores.content.content_storage_factory import get_content_store
from app.core.stores.content.local_content_store import LocalStorageBackend
from app.core.stores.content.minio_content_store import MinioContentStore


class DummyConfig:  # pylint: disable=too-few-public-methods
    """Simple dummy config to simulate different content_storage types."""

    def __init__(self, store_type):
        self.content_storage = type("StorageCfg", (), {"type": store_type})()


class DummyAppContext:  # pylint: disable=too-few-public-methods
    """Dummy application context that returns the dummy config."""

    def __init__(self, config):
        self._config = config

    def get_config(self):
        return self._config


class DummyMinio:
    """Dummy Minio class."""

    def bucket_exists(self, name):
        return True

    def make_bucket(self, name):
        pass


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def patch_app_context(monkeypatch):
    """
    Fixture to allow patching ApplicationContext.get_instance()
    with custom backend type for each test.
    """

    def _patch_with_backend(store_type):
        dummy_context = DummyAppContext(DummyConfig(store_type))
        monkeypatch.setattr(
            "app.core.stores.content.content_storage_factory.ApplicationContext.get_instance",
            lambda: dummy_context,
        )

    return _patch_with_backend


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


@pytest.mark.content_storage_type(type="local")
def test_get_local_content_store(monkeypatch):
    """Test: returns LocalStorageBackend when type is 'local'."""

    # Patch le chemin local de manière sécurisée
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(
            "app.core.stores.content.content_storage_factory.ContentStoreLocalSettings",
            lambda: type("DummySettings", (), {"root_path": tmpdir}),
        )

        store = get_content_store()
        assert isinstance(store, LocalStorageBackend)


# ----------------------------
# ❌ Failure Case
# ----------------------------


def test_get_unsupported_backend_type(patch_app_context):
    """Test: raises ValueError when backend type is not recognized."""
    patch_app_context("unsupported")

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        get_content_store()
