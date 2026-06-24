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


def test_gcs_content_store_factory_fails_fast_without_signing_email(app_context: ApplicationContext):
    """A GCS content store without a signing SA email must refuse to build.

    Why this exists:
    - tabular_store is always configured, so there is no per-feature flag to
      detect tabular usage; a missing signing email is a deployment error that
      must surface clearly at startup rather than as an opaque later failure.
    """
    config = app_context.get_config()
    config.content_storage = GcsStorageConfig(type="gcs", bucket_name="fred")

    with pytest.raises(ValueError, match="signing_service_account_email"):
        app_context.get_content_store()
