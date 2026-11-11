# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""A dependency's refusal or outage says its origin, its code and the setting to check."""

from __future__ import annotations

import socket

import pytest
from fred_core.common.platform_failure import (
    PlatformFailure,
    database_failure,
    object_storage_failure,
    search_index_failure,
)
from fred_core.history.history_schema import (
    FailureOrigin,
    ToolFailure,
    ToolFailureCode,
)
from minio.error import S3Error
from opensearchpy.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConnectionError,
    ConnectionTimeout,
    NotFoundError,
)
from pydantic import ValidationError
from urllib3 import HTTPResponse
from urllib3.exceptions import NewConnectionError, ProtocolError, ReadTimeoutError

MISCONFIGURED = ToolFailureCode.misconfigured
UNAVAILABLE = ToolFailureCode.service_busy
KEYS = {
    "access_key_setting": "KF_ARTIFACT_ACCESS_KEY",
    "secret_key_setting": "KF_ARTIFACT_SECRET_KEY",  # nosec B105 # pragma: allowlist secret
}


def _s3(code: str) -> S3Error:
    return S3Error(
        HTTPResponse(status=403),
        code,
        "dependency text that never leaves the log",
        "/app-content-documents/doc/output.md",
        "request",
        "host",
    )


class _DbapiError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("password authentication failed for user")
        self.sqlstate = sqlstate


def _failure(error: PlatformFailure | None) -> tuple[object, ...] | None:
    if error is None:
        return None
    return (error.failure.origin, error.failure.code, error.failure.setting)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            _s3("InvalidAccessKeyId"),
            (FailureOrigin.object_storage, MISCONFIGURED, "KF_ARTIFACT_ACCESS_KEY"),
        ),
        (
            _s3("SignatureDoesNotMatch"),
            (FailureOrigin.object_storage, MISCONFIGURED, "KF_ARTIFACT_SECRET_KEY"),
        ),
        (_s3("AccessDenied"), (FailureOrigin.object_storage, MISCONFIGURED, None)),
        (
            NewConnectionError(None, "refused"),  # type: ignore[arg-type]
            (FailureOrigin.object_storage, UNAVAILABLE, None),
        ),
        (
            ReadTimeoutError(None, "/", "read timed out"),  # type: ignore[arg-type]
            (FailureOrigin.object_storage, UNAVAILABLE, None),
        ),
        (ProtocolError("reset"), (FailureOrigin.object_storage, UNAVAILABLE, None)),
        (_s3("NoSuchKey"), None),
        (ValueError("not a storage error"), None),
    ],
)
def test_object_storage_errors(error: BaseException, expected: object) -> None:
    assert _failure(object_storage_failure(error, **KEYS)) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            AuthenticationException(401, "security_exception", {}),
            (FailureOrigin.search_index, MISCONFIGURED, "OPENSEARCH_PASSWORD"),
        ),
        (
            AuthorizationException(403, "security_exception", {}),
            (FailureOrigin.search_index, MISCONFIGURED, None),
        ),
        (
            ConnectionError("N/A", "refused", OSError()),
            (FailureOrigin.search_index, UNAVAILABLE, None),
        ),
        (
            ConnectionTimeout("TIMEOUT", "timed out", OSError()),
            (FailureOrigin.search_index, UNAVAILABLE, None),
        ),
        (NotFoundError(404, "index_not_found_exception", {}), None),
    ],
)
def test_search_index_errors(error: BaseException, expected: object) -> None:
    assert _failure(search_index_failure(error)) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            _DbapiError("28P01"),
            (FailureOrigin.database, MISCONFIGURED, "FRED_POSTGRES_PASSWORD"),
        ),
        (_DbapiError("28000"), (FailureOrigin.database, MISCONFIGURED, None)),
        (_DbapiError("57P03"), (FailureOrigin.database, UNAVAILABLE, None)),
        (_DbapiError("53300"), (FailureOrigin.database, UNAVAILABLE, None)),
        (ConnectionRefusedError(), (FailureOrigin.database, UNAVAILABLE, None)),
        (socket.gaierror(), (FailureOrigin.database, UNAVAILABLE, None)),
        (TimeoutError(), (FailureOrigin.database, UNAVAILABLE, None)),
        (_DbapiError("42P01"), None),
    ],
)
def test_database_errors(error: BaseException, expected: object) -> None:
    assert _failure(database_failure(error)) == expected


@pytest.mark.parametrize(
    "setting",
    ["kf_artifact_access_key", "KF ARTIFACT", "AKIA/secret-value", "1KEY", "A" * 65],
)
def test_a_setting_is_only_an_environment_variable_name(setting: str) -> None:
    with pytest.raises(ValidationError):
        ToolFailure(code=MISCONFIGURED, setting=setting)


def test_a_setting_names_only_what_a_misconfiguration_must_correct() -> None:
    with pytest.raises(ValidationError):
        ToolFailure(code=UNAVAILABLE, setting="KF_ARTIFACT_ACCESS_KEY")


def test_a_platform_failure_is_only_a_misconfiguration_or_an_outage() -> None:
    with pytest.raises(ValueError):
        PlatformFailure(FailureOrigin.database, ToolFailureCode.service_error)


def test_the_model_reads_the_component_and_the_setting_never_the_dependency_text() -> (
    None
):
    failure = object_storage_failure(_s3("InvalidAccessKeyId"), **KEYS)
    assert failure is not None
    text = failure.failure.platform_explanation() or ""
    assert "document storage" in text
    assert "configuration problem, not a problem with the user's request" in text
    assert "KF_ARTIFACT_ACCESS_KEY" in text
    assert "never leaves the log" not in text
    assert ToolFailure.from_http_status(500).platform_explanation() is None
