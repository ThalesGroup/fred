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

"""Verify changed log sinks exclude synthetic connection and identity values."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from fred_core.common import PostgresStoreConfig
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac.rebac_engine import (
    RebacReference,
    TeamPermission,
)
from fred_core.sql import base_sql
from fred_core.sql.base_sql import (
    create_async_engine_from_config,
    create_engine_from_config,
)
from fred_core.tests.security.rebac_fakes import FakeRebacEngine

_SECRET = "canary-p4ssw0rd-not-elsewhere"  # nosec B105 # pragma: allowlist secret
_HOST = "canary-host-not-elsewhere.internal"
_ACCOUNT = "canary-account-not-elsewhere"
_DATABASE = "canary-database-not-elsewhere"
_CONNECTION_CANARIES = (_SECRET, _HOST, _ACCOUNT, _DATABASE)
_REQUIRED_ENV = "FRED_POSTGRES_PASSWORD"

# Never touched: every path operation is stubbed out.
_SQLITE_DIRECTORY = "/canary-directory-not-elsewhere"
_SQLITE_FILE = "canary-file-not-elsewhere.sqlite"
_SQLITE_PATH = f"{_SQLITE_DIRECTORY}/{_SQLITE_FILE}"

# One parameter set per engine factory and the constructor it calls, so both
# branches of this module are held to the same rule.
_FACTORIES = [
    pytest.param(create_engine_from_config, "create_engine", id="sync"),
    pytest.param(create_async_engine_from_config, "create_async_engine", id="async"),
]


class _CapturingHandler(logging.Handler):
    """Own handler: `log_setup()` can leave pytest's caplog deaf."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self._formatter = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def sightings(self, needle: str) -> list[str]:
        found: list[str] = []
        for record in self.records:
            if needle in record.getMessage():
                found.append("message")
            if needle in repr(record.args):
                found.append("args")
            if record.exc_info and needle in repr(record.exc_info):
                found.append("exception")
            # What a real handler writes out, traceback and exception chain
            # included — the only check that covers `exc_info=True` logging.
            if needle in self._formatter.format(record):
                found.append("rendered")
        return found


@pytest.fixture
def sink() -> Any:
    handler = _CapturingHandler()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


def _postgres_config(monkeypatch) -> PostgresStoreConfig:
    monkeypatch.setenv(_REQUIRED_ENV, _SECRET)
    return PostgresStoreConfig(
        host=_HOST,
        port=5432,
        database=_DATABASE,
        username=_ACCOUNT,
    )


def _driver_failure() -> Exception:
    """A failure carrying the connection identity in its text and its cause."""
    cause = ValueError(f"password authentication failed: {_SECRET}")
    failure = RuntimeError(f"could not connect to {_HOST} as {_ACCOUNT}/{_DATABASE}")
    failure.__cause__ = cause
    return failure


@pytest.mark.parametrize(("build_engine", "constructor"), _FACTORIES)
def test_engine_creation_logs_no_connection_identity(
    sink, monkeypatch, build_engine, constructor: str
) -> None:
    """This runs on every process start and the line outlives the deployment."""
    monkeypatch.setattr(base_sql, constructor, lambda *args, **kwargs: object())
    config = _postgres_config(monkeypatch)

    build_engine(config)

    for needle in _CONNECTION_CANARIES:
        assert sink.sightings(needle) == []


@pytest.mark.parametrize(("build_engine", "constructor"), _FACTORIES)
def test_engine_creation_failure_logs_no_connection_identity(
    sink, monkeypatch, build_engine, constructor: str
) -> None:
    """A driver failure names the connection in its own text and its cause.

    Logging the exception would copy both into the sink, so the failure is
    recorded without them and raised unchanged for the caller to handle.
    """

    def _fail(*args, **kwargs):
        raise _driver_failure()

    monkeypatch.setattr(base_sql, constructor, _fail)
    config = _postgres_config(monkeypatch)

    with pytest.raises(RuntimeError) as failure:
        build_engine(config)

    assert isinstance(failure.value.__cause__, ValueError)
    for needle in _CONNECTION_CANARIES:
        assert sink.sightings(needle) == []
    assert [record.exc_info for record in sink.records if record.exc_info] == []


def test_sqlite_engine_creation_logs_no_path(sink, monkeypatch) -> None:
    """The path names a location on the host, and often the account on it."""
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        base_sql, "create_async_engine", lambda *args, **kwargs: object()
    )

    create_async_engine_from_config(PostgresStoreConfig(sqlite_path=_SQLITE_PATH))

    for needle in (_SQLITE_PATH, _SQLITE_DIRECTORY, _SQLITE_FILE):
        assert sink.sightings(needle) == []


def test_sqlite_engine_failure_logs_no_path_and_still_raises(sink, monkeypatch) -> None:
    """The failure text is a second route for the same path to reach a sink."""

    def _fail(*args, **kwargs):
        raise RuntimeError(f"unable to open database file {_SQLITE_PATH}")

    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(base_sql, "create_async_engine", _fail)

    with pytest.raises(RuntimeError):
        create_async_engine_from_config(PostgresStoreConfig(sqlite_path=_SQLITE_PATH))

    for needle in (_SQLITE_PATH, _SQLITE_DIRECTORY, _SQLITE_FILE):
        assert sink.sightings(needle) == []


def test_missing_password_is_reported_without_naming_the_variable(
    sink, monkeypatch
) -> None:
    """A secret's variable name tells a reader exactly where the secret is."""
    monkeypatch.delenv(_REQUIRED_ENV, raising=False)
    config = PostgresStoreConfig(
        host=_HOST,
        port=5432,
        database=_DATABASE,
        username=_ACCOUNT,
    )

    with pytest.raises(RuntimeError) as failure:
        create_async_engine_from_config(config)

    assert _REQUIRED_ENV not in str(failure.value)
    assert sink.sightings(_REQUIRED_ENV) == []
    for needle in (_HOST, _ACCOUNT, _DATABASE):
        assert sink.sightings(needle) == []


@pytest.mark.asyncio
async def test_an_authorization_denial_logs_no_subject_or_resource(sink) -> None:
    """A denial names who wanted what — the identifying pair to keep out."""
    rebac = FakeRebacEngine(permitted=False)

    with pytest.raises(AuthorizationError):
        await rebac.check_permission_or_raise(
            RebacReference(type=Resource.TEAM, id=_ACCOUNT),
            TeamPermission.CAN_USE_TEAM_APPLICATIONS,
            RebacReference(type=Resource.APP, id=_DATABASE),
        )

    assert sink.sightings(_ACCOUNT) == []
    assert sink.sightings(_DATABASE) == []


def test_the_canary_probe_can_actually_see_a_leak() -> None:
    """Detect harmless markers without emitting into the logging pipeline."""
    marker = "detector-probe"
    sink = _CapturingHandler()
    sink.handle(
        logging.LogRecord(
            name="probe",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="probe %s",
            args=(marker,),
            exc_info=None,
        )
    )

    assert "message" in sink.sightings(marker)
    assert "args" in sink.sightings(marker)
    assert "rendered" in sink.sightings(marker)


def test_the_canary_probe_can_see_a_leak_through_a_traceback() -> None:
    """Detect an exception marker and its cause in an in-memory record."""
    marker = "detector-exception"
    cause_marker = "detector-cause"
    sink = _CapturingHandler()
    try:
        raise RuntimeError(marker) from ValueError(cause_marker)
    except RuntimeError as error:
        sink.handle(
            logging.LogRecord(
                name="probe",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="probe",
                args=(),
                exc_info=(type(error), error, error.__traceback__),
            )
        )

    assert "exception" in sink.sightings(marker)
    assert "rendered" in sink.sightings(cause_marker)
    assert "exception" not in sink.sightings(cause_marker)
