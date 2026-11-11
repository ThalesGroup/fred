# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""
A dependency refused the platform's configuration or cannot be reached.

Why this module exists:
- the client of a dependency is the only place that knows which dependency
  failed and, for a refused credential, which setting supplied it. It raises
  ``PlatformFailure`` there; one HTTP handler turns it into a 502 or 503 whose
  body says the origin, the code and the setting, never the dependency's text.
- the dependency error codes that mean "credentials refused" or "unreachable"
  are listed here once. A message text is never compared.

How to use it:
- at the client: ``failure = object_storage_failure(error, ...)``; raise it
  ``from error`` when it is not None, re-raise the error otherwise
"""

from __future__ import annotations

from fred_pod.common.structures import OPENSEARCH_PASSWORD_ENV, POSTGRES_PASSWORD_ENV
from minio.error import S3Error
from opensearchpy.exceptions import (
    AuthenticationException,
    AuthorizationException,
)
from opensearchpy.exceptions import ConnectionError as SearchConnectionError
from urllib3.exceptions import HTTPError as StorageTransportError

from fred_core.history.history_schema import (
    FailureOrigin,
    ToolFailure,
    ToolFailureCode,
)

# A dependency refused the configuration: its operator must correct it.
MISCONFIGURED_STATUS = 502
# A dependency cannot be reached: a later attempt may succeed.
UNAVAILABLE_STATUS = 503

# S3 error codes for refused credentials. A signature mismatch is the secret key.
_S3_ACCESS_KEY_REFUSED = frozenset({"InvalidAccessKeyId"})
_S3_SECRET_KEY_REFUSED = frozenset({"SignatureDoesNotMatch"})
_S3_IDENTITY_REFUSED = frozenset({"AccessDenied"})
# PostgreSQL SQLSTATE codes at connection time.
_PG_PASSWORD_REFUSED = frozenset({"28P01"})  # invalid_password
_PG_IDENTITY_REFUSED = frozenset({"28000"})  # invalid_authorization_specification
_PG_UNAVAILABLE = frozenset(
    {"57P03", "53300"}  # cannot_connect_now, too_many_connections
)


class PlatformFailure(Exception):
    """One dependency failure, already classified where its client caught it."""

    def __init__(
        self,
        origin: FailureOrigin,
        code: ToolFailureCode,
        *,
        setting: str | None = None,
    ) -> None:
        if code not in (ToolFailureCode.misconfigured, ToolFailureCode.service_busy):
            raise ValueError("a platform failure is a misconfiguration or an outage")
        self.failure = ToolFailure(code=code, origin=origin, setting=setting)
        self.status = (
            MISCONFIGURED_STATUS
            if code is ToolFailureCode.misconfigured
            else UNAVAILABLE_STATUS
        )
        super().__init__(f"{origin.value}: {code.value}")


def _misconfigured(origin: FailureOrigin, setting: str | None) -> PlatformFailure:
    return PlatformFailure(origin, ToolFailureCode.misconfigured, setting=setting)


def _unavailable(origin: FailureOrigin) -> PlatformFailure:
    return PlatformFailure(origin, ToolFailureCode.service_busy)


def object_storage_failure(
    error: BaseException, *, access_key_setting: str, secret_key_setting: str
) -> PlatformFailure | None:
    """An S3 client error, given the settings that supplied its two keys."""
    origin = FailureOrigin.object_storage
    if isinstance(error, StorageTransportError):
        return _unavailable(origin)
    if not isinstance(error, S3Error):
        return None
    if error.code in _S3_ACCESS_KEY_REFUSED:
        return _misconfigured(origin, access_key_setting)
    if error.code in _S3_SECRET_KEY_REFUSED:
        return _misconfigured(origin, secret_key_setting)
    if error.code in _S3_IDENTITY_REFUSED:
        return _misconfigured(origin, None)
    return None


def search_index_failure(error: BaseException) -> PlatformFailure | None:
    """An OpenSearch client error; its password comes from one environment variable."""
    origin = FailureOrigin.search_index
    if isinstance(error, AuthenticationException):
        return _misconfigured(origin, OPENSEARCH_PASSWORD_ENV)
    if isinstance(error, AuthorizationException):
        return _misconfigured(origin, None)
    if isinstance(error, SearchConnectionError):
        return _unavailable(origin)
    return None


def database_failure(error: BaseException) -> PlatformFailure | None:
    """A PostgreSQL connection error; its password comes from one environment variable."""
    origin = FailureOrigin.database
    if isinstance(error, OSError):
        # Refused, unresolved or timed-out connection: asyncpg raises it bare.
        return _unavailable(origin)
    state = getattr(error, "sqlstate", None)
    if state in _PG_PASSWORD_REFUSED:
        return _misconfigured(origin, POSTGRES_PASSWORD_ENV)
    if state in _PG_IDENTITY_REFUSED:
        return _misconfigured(origin, None)
    if state in _PG_UNAVAILABLE:
        return _unavailable(origin)
    return None
