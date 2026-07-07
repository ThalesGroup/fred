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

import pytest
from fred_core.common import OpenSearchStoreConfig
from pydantic import ValidationError


def test_opensearch_config_requires_password(monkeypatch) -> None:
    monkeypatch.delenv("OPENSEARCH_PASSWORD", raising=False)

    with pytest.raises(ValidationError, match="OPENSEARCH_PASSWORD"):
        OpenSearchStoreConfig(host="https://localhost:9200", username="admin")


def test_opensearch_config_password_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENSEARCH_PASSWORD", "secret")  # pragma: allowlist secret

    cfg = OpenSearchStoreConfig(host="https://localhost:9200", username="admin")

    assert cfg.password == "secret"  # nosec B105  # pragma: allowlist secret


def test_opensearch_config_explicit_password_wins(monkeypatch) -> None:
    monkeypatch.delenv("OPENSEARCH_PASSWORD", raising=False)

    cfg = OpenSearchStoreConfig(
        host="https://localhost:9200",
        username="admin",
        password="inline",  # nosec B106  # pragma: allowlist secret
    )

    assert cfg.password == "inline"  # nosec B105  # pragma: allowlist secret
