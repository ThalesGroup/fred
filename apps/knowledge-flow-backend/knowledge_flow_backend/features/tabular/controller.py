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

import logging
from typing import Annotated, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fred_core import KeycloakUser, get_current_user
from fred_core.common import OwnerFilter

from knowledge_flow_backend.features.tabular.diagnostics import TabularDescriptionNotFound, log_description_failure
from knowledge_flow_backend.features.tabular.execution import (
    TabularCapacityExceededError,
    TabularExecutionTimeoutError,
)
from knowledge_flow_backend.features.tabular.service import (
    TabularDatasetAccessUnsupportedError,
    TabularQueryError,
    TabularService,
)
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularDocumentDescriptionResponse,
    TabularDocumentListResponse,
    TabularDocumentListTableResponse,
    TabularQueryRequest,
    TabularSearchRequest,
    TabularSearchResponse,
)
from knowledge_flow_backend.features.tag.structure import MissingTeamIdError

logger = logging.getLogger(__name__)


class TabularController:
    """API controller for document-centric tabular operations (CSV and spreadsheets)."""

    def __init__(self, router: APIRouter):
        self.service = TabularService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get(
            "/tabular/documents",
            response_model=List[TabularDocumentListResponse],
            response_model_exclude_none=True,
            tags=["Tabular"],
            summary="Discover authorized CSV documents and Excel workbook tables",
            operation_id="list_tabular_documents",
        )
        async def list_documents(
            document_library_tags_ids: Annotated[
                list[str] | None,
                Query(description="Optional library tag IDs used to keep documents inside selected libraries."),
            ] = None,
            owner_filter: Annotated[
                OwnerFilter | None,
                Query(description="Optional ownership scope: 'personal' or 'team'."),
            ] = None,
            team_id: Annotated[
                str | None,
                Query(description="Team ID, required when owner_filter is 'team'."),
            ] = None,
            attachment_uids: Annotated[list[str] | None, Query(max_length=1000, description="Explicit uploader-owned attachment UIDs.")] = None,
            include_session_scope: bool = True,
            include_corpus_scope: bool = True,
            corpus_document_uids: Annotated[list[str] | None, Query()] = None,
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Discover authorized CSV files and Excel workbooks in the current scope.

            Returns document_name, document_uid, source_kind and corpus library
            tag_names. Excel entries also list table aliases, sheets and titles;
            CSV entries have no table list. The runtime supplies conversation
            attachment UIDs and enabled sources. Without attachment scope, only
            corpus documents are listed.

            Copy document_uid values into describe_tabular_documents. Discovery
            does not provide column types: describe every selected document
            before SQL, even if its table aliases are already listed. An empty
            list is a successful discovery with no visible tabular documents.
            """

            try:
                documents = await self.service.list_documents(
                    user,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                    attachment_uids=attachment_uids,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                    corpus_document_uids=corpus_document_uids,
                )
                return [
                    TabularDocumentListResponse(
                        document_uid=document.document_uid,
                        document_name=document.document_name,
                        source_kind=document.source_kind,
                        tag_names=document.tag_names or None,
                        tables=(
                            [
                                TabularDocumentListTableResponse(
                                    query_alias=table.query_alias,
                                    sheet=table.sheet,
                                    title=table.title,
                                )
                                for table in document.tables
                            ]
                            if document.kind == "spreadsheet"
                            else None
                        ),
                    )
                    for document in documents
                ]
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Failed to list tabular documents")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/documents/schemas",
            response_model=List[TabularDocumentDescriptionResponse],
            response_model_exclude_none=True,
            tags=["Tabular"],
            summary="Inspect document catalogs, SQL aliases and column types",
            operation_id="describe_tabular_documents",
        )
        async def describe_documents(
            document_uids: Annotated[
                list[str],
                Query(
                    min_length=1,
                    description="Document UIDs copied exactly from list_tabular_documents or authorized attachments, not filenames or SQL table aliases. Repeat the parameter for several documents.",
                ),
            ],
            table_names: Annotated[
                list[str] | None,
                Query(max_length=1000, description="Optional exact query_alias values or unambiguous sheet/title names. Omit or pass an empty list for all tables. Does not rename SQL aliases."),
            ] = None,
            document_library_tags_ids: Annotated[
                list[str] | None,
                Query(description="Optional library tag IDs used to keep documents inside selected libraries."),
            ] = None,
            owner_filter: Annotated[
                OwnerFilter | None,
                Query(description="Optional ownership scope: 'personal' or 'team'."),
            ] = None,
            team_id: Annotated[
                str | None,
                Query(description="Team ID, required when owner_filter is 'team'."),
            ] = None,
            attachment_uids: Annotated[list[str] | None, Query(max_length=1000, description="Explicit uploader-owned attachment UIDs.")] = None,
            include_session_scope: bool = True,
            include_corpus_scope: bool = True,
            corpus_document_uids: Annotated[list[str] | None, Query()] = None,
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Inspect the catalog, SQL table aliases and column types before querying.

            Pass exact document_uids from authorized discovery, not filenames or
            SQL aliases. Batch several documents when a query will join them.
            For Excel, read markdown first for sheet/table context and residual
            notes, then inspect tables[].columns. CSV has no markdown catalog.
            Describe all tables by default, or select exact table_names to
            inspect only relevant schemas. The workbook catalog stays complete.
            Returned tables include query_alias, exact column names and dtypes.

            Categorical string categorical_values contain all distinct non-null
            values when available: preserve their exact spelling and format in
            filters. Numeric min_value/max_value are finite observed bounds,
            not query answers. Use query_alias values in SQL FROM/JOIN clauses;
            use document UIDs only as document selectors.
            """

            try:
                return await self.service.describe_documents(
                    user,
                    document_uids=document_uids,
                    table_names=table_names,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                    attachment_uids=attachment_uids,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                    corpus_document_uids=corpus_document_uids,
                )
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except TabularDescriptionNotFound as e:
                log_description_failure(e)
                raise HTTPException(status_code=404, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except (TabularCapacityExceededError, TabularExecutionTimeoutError):
                raise
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except TabularDatasetAccessUnsupportedError as e:
                raise HTTPException(status_code=501, detail=str(e))
            except Exception as e:
                logger.exception("Failed to describe tabular documents %s", document_uids)
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/query",
            response_model=RawSQLResponse,
            tags=["Tabular"],
            summary="Run one read-only DuckDB SELECT over discovered tables",
            operation_id="read_query",
        )
        async def raw_sql_read(
            request: TabularQueryRequest = Body(..., description="Read-only DuckDB query over discovered document tables"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Run one read-only DuckDB SELECT after describing every document it reads.

            Use exact discovered query_alias values in FROM/JOIN. dataset_uids
            contains document UIDs; one workbook UID selects all its tables.
            Only referenced authorized tables are mounted. At least one dataset
            alias is required; cross-table/document joins must stay within the
            server's dataset limit. max_rows limits returned rows: compute
            totals and aggregates in SQL instead of inferring them from previews.

            Returns sql_query, rows, error and dataset references. rows=[] with
            error=null is a successful query with zero matching rows and an
            explicit success message. A zero count or null aggregate is still a
            row. Reuse successful results; inspect types/filters before changing
            an unexpectedly empty query instead of repeating it unchanged.

            HTTP 400 requires correcting SQL/arguments; a memory-budget error
            requires a narrower query. HTTP 503 indicates temporary capacity;
            HTTP 504 requires narrowing a query that exceeded its time budget.
            """

            try:
                return await self.service.query_read(user, request=request)
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except (TabularCapacityExceededError, TabularExecutionTimeoutError):
                # Re-raise for the app-level handlers registered in main.py. This
                # branch exists only because of the `except Exception` catch-all
                # below, which would otherwise turn overload into a 500 before
                # the handler ever sees it.
                raise
            except TabularQueryError as e:
                # Invalid SQL (binder/parser/type error) is a caller fault, not a
                # server failure: return 400 without a stack trace. Must precede
                # the ValueError branch since TabularQueryError subclasses it.
                raise HTTPException(status_code=400, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except TabularDatasetAccessUnsupportedError as e:
                raise HTTPException(status_code=501, detail=str(e))
            except Exception as e:
                logger.exception("Read SQL query failed")
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/search",
            response_model=TabularSearchResponse,
            tags=["Tabular"],
            summary="Locate a precise value after inspecting document structure",
            operation_id="search_tabular_values",
        )
        async def search_values(
            request: TabularSearchRequest = Body(..., description="Precise value lookup over previously described document tables"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Locate a precise value when the inspected catalog cannot identify its table.

            Use only after describe_tabular_documents, as a last-resort value
            locator rather than a structure-discovery or aggregation tool.
            Send a specific keyword of at least two characters, preferably with
            dataset_uids scoped to exact document UIDs. One workbook UID covers
            all its tables. Matching ignores case, accents and whitespace;
            numeric columns are searchable too.

            Returns matching tables, columns and sample rows. tables_truncated
            or row_truncated means partial coverage: refine the keyword/scope.
            max_matching_tables and max_rows_per_table bound returned previews.
            Empty matches are a successful search with no matches in the searched
            scope. Use the located table aliases in a subsequent read_query.
            """

            try:
                return await self.service.search_values(user, request=request)
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except (TabularCapacityExceededError, TabularExecutionTimeoutError):
                # Same reason as read_query: the catch-all below would mask these.
                raise
            except TabularQueryError as e:
                # A DuckDB authoring error is a caller fault (400), not a server
                # failure — same classification as read_query.
                raise HTTPException(status_code=400, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except TabularDatasetAccessUnsupportedError as e:
                raise HTTPException(status_code=501, detail=str(e))
            except Exception as e:
                logger.exception("Tabular value search failed")
                raise HTTPException(status_code=500, detail=str(e))
