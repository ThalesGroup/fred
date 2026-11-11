# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The artifact reader names the setting of a key the store refused, never the key."""

from __future__ import annotations

import pytest
from fred_core.common.platform_failure import PlatformFailure
from fred_core.history.history_schema import FailureOrigin, ToolFailureCode
from minio.error import S3Error
from urllib3 import HTTPResponse
from urllib3.exceptions import NewConnectionError

from fred_knowledge.artifacts.contracts import Artifact
from fred_knowledge.artifacts.reader import ArtifactReader
from fred_knowledge.configuration import ArtifactStorageConfig

ACCESS_KEY = "wrong-access-key-value"


class _Refusing:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def get_object(self, *_args: object) -> object:
        raise self.error


def _reader(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> ArtifactReader:
    monkeypatch.setenv("KF_ARTIFACT_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("KF_ARTIFACT_SECRET_KEY", "wrong-secret-value")
    reader = ArtifactReader(
        ArtifactStorageConfig(
            endpoint="https://storage.example",
            bucket="app-content-documents",
            access_key_env="KF_ARTIFACT_ACCESS_KEY",
            secret_key_env="KF_ARTIFACT_SECRET_KEY",  # pragma: allowlist secret
        )
    )
    reader.client = _Refusing(error)  # type: ignore[assignment]
    return reader


def _s3(code: str) -> S3Error:
    return S3Error(HTTPResponse(status=403), code, "refused", "/b/k", "r", "h")


ARTIFACT = Artifact(path="output.md", size=1, sha256="0" * 64)


@pytest.mark.parametrize(
    ("error", "code", "setting"),
    [
        (_s3("InvalidAccessKeyId"), ToolFailureCode.misconfigured, "KF_ARTIFACT_ACCESS_KEY"),
        (_s3("SignatureDoesNotMatch"), ToolFailureCode.misconfigured, "KF_ARTIFACT_SECRET_KEY"),
        (NewConnectionError(None, "refused"), ToolFailureCode.service_busy, None),  # type: ignore[arg-type]
    ],
)
def test_a_refused_key_or_an_unreachable_store_is_classified_at_the_reader(monkeypatch: pytest.MonkeyPatch, error: BaseException, code: ToolFailureCode, setting: str | None) -> None:
    with pytest.raises(PlatformFailure) as raised:
        _reader(monkeypatch, error).read_bytes("prefix/", ARTIFACT)
    failure = raised.value.failure
    assert (failure.origin, failure.code, failure.setting) == (FailureOrigin.object_storage, code, setting)
    assert raised.value.__cause__ is error
    assert ACCESS_KEY not in repr(failure)


def test_a_missing_object_keeps_its_own_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(S3Error):
        _reader(monkeypatch, _s3("NoSuchKey")).read_bytes("prefix/", ARTIFACT)
