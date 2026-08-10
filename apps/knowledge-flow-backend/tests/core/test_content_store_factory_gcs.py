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

"""Factory-level tests for the GCS content store fail-fast guard (FILES-06)."""

import pytest

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import GcsStorageConfig
from knowledge_flow_backend.core.stores.content import gcs_content_store as gcs_content_store_module
from knowledge_flow_backend.core.stores.content.gcs_content_store import GcsContentStore


def test_gcs_content_store_factory_fails_fast_without_signing_email(app_context: ApplicationContext):
    """A GCS content store without a signing SA email must refuse to build.

    Why this exists:
    - with url_strategy='presigned' there is no per-feature flag to detect which
      feature will need a signed URL; a missing signing email is a deployment error
      that must surface clearly at startup rather than as an opaque later failure.
    """
    config = app_context.get_config()
    config.content_storage = GcsStorageConfig(type="gcs", bucket_name="fred")

    with pytest.raises(ValueError, match="signing_service_account_email"):
        app_context.get_content_store()


class _FakeGcsClient:
    def bucket(self, name: str) -> object:
        return object()


def test_gcs_content_store_factory_starts_without_signing_email_in_proxy_mode(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch):
    """url_strategy='proxy' is exactly the deployment that has no signBlob permission.

    This is the point of CONTENT-URL-STRATEGY: browser-facing objects are streamed by
    the backend behind an application-signed URL, so GCS never signs anything and the
    platform must boot without a signing service account.
    """
    monkeypatch.setattr(gcs_content_store_module, "build_gcs_client", lambda project_id=None: _FakeGcsClient())
    config = app_context.get_config()
    config.content_storage = GcsStorageConfig(type="gcs", bucket_name="fred", url_strategy="proxy")

    store = app_context.get_content_store()

    assert isinstance(store, GcsContentStore)
    assert store.object_bucket_name == "fred-objects"


def test_get_content_store_builds_once_and_reuses_the_instance(app_context: ApplicationContext):
    """`get_content_store()` must cache its instance like its siblings `get_file_store()`/
    `get_log_store()` in the same class — each backend's __init__ builds a real client
    (a GCS `storage.Client()`, in production, with its own auth + HTTP connection pool),
    so rebuilding it on every call reloads that on every Temporal activity that touches
    content storage, not just once per pod."""
    first = app_context.get_content_store()
    second = app_context.get_content_store()

    assert first is second


def test_get_embedder_builds_once_and_reuses_the_instance(app_context: ApplicationContext):
    """`get_embedder()` was the one get_* factory in ApplicationContext without a cache
    slot, unlike every sibling (get_file_store, get_content_store, ...) — it's called
    per-activity from several scheduler activities (fast_store_vectors, delete_vectors,
    ...), not just once at startup, so rebuilding the underlying provider client on
    every call matters just like the content-store case above."""
    first = app_context.get_embedder()
    second = app_context.get_embedder()

    assert first is second
