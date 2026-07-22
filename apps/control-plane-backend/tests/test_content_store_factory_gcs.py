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

"""Factory-level tests for the control-plane GCS content store (issue #2022).

Mirrors knowledge-flow's equivalent fail-fast guard test: banner/logo images
are served straight to the browser via get_presigned_url, so a GCS content
store without a signing service account email is a deployment error that must
surface clearly at startup rather than as a silently-missing banner later.
"""

from __future__ import annotations

import pytest
from control_plane_backend.app.context import ApplicationContext
from control_plane_backend.config.loader import load_configuration
from control_plane_backend.config.models import GcsContentStorageConfig
from fred_core.store import GcsContentStore
from fred_core.store import gcs_content_store as gcs_content_store_module


def _context(monkeypatch: pytest.MonkeyPatch) -> ApplicationContext:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    return ApplicationContext(load_configuration())


def test_gcs_content_store_factory_fails_fast_without_signing_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context(monkeypatch)
    ctx.configuration.storage.content_storage = GcsContentStorageConfig(
        type="gcs", bucket_name="fred"
    )

    with pytest.raises(ValueError, match="signing_service_account_email"):
        ctx.get_content_store()


class _FakeClient:
    def bucket(self, name: str) -> object:
        return object()


def test_gcs_content_store_factory_builds_store_with_suffixed_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gcs_content_store_module,
        "build_gcs_client",
        lambda project_id=None: _FakeClient(),
    )
    ctx = _context(monkeypatch)
    ctx.configuration.storage.content_storage = GcsContentStorageConfig(
        type="gcs",
        bucket_name="fred",
        signing_service_account_email="signer@project.iam.gserviceaccount.com",
    )

    store = ctx.get_content_store()

    assert isinstance(store, GcsContentStore)
    assert store.bucket_name == "fred-objects"
    assert (
        store.signing_service_account_email == "signer@project.iam.gserviceaccount.com"
    )
