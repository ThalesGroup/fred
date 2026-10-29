# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID

import duckdb
import pandas as pd
from fred_core.documents.access import PublishedArtifact, SpaceNotFoundError, SpacePendingDeletionError, published_tabular_documents, resolve_scope
from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from fred_core.documents.selection import DocumentScope
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.manager_processing.artifacts import safe_path
from knowledge_flow_backend.features.manager_processing.contracts import Artifact
from knowledge_flow_backend.features.tabular.artifacts import (
    TabularArtifactV1,
    TabularTableArtifactV1,
    build_default_query_alias,
    describe_numeric_column,
    read_tabular_artifact,
    read_tabular_multi_artifact,
)
from knowledge_flow_backend.features.tabular.execution import (
    DuckDBAbortHandle,
    close_duckdb_connection,
    open_duckdb_connection,
    run_duckdb_job,
)
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularColumnSchema,
    TabularDatasetResponse,
    TabularDocumentDescriptionResponse,
    TabularDocumentKind,
    TabularDocumentResponse,
    TabularQueryRequest,
    TabularSearchRequest,
    TabularSearchResponse,
    TabularTableMatch,
    TabularTableSchema,
    TabularTableSummary,
)
from knowledge_flow_backend.features.tabular.utils import dataframe_to_records, quote_identifier, quote_string_literal, validate_read_query
from knowledge_flow_backend.security.weaver_admission import _space_error, require_space_read

logger = logging.getLogger(__name__)


def forbidden_datasets_message(document_uids: Sequence[str]) -> str:
    """Explain ambiguous ReBAC denials without disclosing document existence."""

    return (
        f"Not authorized to read datasets: {', '.join(document_uids)}. "
        "These values are either not readable by you or not valid document uids - "
        "call list_tabular_documents to get valid document_uid values "
        "(a document uid is an opaque id, not a file name and not a SQL table alias)."
    )


@dataclass(frozen=True)
class ResolvedDataset:
    """
    Authorized dataset ready to be exposed or mounted in DuckDB.

    Why this exists:
    - The service needs one internal structure carrying the metadata record, the
      stored tabular artifact, and the stable SQL alias at the same time.

    How to use:
    - Build these with `_resolve_authorized_datasets(...)`.
    - Convert them to API payloads or mount them in DuckDB for one query.
    """

    metadata: DocumentMetadata
    artifact: TabularArtifactV1
    query_alias: str
    source_kind: Literal["corpus", "conversation_attachment"] = "corpus"
    catalog: PublishedArtifact | None = None


class TabularDatasetAccessUnsupportedError(RuntimeError):
    """
    Raised when a tabular artifact cannot be exposed to DuckDB.

    Why this exists:
    - Tabular reads need either a backend-internal signed URL or a local file
      path. Some content stores, notably GCS before internal V4 signing lands,
      support object streams but not DuckDB-readable locations.

    How to use:
    - Let controllers map this to an explicit unsupported-operation response.
    """


class TabularDatasetReadError(RuntimeError):
    """
    Raised when DuckDB fails to read a tabular artifact.

    Why this exists:
    - A failed Parquet read echoes the full object location — including a
      backend-internal V4 signed URL with its signature — in the DuckDB/`httpfs`
      exception text. Surfacing that verbatim would leak a temporary credential
      into logs and API error responses.
    - This error carries a redacted message and severs the original cause so the
      signed URL cannot escape through the exception chain.

    How to use:
    - Raised by `_redacting_dataset_read_errors()`; controllers map it to a
      generic 500 like any other read failure.
    """


class TabularQueryError(ValueError):
    """
    Raised when DuckDB rejects a caller-supplied read query for an authoring reason.

    Why this exists:
    - A binder/parser/catalog/type error (e.g. `LIKE` on a numeric column, an
      unknown column, or a syntax error) means the caller's SQL is invalid — not
      that the server failed. It must surface as an HTTP 400, not a 500 with a
      stack trace: the failure is expected (an LLM caller reads the message and
      rewrites its query), and logging it as a 500 is noise that hides real
      outages.
    - Subclassing `ValueError` lets the controller map it to 400 through the same
      branch it already uses for other invalid-input errors.

    How to use:
    - Raised by `_redacting_query_execution_errors()` around the query `execute`;
      carries a redacted message safe to return to the caller.
    """


# Matches any http(s) URL up to the first whitespace or quote. Broad on purpose:
# it redacts GCS V4 (`X-Goog-Signature`) and S3/MinIO (`X-Amz-Signature`) signed
# URLs alike, and local file paths never match.
_OBJECT_URL_RE = re.compile(r"https?://[^\s'\"]+")


def _redact_signed_urls(message: str) -> str:
    """Replace every http(s) object URL in a message with a fixed placeholder."""
    return _OBJECT_URL_RE.sub("<redacted-signed-url>", message)


@contextmanager
def _redacting_dataset_read_errors():
    """Re-raise DuckDB/`httpfs` read errors with signed URLs stripped.

    Why this exists:
    - DuckDB embeds the object location in IO error messages, so a transient
      signing or network failure would otherwise print the signed URL.

    How to use:
    - Wrap only the DuckDB calls that touch remote dataset locations
      (`from_parquet`, query execution). `from None` severs the original
      exception so its un-redacted text cannot resurface in the cause chain.
    """
    try:
        yield
    except duckdb.OutOfMemoryException:
        # Same reasoning as the query wrapper: a scan that blows the per-query
        # budget is the caller asking for too much, not a server failure.
        logger.warning("[TABULAR] dataset read exceeded its memory budget")
        raise TabularQueryError("Reading this dataset exceeded the per-query memory budget. Scope the request to fewer datasets.") from None
    except duckdb.Error as exc:
        raise TabularDatasetReadError(_redact_signed_urls(str(exc))) from None


@contextmanager
def _redacting_query_execution_errors():
    """Classify DuckDB errors raised while executing a caller-supplied SQL query.

    Why this exists:
    - Query execution fails in two very different ways. Either the SQL is invalid
      (binder/parser/catalog/type error → the caller's fault → HTTP 400), or a
      backing Parquet read fails (IO/`httpfs` error → server-side → HTTP 500).
      The first must not be logged as a 500 stack trace: it is expected traffic
      (the LLM caller self-corrects) and treating it as a server fault is pure
      log noise that also hides real outages and skews availability metrics.

    How to use:
    - Wrap only the DuckDB call that runs the user's SQL. Mounting and plain
      Parquet preview reads keep `_redacting_dataset_read_errors` (IO only).
      `from None` severs the original cause so an un-redacted signed URL cannot
      resurface in the chain, exactly as the sibling helper does.
    """
    try:
        yield
    except duckdb.OutOfMemoryException:
        # Spilling is disabled on purpose (see execution.py), so an over-budget
        # query fails instead of silently writing gigabytes to the container's
        # filesystem. That makes this a caller fault — the query asked for more
        # than one request is allowed to use — and it must read as 400, not as a
        # 500 with a stack trace, so an LLM caller can narrow and retry. The
        # DuckDB text is dropped rather than redacted: it names the configured
        # limit and advises setting `temp_directory`, neither of which is the
        # caller's business.
        logger.warning("[TABULAR] read query exceeded its memory budget")
        raise TabularQueryError("Query exceeded the per-query memory budget. Add filters, aggregate, or select fewer columns.") from None
    except (duckdb.ProgrammingError, duckdb.DataError) as exc:
        message = _redact_signed_urls(str(exc))
        logger.warning("[TABULAR] read query rejected by DuckDB: %s", message)
        raise TabularQueryError(message) from None
    except duckdb.Error as exc:
        raise TabularDatasetReadError(_redact_signed_urls(str(exc))) from None


# Below this length a keyword is too generic to locate anything useful; the
# value-locator rejects it rather than matching a large fraction of every table.
_MIN_KEYWORD_LENGTH = 2


class TabularService:
    """
    Tabular engine backed by authorized Weaver publications.

    Why this exists:
    - Read-only SQL follows the shared space, publication and document-selection
      boundary before any Parquet table is opened.

    How to use:
    - The tabular controller calls `list_documents`, `describe_documents`, and
      `query_read`; the statistic feature and document previews call
      `list_datasets` and the frame readers.
    - Every method applies the shared Weaver access rules before
      exposing schema or data.
    """

    def __init__(self, *, space_id: UUID, document_scope: DocumentScope):
        context = ApplicationContext.get_instance()
        self.engine = context.get_pg_async_engine()
        self.artifact_reader = context.get_published_artifact_reader()
        self.space_id = space_id
        self.document_scope = document_scope
        self.tabular_config = context.get_config().storage.tabular_store

    async def list_datasets(
        self,
        user: AssertedUser,
    ) -> list[TabularDatasetResponse]:
        """
        List every tabular dataset the current user is allowed to read.

        Why this exists:
        - The SQL agent and the API both need one document-scoped inventory of
          queryable datasets.
        - Team/personal area scoping must stay aligned with the rest of the
          corpus features, not only with raw document readability.

        How to use:
        - The service requires the server-bound space and document scope.
        """

        datasets = await self._resolve_authorized_datasets(
            user,
        )
        return [self._dataset_to_response(dataset) for dataset in datasets]

    async def list_documents(
        self,
        user: AssertedUser,
    ) -> list[TabularDocumentResponse]:
        """
        List every tabular document the current user is allowed to read.

        Why this exists:
        - Agents pick sources at document level: one CSV maps to one table,
          one Excel workbook to several. The per-table dataset listing
          repeated the document identity once per table.

        How to use:
        - Call from `GET /tabular/documents`.
        - Table columns are intentionally absent; follow up with
          `describe_documents(...)` for the extraction catalog and typed tables.
        """

        datasets = await self._resolve_authorized_datasets(
            user,
        )
        return [
            TabularDocumentResponse(
                document_uid=document_datasets[0].metadata.document_uid,
                document_name=document_datasets[0].metadata.document_name,
                kind=self._document_kind(document_datasets),
                tables=[self._table_summary(dataset) for dataset in document_datasets],
                tag_ids=list(document_datasets[0].metadata.tags.tag_ids or []),
                tag_names=list(document_datasets[0].metadata.tags.tag_names or []),
                source_tag=document_datasets[0].metadata.source_tag,
                source_kind=document_datasets[0].source_kind,
            )
            for document_datasets in self._group_datasets_by_document(datasets).values()
        ]

    async def describe_documents(
        self,
        user: AssertedUser,
        document_uids: list[str],
    ) -> list[TabularDocumentDescriptionResponse]:
        """
        Return the catalog and typed tables of authorized tabular documents.

        Why this exists:
        - One batch call covers every table of a multi-table workbook and its
          extraction context, keeping agent round trips low.

        How to use:
        - Call from `GET /tabular/documents/schemas` with document uids
          selected from `list_documents(...)`.
        - Raises `PermissionError` when one requested uid is not readable and
          `FileNotFoundError` when it carries no tabular artifact.
        """

        if not document_uids:
            raise ValueError("At least one document uid is required")

        datasets = await self._resolve_authorized_datasets(
            user,
            document_uids=document_uids,
        )
        datasets_by_uid = self._group_datasets_by_document(datasets)
        requested_uids = list(dict.fromkeys(document_uids))

        missing_uids = [document_uid for document_uid in requested_uids if document_uid not in datasets_by_uid]
        if missing_uids:
            raise PermissionError(forbidden_datasets_message(missing_uids))

        spreadsheet_uids = [document_uid for document_uid in requested_uids if self._document_kind(datasets_by_uid[document_uid]) == "spreadsheet"]
        read_limit = asyncio.Semaphore(8)

        async def read_catalog(document_uid: str) -> tuple[str, str]:
            catalog = datasets_by_uid[document_uid][0].catalog
            if catalog is None:
                raise FileNotFoundError("Published spreadsheet catalog is missing")
            async with read_limit:
                content = await asyncio.to_thread(self.artifact_reader.read_bytes, catalog.prefix, Artifact(path="output.md", size=catalog.size, sha256=catalog.sha256))
            return document_uid, content.decode("utf-8")

        ordered_datasets = [dataset for document_uid in requested_uids for dataset in datasets_by_uid[document_uid]]
        max_selected = self.tabular_config.query.max_selected_datasets
        if len(ordered_datasets) > max_selected:
            raise ValueError(f"Description references {len(ordered_datasets)} datasets, above the limit of {max_selected}; request fewer documents or increase max_selected_datasets")
        catalogs = dict(await asyncio.gather(*(read_catalog(document_uid) for document_uid in spreadsheet_uids)))
        described_columns = await self._describe_columns(ordered_datasets)
        tables_by_uid: dict[str, list[TabularTableSchema]] = {}
        for dataset, columns in zip(ordered_datasets, described_columns, strict=True):
            tables_by_uid.setdefault(dataset.metadata.document_uid, []).append(self._table_schema(dataset, columns))
        return [
            TabularDocumentDescriptionResponse(
                document_uid=document_uid,
                document_name=datasets_by_uid[document_uid][0].metadata.document_name,
                kind=self._document_kind(datasets_by_uid[document_uid]),
                markdown=catalogs.get(document_uid),
                tables=tables_by_uid[document_uid],
                source_tag=datasets_by_uid[document_uid][0].metadata.source_tag,
            )
            for document_uid in requested_uids
        ]

    async def _describe_columns(self, datasets: list[ResolvedDataset]) -> list[list[TabularColumnSchema]]:
        """Read categorical values and numeric bounds from authorized Parquet tables."""

        query_config = self.tabular_config.query

        def _job(handle: DuckDBAbortHandle) -> list[list[TabularColumnSchema]]:
            connection = open_duckdb_connection(handle, config=query_config)
            try:
                results: list[list[TabularColumnSchema]] = []
                httpfs_ready = False
                for dataset in datasets:
                    handle.raise_if_aborted()
                    columns = [column.model_copy(update={"sample_values": None, "min_value": None, "max_value": None}) for column in dataset.artifact.columns]
                    numeric = [(index, column) for index, column in enumerate(columns) if column.dtype in {"integer", "float"}]
                    categorical = [(index, column) for index, column in enumerate(columns) if column.dtype == "string" and column.is_categorical is True]
                    location = self._resolve_dataset_location(dataset.artifact.object_key)
                    if self._requires_httpfs(location) and not httpfs_ready:
                        self._ensure_httpfs_ready(connection)
                        httpfs_ready = True
                    with _redacting_dataset_read_errors():
                        connection.from_parquet(location).create_view("tabular_description_table", replace=True)
                        if numeric:
                            aggregates = []
                            for _, column in numeric:
                                identifier = quote_identifier(column.name)
                                aggregates.extend((f"MIN({identifier}) FILTER (WHERE isfinite({identifier}))", f"MAX({identifier}) FILTER (WHERE isfinite({identifier}))"))
                            bounds = connection.execute(f"SELECT {', '.join(aggregates)} FROM tabular_description_table").fetchone()  # nosec B608 — quoted stored column names
                            if bounds is not None:
                                for position, (index, column) in enumerate(numeric):
                                    columns[index] = describe_numeric_column(column, bounds[2 * position], bounds[2 * position + 1])
                        for index, column in categorical:
                            handle.raise_if_aborted()
                            identifier = quote_identifier(column.name)
                            rows = connection.execute(
                                f"SELECT DISTINCT {identifier} FROM tabular_description_table WHERE {identifier} IS NOT NULL"  # nosec B608 — quoted stored column name
                            ).fetchall()
                            columns[index] = column.model_copy(update={"sample_values": sorted(str(row[0]) for row in rows) or None})
                        if not numeric and not categorical:
                            connection.execute("SELECT COUNT(*) FROM tabular_description_table").fetchone()
                    results.append(columns)
                return results
            finally:
                close_duckdb_connection(handle, connection)

        return await run_duckdb_job(_job, config=query_config, operation="description")

    @staticmethod
    def _group_datasets_by_document(datasets: list[ResolvedDataset]) -> dict[str, list[ResolvedDataset]]:
        """Group resolved datasets by document uid, preserving resolution order."""

        datasets_by_uid: dict[str, list[ResolvedDataset]] = {}
        for dataset in datasets:
            datasets_by_uid.setdefault(dataset.metadata.document_uid, []).append(dataset)
        return datasets_by_uid

    @staticmethod
    def _document_kind(document_datasets: list[ResolvedDataset]) -> TabularDocumentKind:
        """Return the document kind from the artifact type of its tables."""

        return "spreadsheet" if isinstance(document_datasets[0].artifact, TabularTableArtifactV1) else "csv"

    @staticmethod
    def _table_summary(dataset: ResolvedDataset) -> TabularTableSummary:
        """Build the lightweight table view exposed by the document list."""

        artifact = dataset.artifact
        return TabularTableSummary(
            query_alias=dataset.query_alias,
            sheet=artifact.sheet if isinstance(artifact, TabularTableArtifactV1) else None,
            title=artifact.title if isinstance(artifact, TabularTableArtifactV1) else None,
            row_count=artifact.row_count,
            generated_at=artifact.generated_at,
        )

    @staticmethod
    def _table_schema(dataset: ResolvedDataset, columns: list[TabularColumnSchema]) -> TabularTableSchema:
        """Build the full table view (columns included) exposed by the schemas endpoint."""

        artifact = dataset.artifact
        return TabularTableSchema(
            query_alias=dataset.query_alias,
            sheet=artifact.sheet if isinstance(artifact, TabularTableArtifactV1) else None,
            title=artifact.title if isinstance(artifact, TabularTableArtifactV1) else None,
            row_count=artifact.row_count,
            generated_at=artifact.generated_at,
            columns=columns,
        )

    async def read_dataset_frame(
        self,
        user: AssertedUser,
        document_uid: str,
    ) -> pd.DataFrame:
        """
        Load one authorized dataset into a pandas DataFrame.

        Why this exists:
        - Some callers need in-memory pandas DataFrames rather than SQL results.
        - Reusing the dataset-centric resolver keeps those reads aligned with
          the same document-level permissions as SQL queries.
        - Team/personal scoping must also apply to these DataFrame reads.

        How to use:
        - Pass the current user and the dataset `document_uid` selected from
          `list_datasets`.
        - The constructor-bound Weaver scope applies to direct reads too.
        """

        dataset = await self._get_dataset_or_raise(
            user=user,
            document_uid=document_uid,
        )
        return await self._load_dataset_frame(dataset=dataset)

    async def read_dataset_preview_frame(
        self,
        user: AssertedUser,
        document_uid: str,
        *,
        max_rows: int = 200,
    ) -> pd.DataFrame:
        """
        Load only the first rows of one authorized dataset into pandas.

        Why this exists:
        - Document previews should reuse the indexed Parquet artifact instead
          of persisting a duplicate `table.csv` copy in content storage.
        - Preview endpoints need a bounded read that stays cheap for large
          datasets.

        How to use:
        - Pass the current user and target dataset uid.
        - Tune `max_rows` when a caller needs a smaller or larger tabular
          preview window.
        """
        if max_rows < 1:
            raise ValueError("max_rows must be greater than 0")

        dataset = await self._get_dataset_or_raise(
            user=user,
            document_uid=document_uid,
        )
        return await self._load_dataset_frame(dataset=dataset, max_rows=max_rows)

    async def query_read(
        self,
        user: AssertedUser,
        *,
        request: TabularQueryRequest,
    ) -> RawSQLResponse:
        """
        Execute one read-only SQL query against authorized datasets only.

        Why this exists:
        - The runtime must mount only the caller's readable datasets in a fresh
          DuckDB session and keep every query read-only.
        - Team/personal area scoping must flow through SQL execution exactly as
          it does for corpus retrieval.

        How to use:
        - Provide a validated `TabularQueryRequest`.
        - Dataset IDs can narrow the constructor-bound Weaver scope.
        """

        available_datasets = await self._resolve_authorized_datasets(user, document_uids=request.dataset_uids)
        selected_datasets = await self._select_query_datasets(
            user=user,
            requested_uids=request.dataset_uids,
            available_datasets=available_datasets,
        )
        if not selected_datasets:
            raise ValueError("No authorized tabular datasets are available for this query")

        allowed_aliases = {dataset.query_alias for dataset in selected_datasets}
        query_config = self.tabular_config.query
        effective_max_rows = min(
            request.max_rows or query_config.default_max_rows,
            query_config.max_rows,
        )

        def _job(handle: DuckDBAbortHandle) -> tuple[str, list[dict], list[ResolvedDataset]]:
            connection = open_duckdb_connection(handle, config=query_config)
            try:
                handle.raise_if_aborted()
                # Validation parses the SQL and already knows which authorized
                # aliases it touches, so it runs here — inside the worker, since
                # it opens its own DuckDB connection — and its result decides
                # what gets mounted.
                validated = validate_read_query(request.sql_text, allowed_relations=allowed_aliases)
                mounted_datasets = self._datasets_to_mount(
                    selected_datasets=selected_datasets,
                    referenced_relations=validated.referenced_relations,
                )
                self._mount_datasets(connection=connection, datasets=mounted_datasets, handle=handle)
                handle.raise_if_aborted()
                limited_query = f"SELECT * FROM ({validated.sql}) AS fred_result LIMIT {effective_max_rows}"
                with _redacting_query_execution_errors():
                    rows_df = connection.execute(limited_query).df()
                return validated.sql, dataframe_to_records(rows_df), mounted_datasets
            finally:
                close_duckdb_connection(handle, connection)

        started_at = time.perf_counter()
        sql_query, rows, mounted_datasets = await run_duckdb_job(_job, config=query_config, operation="query")

        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "[TABULAR] user=%s datasets=%s aliases=%s sql_sha256=%s rows=%s duration_ms=%.2f",
            user.uid,
            [dataset.metadata.document_uid for dataset in mounted_datasets],
            [dataset.query_alias for dataset in mounted_datasets],
            hashlib.sha256(sql_query.encode("utf-8")).hexdigest(),
            len(rows),
            duration_ms,
        )

        return RawSQLResponse(
            sql_query=sql_query,
            rows=rows,
            error=None,
            dataset_uids=[dataset.metadata.document_uid for dataset in mounted_datasets],
            query_aliases=[dataset.query_alias for dataset in mounted_datasets],
        )

    async def search_values(
        self,
        user: AssertedUser,
        *,
        request: TabularSearchRequest,
    ) -> TabularSearchResponse:
        """
        Locate a keyword across the tables of authorized documents.

        Why this exists:
        - The catalog and schemas expose a workbook's structure but never its
          cell values, so a question about a value forces the agent to scan every
          table one `query_tabular_documents` at a time — one MCP/LLM round trip per table.
          This runs that fan-out once, server-side, and returns which tables and
          columns hold the value plus a bounded sample of matching rows, so the
          agent can then issue one targeted query.

        How to use:
        - Provide a precise `keyword`; scope with `request.dataset_uids` when
          possible. Matching is a normalized substring test — case, accents and
          whitespace insensitive, decimal comma treated as point — over every
          column cast to text, so numeric columns are searchable too.
        - Authorization, scoping and mounting reuse the same path as
          `query_read`; the result is bounded by `max_rows_per_table` and
          `max_matching_tables`, with truncation signalled explicitly.
        """

        raw_keyword = request.keyword.strip()
        if len(raw_keyword) < _MIN_KEYWORD_LENGTH:
            raise ValueError(f"Keyword must be at least {_MIN_KEYWORD_LENGTH} characters long")

        available_datasets = await self._resolve_authorized_datasets(user, document_uids=request.dataset_uids)
        selected_datasets = await self._select_query_datasets(
            user=user,
            requested_uids=request.dataset_uids,
            available_datasets=available_datasets,
        )
        if not selected_datasets:
            raise ValueError("No authorized tabular datasets are available for this search")

        query_config = self.tabular_config.query
        # A search has no SQL to narrow the selection with, so the cap is the only
        # bound on how many tables one request may scan. Truncating here bounds
        # mounting too, which on a remote store is one Parquet metadata fetch per
        # dataset before any scanning starts.
        scanned_datasets = selected_datasets[: query_config.max_selected_datasets]
        selection_truncated = len(scanned_datasets) < len(selected_datasets)
        # A multi-table workbook can be cut mid-document by the cap. Reporting
        # its uid as searched would tell the caller "the value is not in this
        # document" when tables of it were never opened, so a partially scanned
        # document is left out of `searched_dataset_uids` entirely.
        dropped_document_uids = {dataset.metadata.document_uid for dataset in selected_datasets[query_config.max_selected_datasets :]}
        if selection_truncated:
            logger.info(
                "[TABULAR] search selection capped user=%s selected=%s scanned=%s",
                user.uid,
                len(selected_datasets),
                len(scanned_datasets),
            )

        def _job(handle: DuckDBAbortHandle) -> tuple[str, list[TabularTableMatch], bool]:
            connection = open_duckdb_connection(handle, config=query_config)
            try:
                handle.raise_if_aborted()
                # Normalize the keyword through the exact same DuckDB expression the
                # column values pass through, so both operands are strictly comparable.
                keyword_probe_sql = f"SELECT {self._normalize_expr(quote_string_literal(raw_keyword))}"
                probe_row = connection.execute(keyword_probe_sql).fetchone()
                probe_keyword = probe_row[0] if probe_row else None
                if not probe_keyword:
                    raise ValueError("Keyword is empty after normalization; provide a more specific value")

                self._mount_datasets(connection=connection, datasets=scanned_datasets, handle=handle)

                matches: list[TabularTableMatch] = []
                tables_truncated = selection_truncated
                with _redacting_dataset_read_errors():
                    for dataset in scanned_datasets:
                        if len(matches) >= request.max_matching_tables:
                            # The cap is reached and at least one more table remains
                            # unscanned: other occurrences may exist beyond what we return.
                            tables_truncated = True
                            break
                        handle.raise_if_aborted()
                        match = self._search_one_table(
                            connection=connection,
                            dataset=dataset,
                            normalized_keyword=probe_keyword,
                            max_rows_per_table=request.max_rows_per_table,
                        )
                        if match is not None:
                            matches.append(match)
                return probe_keyword, matches, tables_truncated
            finally:
                close_duckdb_connection(handle, connection)

        started_at = time.perf_counter()
        normalized_keyword, matches, tables_truncated = await run_duckdb_job(_job, config=query_config, operation="search")

        duration_ms = (time.perf_counter() - started_at) * 1000
        # The keyword itself is not logged: it may carry sensitive terms, exactly
        # as query_read logs a SQL hash rather than the SQL text.
        logger.info(
            "[TABULAR] search user=%s datasets=%s matches=%s tables_truncated=%s duration_ms=%.2f",
            user.uid,
            [dataset.metadata.document_uid for dataset in scanned_datasets],
            len(matches),
            tables_truncated,
            duration_ms,
        )

        return TabularSearchResponse(
            keyword=raw_keyword,
            normalized_keyword=normalized_keyword,
            matches=matches,
            tables_truncated=tables_truncated,
            searched_dataset_uids=[document_uid for document_uid in dict.fromkeys(dataset.metadata.document_uid for dataset in scanned_datasets) if document_uid not in dropped_document_uids],
        )

    @staticmethod
    def _normalize_expr(expr: str) -> str:
        """
        Wrap a text-yielding SQL expression with the search normalization chain.

        Why this exists:
        - Keyword search must be insensitive to case, accents and whitespace and
          treat a decimal comma as a point, applied identically to the cell value
          and the keyword so the two are comparable.

        How to use:
        - Pass any SQL expression that yields text, e.g. `CAST(col AS VARCHAR)` or
          a quoted string literal. Returns the normalized SQL expression.
        """

        # lower -> strip accents -> remove every whitespace char -> comma to point.
        return f"replace(regexp_replace(strip_accents(lower({expr})), '\\s', '', 'g'), ',', '.')"

    def _search_one_table(
        self,
        *,
        connection: duckdb.DuckDBPyConnection,
        dataset: ResolvedDataset,
        normalized_keyword: str,
        max_rows_per_table: int,
    ) -> TabularTableMatch | None:
        """
        Scan one mounted table for the normalized keyword.

        Why this exists:
        - The locator needs, per table, both the exhaustive set of columns that
          contain the keyword (one aggregate pass) and a bounded sample of
          matching rows (one limited pass).

        How to use:
        - Call on a table already mounted in `connection` under
          `dataset.query_alias`. Returns `None` when the table holds no match.
        """

        columns = [column.name for column in dataset.artifact.columns]
        if not columns:
            return None

        alias_sql = quote_identifier(dataset.query_alias)
        keyword_literal = quote_string_literal(normalized_keyword)
        column_conditions: list[str] = []
        for column_name in columns:
            cast_expr = f"CAST({quote_identifier(column_name)} AS VARCHAR)"
            column_conditions.append(f"contains({self._normalize_expr(cast_expr)}, {keyword_literal})")

        # Pass 1 — which columns match anywhere in the table (exhaustive). Every
        # relation, column and literal below is machine-generated and quoted with
        # quote_identifier / quote_string_literal, never caller text.
        count_select = ", ".join(f"count(*) FILTER (WHERE {condition}) AS m{index}" for index, condition in enumerate(column_conditions))
        count_sql = f"SELECT {count_select} FROM {alias_sql}"  # nosec B608 — machine-built; relation/columns quoted, no caller text
        count_row = connection.execute(count_sql).fetchone()
        matched_columns = [name for index, name in enumerate(columns) if count_row and count_row[index]]
        if not matched_columns:
            return None

        # Pass 2 — a bounded sample of matching rows (one extra row detects truncation).
        where_any_column = " OR ".join(column_conditions)
        sample_sql = f"SELECT * FROM {alias_sql} WHERE {where_any_column} LIMIT {max_rows_per_table + 1}"  # nosec B608 — machine-built; relation/columns quoted, no caller text
        rows_df = connection.execute(sample_sql).df()
        row_truncated = len(rows_df) > max_rows_per_table
        rows = dataframe_to_records(rows_df.head(max_rows_per_table))

        artifact = dataset.artifact
        is_table_artifact = isinstance(artifact, TabularTableArtifactV1)
        return TabularTableMatch(
            document_uid=dataset.metadata.document_uid,
            document_name=dataset.metadata.document_name,
            query_alias=dataset.query_alias,
            sheet=artifact.sheet if is_table_artifact else None,
            title=artifact.title if is_table_artifact else None,
            matched_columns=matched_columns,
            rows=rows,
            row_truncated=row_truncated,
        )

    async def _resolve_authorized_datasets(
        self,
        user: AssertedUser,
        *,
        document_uids: list[str] | None = None,
    ) -> list[ResolvedDataset]:
        await require_space_read(user, self.space_id)
        try:
            ids = [UUID(uid) for uid in document_uids] if document_uids is not None else None
        except ValueError:
            raise PermissionError(forbidden_datasets_message(document_uids or [])) from None
        try:
            async with self.engine.connect() as conn:
                scope = await resolve_scope(conn, self.space_id, self.document_scope)
            cursor = UUID(int=0)
            resolved = []
            while True:
                # Release SQL connections before object-store I/O. No permission cache.
                async with self.engine.connect() as conn:
                    documents, next_cursor = await published_tabular_documents(conn, scope, after=cursor, document_ids=ids)
                for start in range(0, len(documents), 8):
                    batches = await asyncio.gather(*(asyncio.to_thread(self._read_published_datasets, doc) for doc in documents[start : start + 8]))
                    resolved.extend(dataset for batch in batches for dataset in batch)
                if next_cursor is None:
                    break
                cursor = next_cursor
            aliases = set()
            for dataset in resolved:
                if dataset.query_alias in aliases:
                    raise ValueError("Published tabular aliases collide")
                aliases.add(dataset.query_alias)
            return resolved
        except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
            raise _space_error(exc) from None

    def _read_published_datasets(self, document) -> list[ResolvedDataset]:
        manifest = document.artifacts
        metadata_artifact = manifest.get("metadata.json")
        if metadata_artifact is None or not 0 < metadata_artifact.size <= 2_097_152:
            raise ValueError("Invalid published tabular metadata")
        metadata = DocumentMetadata.model_validate_json(
            self.artifact_reader.read_bytes(
                metadata_artifact.prefix,
                Artifact(path="metadata.json", size=metadata_artifact.size, sha256=metadata_artifact.sha256),
            )
        )
        uid = str(document.document_id)
        if metadata.document_uid != uid or metadata.file.sha256 != document.source_revision:
            raise ValueError("Published tabular identity mismatch")
        if metadata.processing.stages.get(ProcessingStage.SQL_INDEXED) != ProcessingStatus.DONE:
            raise ValueError("Published tabular indexing is incomplete")
        metadata.identity.document_name = document.name
        single = read_tabular_artifact(metadata)
        multi = read_tabular_multi_artifact(metadata)
        tables = [single] if single is not None else list(multi.tables) if multi is not None else []
        result = []
        for table in tables:
            stored = manifest.get(table.object_key)
            if (
                stored is None
                or not safe_path(table.object_key)
                or not table.object_key.startswith("datasets/")
                or not table.object_key.endswith(".parquet")
                or table.format != "parquet"
                or table.dataset_uid != uid
                or table.source_revision != document.source_revision
                or stored.size != table.file_size_bytes
            ):
                raise ValueError("Invalid published tabular artifact")
            result.append(
                ResolvedDataset(
                    metadata=metadata,
                    artifact=table.model_copy(update={"object_key": stored.prefix + table.object_key}),
                    query_alias=table.query_alias if isinstance(table, TabularTableArtifactV1) else build_default_query_alias(uid, document.name),
                    catalog=manifest.get("output.md"),
                )
            )
        return result

    async def _get_dataset_or_raise(self, *, user: AssertedUser, document_uid: str) -> ResolvedDataset:
        datasets = await self._resolve_authorized_datasets(user, document_uids=[document_uid])
        if not datasets:
            raise PermissionError(forbidden_datasets_message([document_uid]))
        # Existing frame/preview contract: the first table of a workbook.
        return datasets[0]

    async def _select_query_datasets(self, *, user: AssertedUser, requested_uids: list[str] | None, available_datasets: list[ResolvedDataset]) -> list[ResolvedDataset]:
        if requested_uids is None:
            return available_datasets
        grouped = self._group_datasets_by_document(available_datasets)
        missing = [uid for uid in requested_uids if uid not in grouped]
        if missing:
            raise PermissionError(forbidden_datasets_message(missing))
        return [dataset for uid in dict.fromkeys(requested_uids) for dataset in grouped[uid]]

    def _datasets_to_mount(
        self,
        *,
        selected_datasets: list[ResolvedDataset],
        referenced_relations: frozenset[str],
    ) -> list[ResolvedDataset]:
        """
        Narrow one authorized selection to the datasets a query actually reads.

        Why this exists:
        - Omitting `dataset_uids` selects every readable dataset, and every
          selected dataset used to be mounted whether or not the SQL referenced
          it. On a remote content store each mount is a Parquet metadata fetch,
          so an unscoped `SELECT 1` against a large tenant paid for hundreds of
          round trips before executing anything. Mounting only the referenced
          relations makes that cost proportional to the query.
        - The remaining cap is a backstop for a query that legitimately joins
          more datasets than one request is allowed to open at once.

        How to use:
        - Pass the authorized selection and `ValidatedReadQuery.referenced_relations`.
        - Raises `ValueError` (HTTP 400) when the query reads no dataset at all,
          or when it reads more than `max_selected_datasets`.
        """

        mounted_datasets = [dataset for dataset in selected_datasets if dataset.query_alias in referenced_relations]
        if not mounted_datasets:
            raise ValueError("Query references no authorized dataset; name at least one dataset alias in the FROM clause")

        max_selected = self.tabular_config.query.max_selected_datasets
        if len(mounted_datasets) > max_selected:
            raise ValueError(f"Query references {len(mounted_datasets)} datasets, above the limit of {max_selected}; narrow dataset_uids or the query")
        return mounted_datasets

    def _mount_datasets(
        self,
        *,
        connection: duckdb.DuckDBPyConnection,
        datasets: list[ResolvedDataset],
        handle: DuckDBAbortHandle,
    ) -> None:
        """Mount authorized Parquet views with exact-path external access.

        Resolve paths and load httpfs before restricting access. Abort checks
        bracket mounts because remote reads can block outside DuckDB execution.
        """

        dataset_locations: list[tuple[ResolvedDataset, str]] = []
        for dataset in datasets:
            handle.raise_if_aborted()
            location = self._resolve_dataset_location(dataset.artifact.object_key)
            dataset_locations.append((dataset, location))

        if any(self._requires_httpfs(location) for _, location in dataset_locations):
            self._ensure_httpfs_ready(connection)

        connection.execute("SET allow_persistent_secrets = false")
        connection.execute("SET allowed_paths = ?", [[location for _, location in dataset_locations]])
        connection.execute("SET enable_external_access = false")

        with _redacting_dataset_read_errors():
            for dataset, location in dataset_locations:
                handle.raise_if_aborted()
                connection.from_parquet(location).create_view(dataset.query_alias)

    def _resolve_dataset_location(self, object_key: str) -> str:
        """Only keys resolved from the published generation reach this method."""
        return self.artifact_reader.client.presigned_get_object(
            self.artifact_reader.bucket,
            object_key,
            expires=timedelta(seconds=self.tabular_config.query.internal_presigned_ttl_seconds),
        )

    def _ensure_httpfs_ready(self, connection: duckdb.DuckDBPyConnection) -> None:
        """
        Ensure DuckDB `httpfs` is available for remote Parquet access.

        Why this exists:
        - The S3-compatible runtime is intentionally `httpfs`-based.
        - Kubernetes/offline deployments preinstall the extension in the image,
          while connected environments may still need one best-effort
          `INSTALL httpfs` before the query can proceed.

        How to use:
        - Call before executing `from_parquet(...)` on HTTP(S) locations.
        """

        try:
            connection.execute("LOAD httpfs")
            return
        except Exception as load_exc:  # noqa: BLE001
            logger.info(
                "[TABULAR] DuckDB httpfs not yet available, trying INSTALL+LOAD: %s",
                load_exc,
            )
        try:
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
        except Exception as install_exc:  # noqa: BLE001
            raise RuntimeError(
                "DuckDB httpfs is required for remote tabular dataset access. Preinstall it in the runtime image for offline/containerized deployments, or allow DuckDB to install extensions at startup in connected environments."
            ) from install_exc

    def _requires_httpfs(self, location: str) -> bool:
        """
        Return whether one dataset location points to an HTTP(S) resource.

        Why this exists:
        - The tabular runtime needs one small predicate to decide when DuckDB
          `httpfs` must be loaded.

        How to use:
        - Pass the location returned by `_resolve_dataset_location(...)`.
        """

        return location.startswith(("http://", "https://"))

    def _dataset_to_response(self, dataset: ResolvedDataset) -> TabularDatasetResponse:
        """
        Convert one resolved dataset into the REST response model.

        Why this exists:
        - The list endpoint should expose one stable, serializable view of
          authorized datasets without leaking the internal content-store key.

        How to use:
        - Use for `GET /tabular/datasets`.
        """

        return TabularDatasetResponse(
            document_uid=dataset.metadata.document_uid,
            document_name=dataset.metadata.document_name,
            query_alias=dataset.query_alias,
            row_count=dataset.artifact.row_count,
            columns=dataset.artifact.columns,
            tag_ids=list(dataset.metadata.tags.tag_ids or []),
            tag_names=list(dataset.metadata.tags.tag_names or []),
            source_tag=dataset.metadata.source_tag,
            generated_at=dataset.artifact.generated_at,
        )

    async def _load_dataset_frame(
        self,
        *,
        dataset: ResolvedDataset,
        max_rows: int | None = None,
    ) -> pd.DataFrame:
        """
        Read one dataset artifact from Parquet into a pandas DataFrame.

        Why this exists:
        - Full dataset reads and preview reads share the same object-location
          resolution and DuckDB/httpfs setup.
        - Keeping that logic in one helper avoids preview-specific drift, and
          means the document-preview route gets the same execution guardrails as
          SQL queries — it shares the process-wide slot budget rather than
          bypassing it.

        How to use:
        - Pass a resolved dataset from `_get_dataset_or_raise(...)`.
        - Optionally set `max_rows` to limit the returned preview size.

        Example:
        - `frame = await self._load_dataset_frame(dataset=dataset, max_rows=200)`
        """

        query_config = self.tabular_config.query

        def _job(handle: DuckDBAbortHandle) -> pd.DataFrame:
            connection = open_duckdb_connection(handle, config=query_config)
            try:
                handle.raise_if_aborted()
                location = self._resolve_dataset_location(dataset.artifact.object_key)
                if self._requires_httpfs(location):
                    self._ensure_httpfs_ready(connection)

                handle.raise_if_aborted()
                with _redacting_dataset_read_errors():
                    relation = connection.from_parquet(location)
                    if max_rows is not None:
                        relation = relation.limit(max_rows)
                    return relation.df()
            finally:
                close_duckdb_connection(handle, connection)

        started_at = time.perf_counter()
        frame = await run_duckdb_job(_job, config=query_config, operation="preview")
        logger.info(
            "[TABULAR] preview dataset=%s rows=%s duration_ms=%.2f",
            dataset.metadata.document_uid,
            len(frame),
            (time.perf_counter() - started_at) * 1000,
        )
        return frame
