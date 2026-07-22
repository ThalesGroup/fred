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

import io
import logging
from datetime import timedelta
from typing import BinaryIO, Optional

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud.exceptions import NotFound

from fred_core.common.gcs_client import build_gcs_client

logger = logging.getLogger(__name__)

# OAuth2 scope required to mint the access token that authorizes the IAM
# signBlob call used for keyless V4 URL signing under Workload Identity.
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def _load_adc_credentials():
    """Return Application Default Credentials able to mint OAuth2 access tokens.

    Why this exists:
    - Keyless V4 signing needs an access token for the IAM signBlob API. This is
      isolated as a module function so tests can substitute it without reaching
      into the shared ``google.auth`` namespace.
    """
    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    return credentials


class GcsContentStore:
    """Content store backed by Google Cloud Storage.

    Why this exists:
    - Deployments on GKE want native GCS instead of MinIO, authenticated via
      Application Default Credentials / Workload Identity (no JSON key).

    Signed URLs need special care under Workload Identity: there is no service
    account private key, so plain ``blob.generate_signed_url()`` fails. This
    store mints short-lived V4 signed URLs via IAM ``signBlob`` impersonation
    of ``signing_service_account_email`` instead — the same keyless mechanism
    already used for backend-internal tabular Parquet reads in
    knowledge-flow's ``GcsContentStore`` (see
    ``docs/swift/rfc/GCS-TABULAR-SIGNED-URL-RFC.md``). Callers here are
    browser-facing (e.g. team banner images), which that RFC left open as "a
    separate browser direct-download decision" — this class is that decision,
    scoped to fred-core's generic object store only.

    Basic usage:
    ```python
    from io import BytesIO
    from fred_core.store import GcsContentStore

    store = GcsContentStore(
        bucket_name="fred-objects",
        signing_service_account_email="fred-sa@my-project.iam.gserviceaccount.com",
    )
    store.put_object("teams/t1/banner.png", BytesIO(b"..."), content_type="image/png")
    url = store.get_presigned_url("teams/t1/banner.png")
    ```
    """

    def __init__(
        self,
        *,
        bucket_name: str,
        project_id: Optional[str] = None,
        signing_service_account_email: Optional[str] = None,
    ) -> None:
        """Bind to a GCS bucket using ADC. The bucket must already exist.

        `signing_service_account_email` is required to call `get_presigned_url`;
        callers that only write objects can omit it, but the application factory
        should fail fast when it is missing for a deployment that needs it.
        """

        self.bucket_name = bucket_name
        self.signing_service_account_email = signing_service_account_email
        # Lazily-acquired ADC credentials, cached and refreshed on demand to mint
        # the access token for IAM signBlob. None until the first signing call.
        self._signing_credentials = None

        self.client = build_gcs_client(project_id)
        self.bucket = self.client.bucket(bucket_name)
        logger.info(
            "[CONTENT][GCS] Initialized GcsContentStore bucket='%s'", bucket_name
        )

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Remove a leading slash so GCS object names stay consistent.

        Example:
        ```python
        GcsContentStore._normalize_key("/a/b.txt")  # "a/b.txt"
        ```
        """

        return key.lstrip("/")

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        """Upload bytes to GCS under `key`.

        Example:
        ```python
        from io import BytesIO
        store.put_object("exports/run-42.json", BytesIO(b"{}"), content_type="application/json")
        ```
        """

        object_name = self._normalize_key(key)
        payload = stream.read()
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        ct = content_type or "application/octet-stream"
        blob = self.bucket.blob(object_name)
        blob.upload_from_file(io.BytesIO(payload), content_type=ct)
        logger.info(
            "[CONTENT][GCS] put object=%s bucket='%s'", object_name, self.bucket_name
        )

    def _mint_access_token(self) -> str:
        """Return a valid OAuth2 access token for the IAM signBlob signing call.

        Credentials are cached on the instance and refreshed only when expired,
        so steady-state signing avoids a token round-trip per call.
        """
        if self._signing_credentials is None:
            self._signing_credentials = _load_adc_credentials()
        if not self._signing_credentials.valid:
            self._signing_credentials.refresh(GoogleAuthRequest())
        token = self._signing_credentials.token
        if not token:
            raise RuntimeError(
                "[CONTENT][GCS] ADC returned no access token for IAM signBlob signing"
            )
        return token

    def get_presigned_url(
        self, key: str, expires: timedelta = timedelta(hours=1)
    ) -> str:
        """Create a temporary browser-facing download URL for object `key`.

        Mints a short-lived V4 signed URL via IAM `signBlob` impersonation of
        `signing_service_account_email` — keyless, works under Workload
        Identity. Requires the impersonated service account to hold
        `storage.objects.get` on this bucket, and the caller's Workload
        Identity service account to hold `iam.serviceAccounts.signBlob` on it.

        Raises:
            RuntimeError: no `signing_service_account_email` was configured.
            FileNotFoundError: object does not exist.
        """

        if not self.signing_service_account_email:
            raise RuntimeError(
                f"[CONTENT][GCS] Cannot sign URL for '{key}': no "
                "signing_service_account_email configured for this GCS content store."
            )
        object_name = self._normalize_key(key)
        blob = self.bucket.blob(object_name)
        try:
            if not blob.exists(self.client):
                raise FileNotFoundError(f"Object not found: {key}")
        except NotFound as e:
            raise FileNotFoundError(f"Object not found: {key}") from e

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expires,
            method="GET",
            service_account_email=self.signing_service_account_email,
            access_token=self._mint_access_token(),
        )
        # Log the request, never the signed URL (it grants temporary read access).
        logger.info(
            "[CONTENT][GCS] minted V4 signed URL key=%s ttl=%ds",
            key,
            int(expires.total_seconds()),
        )
        return signed_url
