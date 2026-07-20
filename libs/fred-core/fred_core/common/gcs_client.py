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

from typing import Optional

import google.auth
from google.api_core.client_options import ClientOptions
from google.cloud import storage


def build_gcs_client(project_id: Optional[str] = None) -> storage.Client:
    """Build a GCS client whose universe domain matches the loaded ADC credentials.

    Why this exists:
    - Bare ``storage.Client(project=project_id)`` implicitly assumes the
      ``googleapis.com`` universe domain. Under Trusted Partner Cloud /
      sovereign deployments (e.g. S3NS, the Thales/Google joint venture cloud
      in France), Workload Identity Federation ADC credentials declare a
      different universe domain (e.g. ``s3nsapis.fr``), and the client raises
      ``google.api_core.universe.UniverseMismatchError`` the moment it tries
      to authenticate: "The configured universe domain (googleapis.com) does
      not match the universe domain found in the credentials (s3nsapis.fr)."
    - Explicitly loading ADC and mirroring ``credentials.universe_domain``
      into ``client_options`` makes every GCS-backed store portable across
      public GCP and sovereign GCP variants with zero extra configuration —
      the client always trusts whatever universe the credentials actually
      belong to instead of assuming the public default.

    Used by every native-GCS backend (fred-core's content store and virtual
    filesystem, knowledge-flow's content store and file store) so the fix
    lives in one place.
    """

    credentials, adc_project = google.auth.default()
    return storage.Client(
        project=project_id or adc_project,
        credentials=credentials,
        client_options=ClientOptions(universe_domain=credentials.universe_domain),
    )
