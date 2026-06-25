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

"""Unit tests for the GcsStorageConfig signing service account field (FILES-06)."""

from knowledge_flow_backend.common.structures import GcsStorageConfig


def test_signing_service_account_email_defaults_to_none():
    """The signing SA email is optional at the model level.

    Why this exists:
    - The fail-fast requirement is enforced at store construction (factory),
      not in the pydantic model, so the model itself accepts an absent email
      and other GCS-config consumers stay decoupled from tabular concerns.
    """
    config = GcsStorageConfig(type="gcs", bucket_name="fred")

    assert config.signing_service_account_email is None


def test_signing_service_account_email_is_parsed_when_provided():
    """A configured signing SA email is carried through verbatim."""
    config = GcsStorageConfig(
        type="gcs",
        bucket_name="fred",
        signing_service_account_email="signer@project.iam.gserviceaccount.com",
    )

    assert config.signing_service_account_email == "signer@project.iam.gserviceaccount.com"
