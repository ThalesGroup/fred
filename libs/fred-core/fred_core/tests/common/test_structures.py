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
from fred_core.common import OpenSearchStoreConfig, PostgresStoreConfig
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


# ── PostgresStoreConfig password resolution (OPS-04, issue #2170) ──────────────
#
# `password` is resolved from the environment because passwords never live in config
# files. Knowledge Flow connects to two Postgres databases under different roles, so a
# config block can name its own variable via `password_env`. These tests pin the exact
# semantics of the `default_factory` this replaced — a naive `if password is None` check
# would silently differ on two of them, and one of those differences leaks a live secret
# into `model_dump(exclude_unset=True)`.


def test_postgres_password_defaults_to_fred_postgres_password(monkeypatch) -> None:
    monkeypatch.setenv(
        "FRED_POSTGRES_PASSWORD", "shared-secret"
    )  # pragma: allowlist secret

    cfg = PostgresStoreConfig(host="localhost", database="fred", username="fred")

    assert cfg.password == "shared-secret"  # nosec B105  # pragma: allowlist secret


def test_postgres_password_env_names_a_different_variable(monkeypatch) -> None:
    """A second database under its own role reads its own variable."""
    monkeypatch.setenv(
        "FRED_POSTGRES_PASSWORD", "shared-secret"
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        "POSTGRES_KNOWLEDGE_FLOW_PASSWORD", "task-secret"
    )  # pragma: allowlist secret

    cfg = PostgresStoreConfig(
        host="localhost",
        database="knowledge_flow",
        username="knowledge_flow",
        password_env="POSTGRES_KNOWLEDGE_FLOW_PASSWORD",  # nosec B106 # pragma: allowlist secret
    )

    assert cfg.password == "task-secret"  # nosec B105  # pragma: allowlist secret


def test_postgres_explicit_password_wins_over_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "FRED_POSTGRES_PASSWORD", "shared-secret"
    )  # pragma: allowlist secret

    cfg = PostgresStoreConfig(
        host="localhost",
        database="fred",
        password="inline",  # nosec B106  # pragma: allowlist secret
    )

    assert cfg.password == "inline"  # nosec B105  # pragma: allowlist secret


def test_postgres_explicit_none_password_is_not_resolved_from_env(monkeypatch) -> None:
    """An explicit None means "no password", not "go and find one".

    This is what `default_factory` did: it applies only to an absent field, never to one
    the caller passed. A caller that deliberately passes None must not silently receive
    another database's credential.
    """
    monkeypatch.setenv(
        "FRED_POSTGRES_PASSWORD", "shared-secret"
    )  # pragma: allowlist secret

    cfg = PostgresStoreConfig(host="localhost", database="fred", password=None)

    assert cfg.password is None


def test_postgres_resolved_password_never_enters_exclude_unset_dump(
    monkeypatch,
) -> None:
    """Resolution must not mark `password` as explicitly set.

    `model_dump(exclude_unset=True)` means "only what was configured". If env resolution
    joined `model_fields_set`, every such dump of a storage block would start emitting a
    live database password — for every backend, since this model is shared.
    """
    monkeypatch.setenv(
        "FRED_POSTGRES_PASSWORD", "shared-secret"
    )  # pragma: allowlist secret

    cfg = PostgresStoreConfig(host="localhost", database="fred", username="fred")

    assert "password" not in cfg.model_dump(exclude_unset=True)
    assert "password" not in cfg.model_fields_set
    # ...while the value is still usable for connecting.
    assert cfg.password == "shared-secret"  # nosec B105  # pragma: allowlist secret


def test_postgres_password_missing_env_resolves_to_none(monkeypatch) -> None:
    """Engine construction raises on this; the config itself must not."""
    monkeypatch.delenv("FRED_POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_KNOWLEDGE_FLOW_PASSWORD", raising=False)

    cfg = PostgresStoreConfig(
        host="localhost",
        database="knowledge_flow",
        password_env="POSTGRES_KNOWLEDGE_FLOW_PASSWORD",  # nosec B106 # pragma: allowlist secret
    )

    assert cfg.password is None


def test_postgres_dsn_percent_encodes_url_reserved_characters(monkeypatch) -> None:
    """A password is operator-chosen and may hold `@`, `:`, `/` or `#`.

    Interpolated raw these do not fail loudly — they re-parse the URL, so the connection
    silently targets a different host with a truncated password. This became a live risk
    when `postgresql.knowledgeFlow.password` turned into a required, human-chosen value.
    """
    from sqlalchemy.engine import make_url

    monkeypatch.delenv("FRED_POSTGRES_PASSWORD", raising=False)
    hostile = "p@ss/wo:rd#1"  # nosec B105  # pragma: allowlist secret

    cfg = PostgresStoreConfig(
        host="postgres",
        database="knowledge_flow",
        username="knowledge_flow",
        password=hostile,
    )

    for dsn in (cfg.dsn(), cfg.async_dsn()):
        url = make_url(dsn)
        assert url.host == "postgres"
        assert url.database == "knowledge_flow"
        assert url.username == "knowledge_flow"
        assert url.password == hostile


def test_postgres_dsn_renders_unresolved_password_as_empty_not_none(
    monkeypatch,
) -> None:
    """`dsn()` is consumed directly by PostgresEventBus, which bypasses the engine
    factory's password check. An unresolved password must not become the literal
    string "None" and get offered as a real credential."""
    monkeypatch.delenv("FRED_POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_KNOWLEDGE_FLOW_PASSWORD", raising=False)

    cfg = PostgresStoreConfig(
        host="postgres",
        database="knowledge_flow",
        username="knowledge_flow",
        password_env="POSTGRES_KNOWLEDGE_FLOW_PASSWORD",  # nosec B106 # pragma: allowlist secret
    )

    assert cfg.password is None
    assert "None" not in cfg.dsn()
    assert cfg.dsn() == "postgresql://knowledge_flow:@postgres:5432/knowledge_flow"
