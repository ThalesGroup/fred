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

"""Tests that signed URLs never leak through DuckDB read errors (FILES-06)."""

import duckdb
import pytest

from knowledge_flow_backend.features.tabular.service import (
    TabularDatasetReadError,
    TabularQueryError,
    _redact_signed_urls,
    _redacting_dataset_read_errors,
    _redacting_query_execution_errors,
)

_GCS_SIGNED_URL = (
    "https://storage.googleapis.com/fred-objects/tabular/datasets/d/r/data.parquet?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=signer%40p.iam.gserviceaccount.com&X-Goog-Signature=deadbeefcafe"
)


def test_redacts_gcs_v4_signed_url():
    """A GCS V4 signed URL (signature included) is replaced wholesale."""
    redacted = _redact_signed_urls(f"IO Error: HTTP HEAD failed for '{_GCS_SIGNED_URL}'")

    assert "X-Goog-Signature" not in redacted
    assert "storage.googleapis.com" not in redacted
    assert "<redacted-signed-url>" in redacted


def test_redacts_s3_minio_presigned_url():
    """The same guard covers S3/MinIO presigned URLs, not just GCS."""
    url = "https://minio.internal/app-bucket/data.parquet?X-Amz-Signature=abc123"

    redacted = _redact_signed_urls(f"IO Error reading {url}")

    assert "X-Amz-Signature" not in redacted
    assert "<redacted-signed-url>" in redacted


def test_leaves_messages_without_urls_untouched():
    """Local paths and plain messages pass through unchanged."""
    message = "Parser Error: syntax error at or near 'SELEC' (/var/data/d/r/data.parquet)"

    assert _redact_signed_urls(message) == message


def test_context_manager_wraps_and_redacts_duckdb_error():
    """A DuckDB read error becomes a redacted TabularDatasetReadError."""
    with pytest.raises(TabularDatasetReadError) as exc_info:
        with _redacting_dataset_read_errors():
            raise duckdb.Error(f"IO Error: could not read '{_GCS_SIGNED_URL}'")

    assert "<redacted-signed-url>" in str(exc_info.value)
    assert "X-Goog-Signature" not in str(exc_info.value)


def test_context_manager_severs_cause_so_url_cannot_resurface():
    """The original (un-redacted) exception must not survive in the chain.

    The controller logs failures with logger.exception(...); a retained
    __cause__/__context__ carrying the signed URL would leak it into logs.
    """
    with pytest.raises(TabularDatasetReadError) as exc_info:
        with _redacting_dataset_read_errors():
            raise duckdb.Error(f"IO Error: could not read '{_GCS_SIGNED_URL}'")

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_context_manager_passes_through_non_duckdb_errors():
    """Non-DuckDB errors (e.g. unsupported-store) are not swallowed or wrapped."""
    with pytest.raises(ValueError, match="unrelated"):
        with _redacting_dataset_read_errors():
            raise ValueError("unrelated")


# ---------------------------------------------------------------------------
# Query-execution error classification: invalid SQL -> 400, IO failure -> 500
# ---------------------------------------------------------------------------


def test_query_execution_maps_binder_error_to_client_error():
    """An invalid-SQL binder error (e.g. LIKE on a numeric column) becomes a
    TabularQueryError so the controller returns HTTP 400, not a 500."""
    with pytest.raises(TabularQueryError) as exc_info:
        with _redacting_query_execution_errors():
            raise duckdb.BinderException("Binder Error: No function matches '~~(BIGINT, STRING_LITERAL)'")

    # ValueError subclass → controller maps it to 400 via its ValueError branch.
    assert isinstance(exc_info.value, ValueError)
    # Not a server read error, so it never reaches the generic 500 path.
    assert not isinstance(exc_info.value, TabularDatasetReadError)


def test_query_execution_keeps_io_error_as_server_error():
    """A DuckDB IO error during execution stays a TabularDatasetReadError (500)
    and is still redacted."""
    with pytest.raises(TabularDatasetReadError) as exc_info:
        with _redacting_query_execution_errors():
            raise duckdb.IOException(f"IO Error: could not read '{_GCS_SIGNED_URL}'")

    assert "<redacted-signed-url>" in str(exc_info.value)
    assert "X-Goog-Signature" not in str(exc_info.value)
    # An IO failure is a server fault, not a client (ValueError) error.
    assert not isinstance(exc_info.value, ValueError)


def test_query_execution_redacts_and_severs_cause_on_client_error():
    """Defense in depth: a query-authoring error is redacted and its cause severed
    before it is returned to the caller, exactly like read errors."""
    with pytest.raises(TabularQueryError) as exc_info:
        with _redacting_query_execution_errors():
            raise duckdb.CatalogException(f"Catalog Error near '{_GCS_SIGNED_URL}'")

    assert "<redacted-signed-url>" in str(exc_info.value)
    assert "storage.googleapis.com" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
