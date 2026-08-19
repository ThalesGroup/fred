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

"""Factory-level tests for the GCS content store construction (FILES-06, #2364)."""

from types import SimpleNamespace

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import GcsStorageConfig


def test_gcs_content_store_factory_builds_without_signing_email(app_context: ApplicationContext, monkeypatch):
    """A GCS content store must boot without a signing SA email (#2364).

    Why this exists:
    - Tabular Parquet reads download artifacts through the ADC client instead
      of minting V4 signed URLs, so deployments that cannot grant
      iam.serviceAccounts.signBlob (tp-s3ns) must start normally with the
      email unset. The old fail-fast guard would have blocked exactly them.
    """
    from knowledge_flow_backend.core.stores.content import gcs_content_store

    monkeypatch.setattr(gcs_content_store, "build_gcs_client", lambda project_id=None: SimpleNamespace(bucket=lambda name: None))
    config = app_context.get_config()
    config.content_storage = GcsStorageConfig(type="gcs", bucket_name="fred")

    store = app_context.get_content_store()

    assert store.signing_service_account_email is None


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
