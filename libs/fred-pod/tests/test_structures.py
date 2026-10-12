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
from fred_pod.common import OpenSearchStoreConfig, PodAppIdentity
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


@pytest.mark.parametrize("runtime_id", ["fred-agents", "webdav-kb", "kb2", "a"])
def test_a_runtime_id_is_a_lowercase_slug(runtime_id: str) -> None:
    assert PodAppIdentity(runtime_id=runtime_id).runtime_id == runtime_id


@pytest.mark.parametrize(
    "runtime_id",
    [
        "",
        "My KB",
        "Webdav",
        "fred.samples.webdav",
        "kb_webdav",
        "-kb",
        "kb-",
        "kb--x",
        "2kb",
    ],
)
def test_anything_else_is_refused(runtime_id: str) -> None:
    with pytest.raises(ValidationError):
        PodAppIdentity(runtime_id=runtime_id)


def test_a_runtime_id_has_no_default() -> None:
    with pytest.raises(ValidationError, match="runtime_id"):
        PodAppIdentity.model_validate({})
