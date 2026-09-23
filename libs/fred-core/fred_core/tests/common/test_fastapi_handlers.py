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

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.logs.audit_log import AUDIT_LOGGER_NAME
from fred_core.security.models import (
    AuthorizationError,
    Resource,
    StandingAuthorizationError,
)


def test_authorization_error_handler_returns_team_specific_detail(
    caplog,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/teams")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="alice",
            action="can_update_agents",
            resource=Resource.TEAM,
        )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/teams")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You are not allowed to manage agents in this team. Ask a team admin or editor."
    }
    assert "Authorization denied" in caplog.text
    assert "alice" not in caplog.text


def test_authorization_error_handler_humanizes_generic_resource_action() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/documents")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="alice",
            action="read:global",
            resource=Resource.DOCUMENTS,
        )

    response = TestClient(app, raise_server_exceptions=False).get("/documents")

    assert response.status_code == 403
    assert response.json() == {"detail": "You are not allowed to read global document."}


def test_authorization_error_handler_does_not_label_a_team_subject_as_a_user(
    caplog,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/capability")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="team-1",
            action="can_use",
            resource=Resource.CAPABILITY,
            subject_type=Resource.TEAM,
            subject_id="team-1",
        )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/capability")

    assert response.status_code == 403
    assert "Authorization denied" in caplog.text
    assert "team-1" not in caplog.text


def test_authorization_error_handler_distinguishes_actor_from_team_subject(
    caplog,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/capability")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="alice",
            action="can_use",
            resource=Resource.CAPABILITY,
            actor_uid="alice",
            subject_type=Resource.TEAM,
            subject_id="team-1",
        )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/capability")

    assert response.status_code == 403
    assert "Authorization denied" in caplog.text
    assert "alice" not in caplog.text
    assert "team-1" not in caplog.text


def test_generic_exception_handler_returns_internal_server_error(caplog) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        response = TestClient(app, raise_server_exceptions=False).get("/explode")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "Unhandled request failure" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.parametrize("with_actor", [False, True])
def test_authorization_handler_logs_no_identity_or_exception_chain(
    caplog, with_actor: bool
) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    canaries = ("actor-canary", "subject-canary", "cause-canary")

    @app.get("/denied")
    async def denied() -> None:
        raise AuthorizationError(
            user_id=canaries[0],
            action="can_use",
            resource=Resource.APP,
            actor_uid=canaries[0] if with_actor else None,
            subject_type=Resource.TEAM,
            subject_id=canaries[1],
        ) from RuntimeError(canaries[2])

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/denied")

    assert response.status_code == 403
    records = [
        record
        for record in caplog.records
        if record.name == "fred_core.common.fastapi_handlers"
    ]
    assert [record.getMessage() for record in records] == ["Authorization denied"]
    for record in records:
        assert not record.args
        assert record.exc_info is None
        rendered = logging.Formatter().format(record)
        assert all(canary not in rendered for canary in canaries)


def test_generic_handler_logs_no_request_or_chained_exception_details(caplog) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    canaries = ("route-canary", "query-canary", "error-canary", "cause-canary")

    @app.get("/route-canary")
    async def failure() -> None:
        raise RuntimeError(canaries[2]) from ValueError(canaries[3])

    with caplog.at_level(logging.ERROR):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/route-canary?key=query-canary"
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    records = [
        record
        for record in caplog.records
        if record.name == "fred_core.common.fastapi_handlers"
    ]
    assert [record.getMessage() for record in records] == ["Unhandled request failure"]
    for record in records:
        assert not record.args
        assert record.exc_info is None
        rendered = logging.Formatter().format(record)
        assert all(canary not in rendered for canary in canaries)


def test_authorization_error_is_a_permission_error() -> None:
    """A ReBAC denial raised via `check_permission_or_raise` must be catchable by
    any call site's plain `except PermissionError` — the standard denial -> 403
    mapping used across the codebase — without that call site needing its own
    `except AuthorizationError` clause. Without this, a route with only
    `except PermissionError: ... except Exception: 500` (e.g. the tabular
    controller) turns a real denial into an unhandled 500."""
    exc = AuthorizationError(user_id="alice", action="read", resource=Resource.TAGS)
    assert isinstance(exc, PermissionError)


def test_local_permission_error_handler_still_catches_authorization_error() -> None:
    """Reproduces the exact shape of a route that has its own local exception
    chain (`except PermissionError -> 403`, `except Exception -> 500`) instead of
    relying on the app-wide `AuthorizationError` handler above — the pattern in
    `tabular/controller.py`. Before `AuthorizationError` inherited from
    `PermissionError`, this fell through to the generic 500 branch."""
    app = FastAPI()

    @app.get("/query")
    async def denied() -> None:
        try:
            raise AuthorizationError(
                user_id="alice", action="read", resource=Resource.TAGS
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    response = TestClient(app, raise_server_exceptions=False).get("/query")
    assert response.status_code == 403


def test_a_denial_from_an_unconsultable_dependency_is_a_server_side_failure() -> None:
    """A dependency that could not answer says nothing about the caller. Reported
    as a client refusal it hides an outage from availability alerting."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/unavailable")
    async def denied() -> None:
        raise StandingAuthorizationError(unavailable=True)

    response = TestClient(app, raise_server_exceptions=False).get("/unavailable")

    assert response.status_code == 503


def _app_raising(exc: AuthorizationError) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/denied")
    async def denied() -> None:
        raise exc

    return app


def test_a_standing_refusal_reads_differently_from_a_permission_refusal() -> None:
    """Told only "not allowed", a person whose account was disabled goes looking
    for a permission that was never the problem."""
    standing = TestClient(
        _app_raising(StandingAuthorizationError()), raise_server_exceptions=False
    ).get("/denied")
    permission = TestClient(
        _app_raising(
            AuthorizationError(
                user_id="a-person", action="read:global", resource=Resource.DOCUMENTS
            )
        ),
        raise_server_exceptions=False,
    ).get("/denied")

    assert standing.status_code == 403 and permission.status_code == 403
    assert standing.json()["detail"] != permission.json()["detail"]
    assert "standing" in standing.json()["detail"].lower()


def test_a_bounded_detail_names_no_person_team_or_resource() -> None:
    response = TestClient(
        _app_raising(StandingAuthorizationError()), raise_server_exceptions=False
    ).get("/denied")

    detail = response.json()["detail"]
    assert "a-person" not in detail
    assert "organization" not in detail.lower()


def test_an_unavailable_dependency_does_not_claim_the_person_lacks_access() -> None:
    """The dependency never decided, so asserting a refusal would be a guess."""
    response = TestClient(
        _app_raising(StandingAuthorizationError(unavailable=True)),
        raise_server_exceptions=False,
    ).get("/denied")

    assert response.status_code == 503
    assert "not allowed" not in response.json()["detail"].lower()


def _denial_record(caplog, exc: AuthorizationError):
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        TestClient(_app_raising(exc), raise_server_exceptions=False).get("/denied")
    records = [
        record
        for record in caplog.records
        if record.name == "fred_core.common.fastapi_handlers"
    ]
    assert len(records) == 1
    return records[0]


def test_the_denial_record_separates_the_three_causes(caplog) -> None:
    """Undiagnosable otherwise: a disabled account, a missing permission and an
    unreachable dependency are the same 403 with the same message."""
    standing = _denial_record(caplog, StandingAuthorizationError())
    permission = _denial_record(
        caplog,
        AuthorizationError(
            user_id="a-person", action="read:global", resource=Resource.DOCUMENTS
        ),
    )
    unavailable = _denial_record(caplog, StandingAuthorizationError(unavailable=True))

    causes = [
        getattr(record, "denial_cause", None)
        for record in (standing, permission, unavailable)
    ]
    assert len(set(causes)) == 3, causes
    assert getattr(standing, "decision_reached") is True
    assert getattr(unavailable, "decision_reached") is False
    assert getattr(permission, "action") == "read:global"
    assert getattr(permission, "resource_type") == Resource.DOCUMENTS.value


def test_the_denial_record_carries_no_identifier(caplog) -> None:
    canaries = ("actor-canary", "subject-canary")
    record = _denial_record(
        caplog,
        AuthorizationError(
            user_id=canaries[0],
            action="can_use",
            resource=Resource.APP,
            actor_uid=canaries[0],
            subject_type=Resource.TEAM,
            subject_id=canaries[1],
        ),
    )

    rendered = logging.Formatter().format(record)
    assert all(canary not in rendered for canary in canaries)
    # Also absent from the structured fields a JSON formatter would emit.
    for value in vars(record).values():
        assert all(canary != value for canary in canaries)


class _AuditSink(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def audit():
    sink = _AuditSink()
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    previous_level = audit_logger.level
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(sink)
    yield sink
    audit_logger.removeHandler(sink)
    audit_logger.setLevel(previous_level)


def _audit_events(sink: _AuditSink) -> list[object]:
    return [getattr(record, "audit_event", None) for record in sink.records]


def test_a_standing_refusal_reaches_the_audit_surface(audit) -> None:
    """Standing decides whether a person may act at all, so a refusal on it is
    the same class of fact as a delegation decision and belongs beside them."""
    TestClient(
        _app_raising(StandingAuthorizationError()), raise_server_exceptions=False
    ).get("/denied")

    assert "authorization.standing.refused" in _audit_events(audit)


def test_a_permission_refusal_is_not_audited_as_a_standing_refusal(audit) -> None:
    TestClient(
        _app_raising(
            AuthorizationError(
                user_id="a-person", action="read", resource=Resource.TAGS
            )
        ),
        raise_server_exceptions=False,
    ).get("/denied")

    assert "authorization.standing.refused" not in _audit_events(audit)


def test_the_standing_audit_event_carries_no_person_identifier(audit) -> None:
    TestClient(
        _app_raising(StandingAuthorizationError()), raise_server_exceptions=False
    ).get("/denied")

    for record in audit.records:
        rendered = logging.Formatter().format(record)
        assert "a-person" not in rendered
        assert getattr(record, "outcome", None) is not None
        assert getattr(record, "reason", None) is not None


def test_a_denial_that_names_no_cause_is_reported_as_decided() -> None:
    """Defaulting to undecided would turn every ordinary refusal into an outage
    signal, so a site that says nothing is taken to have decided."""
    response = TestClient(
        _app_raising(StandingAuthorizationError()), raise_server_exceptions=False
    ).get("/denied")

    assert response.status_code == 403


def test_every_cause_still_refuses_the_request() -> None:
    """Reporting changed; the outcome must not. Nothing here may become a grant."""
    causes = (
        StandingAuthorizationError(),
        StandingAuthorizationError(unavailable=True),
        AuthorizationError(user_id="a-person", action="read", resource=Resource.TAGS),
    )

    for exc in causes:
        response = TestClient(_app_raising(exc), raise_server_exceptions=False).get(
            "/denied"
        )
        assert response.status_code >= 400, exc
        assert "detail" in response.json()
