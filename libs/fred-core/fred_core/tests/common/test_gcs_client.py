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

"""build_gcs_client must mirror the ADC credentials' universe domain.

Regression coverage for the Trusted Partner Cloud / sovereign deployment case
(e.g. S3NS): bare `storage.Client(project=project_id)` assumes the
`googleapis.com` universe domain and raises `UniverseMismatchError` the moment
ADC credentials belong to a different universe (`s3nsapis.fr`, ...).
"""

from __future__ import annotations

from fred_core.common import gcs_client


class _FakeCredentials:
    def __init__(self, universe_domain: str):
        self.universe_domain = universe_domain


def test_build_gcs_client_passes_credentials_universe_domain_through(monkeypatch):
    fake_credentials = _FakeCredentials("s3nsapis.fr")
    monkeypatch.setattr(
        gcs_client.google.auth, "default", lambda: (fake_credentials, "adc-project")
    )

    captured: dict = {}

    class _FakeClient:
        def __init__(self, *, project, credentials, client_options):
            captured["project"] = project
            captured["credentials"] = credentials
            captured["universe_domain"] = client_options.universe_domain

    monkeypatch.setattr(gcs_client.storage, "Client", _FakeClient)

    gcs_client.build_gcs_client("explicit-project")

    assert captured["project"] == "explicit-project"
    assert captured["credentials"] is fake_credentials
    assert captured["universe_domain"] == "s3nsapis.fr"


def test_build_gcs_client_falls_back_to_adc_project_when_unset(monkeypatch):
    fake_credentials = _FakeCredentials("googleapis.com")
    monkeypatch.setattr(
        gcs_client.google.auth, "default", lambda: (fake_credentials, "adc-project")
    )

    captured: dict = {}

    class _FakeClient:
        def __init__(self, *, project, credentials, client_options):
            captured["project"] = project

    monkeypatch.setattr(gcs_client.storage, "Client", _FakeClient)

    gcs_client.build_gcs_client(None)

    assert captured["project"] == "adc-project"
