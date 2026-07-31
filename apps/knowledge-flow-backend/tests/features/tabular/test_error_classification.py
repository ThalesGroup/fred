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

"""
Issue #2182: disabling DuckDB spilling makes `OutOfMemoryException` reachable.

Before the execution guard, an over-budget query silently spilled to disk and
succeeded. It now fails — which is the point — but it must fail as a caller
error (400) rather than a server error (500), or an LLM caller gets no signal to
narrow its query and every attempt logs a stack trace as if the pod were broken.
`duckdb.OutOfMemoryException` derives from `OperationalError`, so it does NOT
hit the `ProgrammingError`/`DataError` branch and needs its own classification.
"""

from __future__ import annotations

import duckdb
import pytest

from knowledge_flow_backend.features.tabular.service import (
    TabularDatasetReadError,
    TabularQueryError,
    _redacting_dataset_read_errors,
    _redacting_query_execution_errors,
)


def test_out_of_memory_is_not_a_programming_error_subclass():
    """Guard the assumption the classification depends on."""

    assert issubclass(duckdb.OutOfMemoryException, duckdb.Error)
    assert not issubclass(duckdb.OutOfMemoryException, duckdb.ProgrammingError)
    assert not issubclass(duckdb.OutOfMemoryException, duckdb.DataError)


def test_query_out_of_memory_surfaces_as_a_caller_error():
    with pytest.raises(TabularQueryError) as excinfo:
        with _redacting_query_execution_errors():
            raise duckdb.OutOfMemoryException(
                "Out of Memory Error: could not allocate block of size 256.0 KiB (244.0 MiB/244.1 MiB used). Database is launched in in-memory mode, set temp_directory='/path/to/tmp.tmp'"
            )

    message = str(excinfo.value)
    assert "memory budget" in message
    # The DuckDB text names the configured limit and advises setting
    # temp_directory; neither belongs in an API response.
    assert "temp_directory" not in message
    assert "244.1 MiB" not in message


def test_dataset_read_out_of_memory_surfaces_as_a_caller_error():
    with pytest.raises(TabularQueryError):
        with _redacting_dataset_read_errors():
            raise duckdb.OutOfMemoryException("Out of Memory Error: failed to offload data block")


def test_other_duckdb_io_errors_still_surface_as_server_errors():
    """The OOM branch must not swallow genuine read failures."""

    with pytest.raises(TabularDatasetReadError):
        with _redacting_dataset_read_errors():
            raise duckdb.IOException("IO Error: could not read https://signed.example.invalid/x?X-Amz-Signature=deadbeef")
