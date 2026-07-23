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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

import duckdb
import pandas as pd
from fred_core import DocumentPermission, KeycloakUser, RebacDisabledResult, is_service_agent
from fred_core.common import OwnerFilter
from fred_core.documents.document_structures import DocumentMetadata

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.content.filesystem_content_store import FileSystemContentStore
from knowledge_flow_backend.features.tabular.artifacts import (
    TabularArtifactV1,
    TabularTableArtifactV1,
    build_default_query_alias,
    read_tabular_artifact,
    read_tabular_multi_artifact,
)
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularDatasetResponse,
    TabularDocumentKind,
    TabularDocumentResponse,
    TabularDocumentSchemaResponse,
    TabularQueryRequest,
    TabularSearchRequest,
    TabularSearchResponse,
    TabularTableMatch,
    TabularTableSchema,
    TabularTableSummary,
)
from knowledge_flow_backend.features.tabular.utils import quote_identifier, quote_string_literal, validate_read_query
from knowledge_flow_backend.features.tag.tag_service import TagService

logger = logging.getLogger(__name__)


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
    Dataset-centric tabular service backed by document metadata and content storage.

    Why this exists:
    - Read-only SQL access must now follow document-level ReBAC rather than
      exposing every ingested table globally.

    How to use:
    - The tabular controller calls `list_documents`, `describe_documents`,
      `get_document_markdown`, and `query_read`; the statistic feature and
      document previews call `list_datasets` and the frame readers.
    - Every method filters datasets through document-level permissions before
      exposing schema or data.
    """

    def __init__(self):
        """
        Wire the shared stores needed by the dataset-centric tabular runtime.

        Why this exists:
        - Tabular listing and querying now depend on metadata, ReBAC, content
          storage, and runtime query configuration at the same time.

        How to use:
        - Instantiate once inside `TabularController`.
        """

        context = ApplicationContext.get_instance()
        self.metadata_store = context.get_metadata_store()
        self.content_store = context.get_content_store()
        self.rebac = context.get_rebac_engine()
        self.tag_service: TagService | None = None
        self.tabular_config = context.get_config().storage.tabular_store

    async def list_datasets(
        self,
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[TabularDatasetResponse]:
        """
        List every tabular dataset the current user is allowed to read.

        Why this exists:
        - The SQL agent and the API both need one document-scoped inventory of
          queryable datasets.
        - Team/personal area scoping must stay aligned with the rest of the
          corpus features, not only with raw document readability.

        How to use:
        - Call from `GET /tabular/datasets`.
        - Optionally pass `owner_filter`, `team_id`, and
          `document_library_tags_ids` to stay inside one active area/library
          scope.
        """

        datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return [self._dataset_to_response(dataset) for dataset in datasets]

    async def list_documents(
        self,
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
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
          `describe_documents(...)` for column-level schemas.
        """

        datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
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
            )
            for document_datasets in self._group_datasets_by_document(datasets).values()
        ]

    async def describe_documents(
        self,
        user: KeycloakUser,
        document_uids: list[str],
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[TabularDocumentSchemaResponse]:
        """
        Return the full table schemas of one or several authorized documents.

        Why this exists:
        - Schema exposure must cover every table of a multi-table workbook,
          not only the first one, and one batch call keeps agent round trips
          low when a query joins several documents.

        How to use:
        - Call from `GET /tabular/documents/schemas` with the document uids
          selected from `list_documents(...)`.
        - Raises `PermissionError` when one requested uid is not readable and
          `FileNotFoundError` when it carries no tabular artifact.
        """

        if not document_uids:
            raise ValueError("At least one document uid is required")

        datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        datasets_by_uid = self._group_datasets_by_document(datasets)
        requested_uids = list(dict.fromkeys(document_uids))

        missing_uids = [document_uid for document_uid in requested_uids if document_uid not in datasets_by_uid]
        if missing_uids:
            permission_checks = await asyncio.gather(*(self.rebac.has_user_permission(user, DocumentPermission.READ, document_uid) for document_uid in missing_uids))
            forbidden_uids = [document_uid for document_uid, allowed in zip(missing_uids, permission_checks) if not allowed]
            if forbidden_uids:
                raise PermissionError(f"Not authorized to read datasets: {', '.join(forbidden_uids)}")
            raise FileNotFoundError(f"Requested tabular datasets were not found: {', '.join(missing_uids)}")

        return [
            TabularDocumentSchemaResponse(
                document_uid=document_uid,
                document_name=datasets_by_uid[document_uid][0].metadata.document_name,
                kind=self._document_kind(datasets_by_uid[document_uid]),
                tables=[self._table_schema(dataset) for dataset in datasets_by_uid[document_uid]],
                source_tag=datasets_by_uid[document_uid][0].metadata.source_tag,
            )
            for document_uid in requested_uids
        ]

    async def get_document_markdown(self, user: KeycloakUser, document_uid: str) -> str:
        """
        Return the `output.md` extraction catalog of one spreadsheet document.

        Why this exists:
        - The spreadsheet markdown summary is the LLM-readable catalog (sheet
          layout, table context, ranges, residuals, exact `query_alias` per
          table); agents on the tabular MCP need it without leaving the
          tabular surface.

        How to use:
        - Call from `GET /tabular/documents/{document_uid}/markdown`.
        - Spreadsheet documents only: raises `FileNotFoundError` when the
          document carries no `tabular_multi_v1` artifact.
        """

        if not await self.rebac.has_user_permission(user, DocumentPermission.READ, document_uid):
            raise PermissionError(f"Not authorized to read dataset '{document_uid}'")
        metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
        if metadata is None:
            raise FileNotFoundError(f"Tabular document '{document_uid}' was not found")
        if read_tabular_multi_artifact(metadata) is None:
            raise FileNotFoundError(f"Document '{document_uid}' is not a spreadsheet document with a markdown catalog")

        # The content service owns preview resolution (output.md lookup) and
        # re-checks document-level ReBAC; the guard above only scopes this
        # route to spreadsheet documents.
        from knowledge_flow_backend.features.content.content_service import ContentService

        return await ContentService().get_markdown_preview(user, document_uid)

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
    def _table_schema(dataset: ResolvedDataset) -> TabularTableSchema:
        """Build the full table view (columns included) exposed by the schemas endpoint."""

        artifact = dataset.artifact
        return TabularTableSchema(
            query_alias=dataset.query_alias,
            sheet=artifact.sheet if isinstance(artifact, TabularTableArtifactV1) else None,
            title=artifact.title if isinstance(artifact, TabularTableArtifactV1) else None,
            row_count=artifact.row_count,
            generated_at=artifact.generated_at,
            columns=artifact.columns,
        )

    async def read_dataset_frame(
        self,
        user: KeycloakUser,
        document_uid: str,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
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
        - Optionally pass `owner_filter`, `team_id`, and selected library tag
          ids when the caller is bound to one active area.
        """

        dataset = await self._get_dataset_or_raise(
            user=user,
            document_uid=document_uid,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return self._load_dataset_frame(dataset=dataset)

    async def read_dataset_preview_frame(
        self,
        user: KeycloakUser,
        document_uid: str,
        *,
        max_rows: int = 200,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
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
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return self._load_dataset_frame(dataset=dataset, max_rows=max_rows)

    async def query_read(
        self,
        user: KeycloakUser,
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
        - Set `owner_filter`, `team_id`, and `document_library_tags_ids` in the
          request when the caller is bound to one active area/library scope.
        """

        available_datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=request.document_library_tags_ids,
            owner_filter=request.owner_filter,
            team_id=request.team_id,
        )
        selected_datasets = await self._select_query_datasets(
            user=user,
            requested_uids=request.dataset_uids,
            available_datasets=available_datasets,
        )
        if not selected_datasets:
            raise ValueError("No authorized tabular datasets are available for this query")

        allowed_aliases = {dataset.query_alias for dataset in selected_datasets}
        sql_query = validate_read_query(request.sql_text, allowed_relations=allowed_aliases)
        tabular_config = self.tabular_config

        started_at = time.perf_counter()
        sql_hash = hashlib.sha256(sql_query.encode("utf-8")).hexdigest()
        effective_max_rows = min(
            request.max_rows or tabular_config.query.default_max_rows,
            tabular_config.query.max_rows,
        )

        connection = duckdb.connect(database=":memory:")
        try:
            await self._mount_datasets(connection=connection, datasets=selected_datasets)
            limited_query = f"SELECT * FROM ({sql_query}) AS fred_result LIMIT {effective_max_rows}"
            with _redacting_query_execution_errors():
                rows_df = connection.execute(limited_query).df()
            rows = rows_df.to_dict(orient="records")
        finally:
            connection.close()

        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "[TABULAR] user=%s datasets=%s aliases=%s sql_sha256=%s rows=%s duration_ms=%.2f",
            user.uid,
            [dataset.metadata.document_uid for dataset in selected_datasets],
            [dataset.query_alias for dataset in selected_datasets],
            sql_hash,
            len(rows),
            duration_ms,
        )

        return RawSQLResponse(
            sql_query=sql_query,
            rows=rows,
            error=None,
            dataset_uids=[dataset.metadata.document_uid for dataset in selected_datasets],
            query_aliases=[dataset.query_alias for dataset in selected_datasets],
        )

    async def search_values(
        self,
        user: KeycloakUser,
        *,
        request: TabularSearchRequest,
    ) -> TabularSearchResponse:
        """
        Locate a keyword across the tables of authorized documents.

        Why this exists:
        - The catalog and schemas expose a workbook's structure but never its
          cell values, so a question about a value forces the agent to scan every
          table one `read_query` at a time — one MCP/LLM round trip per table.
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

        available_datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=request.document_library_tags_ids,
            owner_filter=request.owner_filter,
            team_id=request.team_id,
        )
        selected_datasets = await self._select_query_datasets(
            user=user,
            requested_uids=request.dataset_uids,
            available_datasets=available_datasets,
        )
        if not selected_datasets:
            raise ValueError("No authorized tabular datasets are available for this search")

        started_at = time.perf_counter()
        connection = duckdb.connect(database=":memory:")
        try:
            # Normalize the keyword through the exact same DuckDB expression the
            # column values pass through, so both operands are strictly comparable.
            keyword_probe_sql = f"SELECT {self._normalize_expr(quote_string_literal(raw_keyword))}"
            probe_row = connection.execute(keyword_probe_sql).fetchone()
            normalized_keyword = probe_row[0] if probe_row else None
            if not normalized_keyword:
                raise ValueError("Keyword is empty after normalization; provide a more specific value")

            await self._mount_datasets(connection=connection, datasets=selected_datasets)

            matches: list[TabularTableMatch] = []
            tables_truncated = False
            with _redacting_dataset_read_errors():
                for dataset in selected_datasets:
                    if len(matches) >= request.max_matching_tables:
                        # The cap is reached and at least one more table remains
                        # unscanned: other occurrences may exist beyond what we return.
                        tables_truncated = True
                        break
                    match = self._search_one_table(
                        connection=connection,
                        dataset=dataset,
                        normalized_keyword=normalized_keyword,
                        max_rows_per_table=request.max_rows_per_table,
                    )
                    if match is not None:
                        matches.append(match)
        finally:
            connection.close()

        duration_ms = (time.perf_counter() - started_at) * 1000
        # The keyword itself is not logged: it may carry sensitive terms, exactly
        # as query_read logs a SQL hash rather than the SQL text.
        logger.info(
            "[TABULAR] search user=%s datasets=%s matches=%s tables_truncated=%s duration_ms=%.2f",
            user.uid,
            [dataset.metadata.document_uid for dataset in selected_datasets],
            len(matches),
            tables_truncated,
            duration_ms,
        )

        return TabularSearchResponse(
            keyword=raw_keyword,
            normalized_keyword=normalized_keyword,
            matches=matches,
            tables_truncated=tables_truncated,
            searched_dataset_uids=list(dict.fromkeys(dataset.metadata.document_uid for dataset in selected_datasets)),
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
        rows = rows_df.head(max_rows_per_table).to_dict(orient="records")

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
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[ResolvedDataset]:
        """
        Resolve every readable document that has a tabular artifact.

        Why this exists:
        - Dataset listing, schema lookup, and query execution all need the same
          filtered, alias-stable view of authorized tabular documents.
        - Active team/personal/library scope must be applied before aliases are
          exposed or mounted in DuckDB.

        How to use:
        - Call once per request and reuse the resulting list for downstream
          selection or API formatting.
        - When ReBAC is enabled, the service resolves only the authorized
          document uids instead of scanning the whole metadata catalog.
        - Multi-table documents (spreadsheets carrying `tabular_multi_v1`)
          expand into one dataset per table; authorization stays at the
          document level, upstream of this expansion.
        """

        authorized_document_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)
        scoped_tag_ids = await self._resolve_scope_tag_ids(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )

        if isinstance(authorized_document_ref, RebacDisabledResult):
            visible_documents = await self.metadata_store.get_all_metadata({})
        elif is_service_agent(user):
            # EVAL-AUTH (Solution A), mirrors tag_service.resolve_authorized_tag_ids_in_rebac:
            # the evaluation worker holds no per-user document relations by design, so the
            # per-user READ lookup above is always empty and would zero out every dataset.
            # Authorize via the team-scoped tag set instead; fail closed without one.
            if not scoped_tag_ids:
                return []
            tag_documents = await asyncio.gather(*(self.metadata_store.get_metadata_in_tag(tag_id) for tag_id in scoped_tag_ids))
            visible_documents = [metadata for documents in tag_documents for metadata in documents]
        else:
            authorized_ids = [document.id for document in authorized_document_ref]
            if not authorized_ids:
                return []
            visible_documents = await self.metadata_store.get_metadata_by_uids(authorized_ids)

        resolved_datasets: list[ResolvedDataset] = []
        used_aliases: set[str] = set()

        def _claim_alias(base_alias: str) -> str:
            query_alias = base_alias
            suffix = 2
            while query_alias in used_aliases:
                query_alias = f"{base_alias}_{suffix}"
                suffix += 1
            used_aliases.add(query_alias)
            return query_alias

        for metadata in visible_documents:
            if scoped_tag_ids is not None and not (set(metadata.tags.tag_ids or []) & scoped_tag_ids):
                continue

            artifact = read_tabular_artifact(metadata)
            if artifact is not None:
                resolved_datasets.append(
                    ResolvedDataset(
                        metadata=metadata,
                        artifact=artifact,
                        query_alias=_claim_alias(build_default_query_alias(metadata.document_uid, metadata.document_name)),
                    )
                )
                continue

            multi_artifact = read_tabular_multi_artifact(metadata)
            if multi_artifact is None:
                continue
            for table in multi_artifact.tables:
                # The stored alias was computed at ingestion time with the
                # shared deterministic helper; `_claim_alias` only guards the
                # theoretical cross-document collision.
                claimed_alias = _claim_alias(table.query_alias)
                if claimed_alias != table.query_alias:
                    logger.warning(
                        "[TABULAR] alias collision: table %s of document %s served as %s, diverging from the output.md catalog alias %s",
                        table.table_id,
                        metadata.document_uid,
                        claimed_alias,
                        table.query_alias,
                    )
                resolved_datasets.append(
                    ResolvedDataset(
                        metadata=metadata,
                        artifact=table,
                        query_alias=claimed_alias,
                    )
                )

        return resolved_datasets

    async def _get_dataset_or_raise(
        self,
        *,
        user: KeycloakUser,
        document_uid: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> ResolvedDataset:
        """
        Return one authorized dataset or raise the appropriate access/not-found error.

        Why this exists:
        - DataFrame reads (statistic feature, document previews) need one clear
          path that does not leak unauthorized datasets.
        - Active team/personal/library scope must be enforced consistently for
          direct dataset access.

        How to use:
        - Pass the current user and target document uid.
        - For multi-table documents the first table wins: frame reads predate
          table-level addressing (tracked as INGEST-05).
        """

        datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        dataset_by_uid: dict[str, ResolvedDataset] = {}
        for dataset in datasets:
            dataset_by_uid.setdefault(dataset.metadata.document_uid, dataset)
        if document_uid in dataset_by_uid:
            return dataset_by_uid[document_uid]

        if not await self.rebac.has_user_permission(user, DocumentPermission.READ, document_uid):
            raise PermissionError(f"Not authorized to read dataset '{document_uid}'")
        raise FileNotFoundError(f"Tabular dataset '{document_uid}' was not found")

    async def _select_query_datasets(
        self,
        *,
        user: KeycloakUser,
        requested_uids: list[str] | None,
        available_datasets: list[ResolvedDataset],
    ) -> list[ResolvedDataset]:
        """
        Resolve the dataset subset requested for one SQL query or value search.

        Why this exists:
        - Query and search callers may scope execution to a subset of readable
          datasets, and both must return `403` when the user is not allowed to
          read an explicitly requested document.

        How to use:
        - Pass the full readable dataset list from `_resolve_authorized_datasets`
          and the caller-requested document uids (`None`/empty selects all).
        - Requesting one multi-table document uid selects every table of that
          document.
        """

        if not requested_uids:
            return available_datasets

        requested_uids = list(dict.fromkeys(requested_uids))
        datasets_by_uid: dict[str, list[ResolvedDataset]] = {}
        for dataset in available_datasets:
            datasets_by_uid.setdefault(dataset.metadata.document_uid, []).append(dataset)

        missing_uids = [document_uid for document_uid in requested_uids if document_uid not in datasets_by_uid]
        if missing_uids:
            permission_checks = await asyncio.gather(*(self.rebac.has_user_permission(user, DocumentPermission.READ, document_uid) for document_uid in missing_uids))
            forbidden_uids = [document_uid for document_uid, allowed in zip(missing_uids, permission_checks) if not allowed]
            if forbidden_uids:
                logger.warning("[TABULAR] user=%s requested forbidden datasets=%s", user.uid, forbidden_uids)
                raise PermissionError(f"Not authorized to read datasets: {', '.join(forbidden_uids)}")
            raise FileNotFoundError(f"Requested tabular datasets were not found: {', '.join(missing_uids)}")

        return [dataset for document_uid in requested_uids for dataset in datasets_by_uid[document_uid]]

    async def _resolve_scope_tag_ids(
        self,
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None,
        owner_filter: OwnerFilter | None,
        team_id: str | None,
    ) -> set[str] | None:
        """
        Resolve the active tabular scope to one authorized tag-id set.

        Why this exists:
        - Tabular access must follow the same library and team/personal scope
          rules as vector search.

        How to use:
        - Call before filtering document metadata.
        - Returns `None` when no extra tabular scope is active, so callers can
          keep the simpler document-level ReBAC behavior.
        """

        if owner_filter is None and not document_library_tags_ids:
            return None

        authorized_tag_ids = await self._get_tag_service().list_authorized_tags_ids(
            user,
            owner_filter,
            team_id,
        )
        if document_library_tags_ids:
            return set(document_library_tags_ids) & authorized_tag_ids
        return authorized_tag_ids

    def _get_tag_service(self) -> TagService:
        """
        Return the tag service only when tabular scope resolution needs it.

        Why this exists:
        - Default tabular reads should still work in lightweight/offline test
          environments that do not bootstrap the full tag backend.

        How to use:
        - Call from helpers that resolve `owner_filter`, `team_id`, or library
          tag ids.
        """

        if self.tag_service is None:
            self.tag_service = TagService()
        return self.tag_service

    async def _mount_datasets(
        self,
        *,
        connection: duckdb.DuckDBPyConnection,
        datasets: list[ResolvedDataset],
    ) -> None:
        """
        Mount authorized Parquet datasets as temporary DuckDB views.

        Why this exists:
        - DuckDB is not the security boundary; only the views registered in the
          session are visible to the query.

        How to use:
        - Call on a fresh in-memory connection before executing one SQL query.
        """

        dataset_locations: list[tuple[ResolvedDataset, str]] = []
        for dataset in datasets:
            location = self._resolve_dataset_location(dataset.artifact.object_key)
            dataset_locations.append((dataset, location))

        if any(self._requires_httpfs(location) for _, location in dataset_locations):
            self._ensure_httpfs_ready(connection)

        with _redacting_dataset_read_errors():
            for dataset, location in dataset_locations:
                connection.from_parquet(location).create_view(dataset.query_alias)

    def _resolve_dataset_location(self, object_key: str) -> str:
        """
        Resolve one content-store object to a DuckDB-readable location.

        Why this exists:
        - Remote object stores use backend-internal presigned URLs through
          DuckDB `httpfs`.
        - The local filesystem content store used in local development and
          offline tests should expose a direct file path instead of emulating a
          remote download flow.

        How to use:
        - Call while mounting the per-query DuckDB session.
        """

        tabular_config = self.tabular_config
        try:
            return self.content_store.get_presigned_url_internal(
                object_key,
                expires=timedelta(seconds=tabular_config.query.internal_presigned_ttl_seconds),
            )
        except NotImplementedError:
            return self._resolve_local_dataset_path(object_key)

    def _resolve_local_dataset_path(self, object_key: str) -> str:
        """
        Resolve one dataset artifact to its real local filesystem path.

        Why this exists:
        - The local filesystem content store does not expose presigned URLs.
        - Local development and test setups should still query tabular
          artifacts directly from disk.

        How to use:
        - Called only when the content store does not support presigned URLs.
        """

        if isinstance(self.content_store, FileSystemContentStore):
            local_path = self.content_store.object_root / object_key.lstrip("/")
            if not local_path.exists():
                raise FileNotFoundError(f"Tabular artifact '{object_key}' was not found in local content storage")
            return str(local_path)

        raise TabularDatasetAccessUnsupportedError(
            "Unsupported operation: tabular dataset reads require a backend-internal "
            "signed URL or a local filesystem content store. The active content "
            f"store ({type(self.content_store).__name__}) provides neither for "
            "DuckDB Parquet access."
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

    def _load_dataset_frame(
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
        - Keeping that logic in one helper avoids preview-specific drift.

        How to use:
        - Pass a resolved dataset from `_get_dataset_or_raise(...)`.
        - Optionally set `max_rows` to limit the returned preview size.

        Example:
        - `frame = self._load_dataset_frame(dataset=dataset, max_rows=200)`
        """
        connection = duckdb.connect(database=":memory:")
        try:
            location = self._resolve_dataset_location(dataset.artifact.object_key)
            if self._requires_httpfs(location):
                self._ensure_httpfs_ready(connection)

            with _redacting_dataset_read_errors():
                relation = connection.from_parquet(location)
                if max_rows is not None:
                    relation = relation.limit(max_rows)
                return relation.df()
        finally:
            connection.close()
