import logging
from typing import Annotated, List

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fred_core import KeycloakUser, get_current_user
from fred_core.common import OwnerFilter

from knowledge_flow_backend.features.tabular.service import (
    TabularDatasetAccessUnsupportedError,
    TabularQueryError,
    TabularService,
)
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularDocumentMarkdownResponse,
    TabularDocumentResponse,
    TabularDocumentSchemaResponse,
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
            response_model=List[TabularDocumentResponse],
            tags=["Tabular"],
            summary="List authorized tabular documents (CSV datasets and Excel workbooks)",
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
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            List every tabular document visible to the current user.

            Why this exists:
            - Agents pick sources at document level: one CSV document carries
              one table, one spreadsheet document carries several.
            - Team/personal and library scope must be enforced before table
              aliases are exposed.

            How to use:
            - Call without parameters to retrieve every readable document with
              its queryable tables (`query_alias` per table, no columns).
            - Follow up with `/tabular/documents/schemas` for column detail and
              `/tabular/documents/{uid}/markdown` for a spreadsheet's catalog.
            """

            try:
                return await self.service.list_documents(
                    user,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Failed to list tabular documents")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/documents/schemas",
            response_model=List[TabularDocumentSchemaResponse],
            tags=["Tabular"],
            summary="Describe the tables of one or several authorized tabular documents",
            operation_id="get_tabular_documents_schemas",
        )
        async def describe_documents(
            document_uids: Annotated[
                list[str],
                Query(min_length=1, description="Document UIDs to describe (repeat the parameter for several documents)."),
            ],
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
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Return the full table schemas for one or several authorized documents.

            Why this exists:
            - Schema inspection must expose every table of a multi-table
              workbook and follow the same document-level access rules as
              query execution.
            - It returns each table's columns as (name, dtype): the reliable
              way to confirm exact column names and types, and the only catalog
              available for CSV documents, which have no markdown extraction.
            - One batch call keeps agent round trips low when a SQL query
              joins tables from several documents.

            How to use:
            - Pass one or several `document_uids` from `/tabular/documents`.
            - Reuse the same scope parameters as the list endpoint when the
              caller is bound to one active area.
            """

            try:
                return await self.service.describe_documents(
                    user,
                    document_uids=document_uids,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except TabularDatasetAccessUnsupportedError as e:
                raise HTTPException(status_code=501, detail=str(e))
            except Exception as e:
                logger.exception("Failed to describe tabular documents %s", document_uids)
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/documents/{document_uid}/markdown",
            response_model=TabularDocumentMarkdownResponse,
            tags=["Tabular"],
            summary="Read the markdown extraction catalog of one spreadsheet document",
            operation_id="get_tabular_document_markdown",
        )
        async def get_document_markdown(
            document_uid: str = Path(..., description="Document UID of the spreadsheet to read"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Return the `output.md` extraction catalog of one spreadsheet document.

            Why this exists:
            - The markdown catalog describes each extracted table of the
              workbook: its sheet, title and context, cell ranges, the exact
              `query_alias` to use in SQL, the name of every identified column,
              and any residual text left on the sheet. Because it lists the real
              column names alongside their surrounding context, it is the best
              way to understand what data a workbook actually holds before
              writing SQL — richer than the column-only schemas endpoint.

            How to use:
            - Pass a `document_uid` of kind `spreadsheet` from
              `/tabular/documents`; CSV or other documents return 404.
            """

            try:
                content = await self.service.get_document_markdown(user, document_uid)
                return TabularDocumentMarkdownResponse(document_uid=document_uid, content=content)
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                logger.exception("Failed to read tabular document markdown %s", document_uid)
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/query",
            response_model=RawSQLResponse,
            tags=["Tabular"],
            summary="Execute one read-only SQL query on authorized datasets",
            operation_id="read_query",
        )
        async def raw_sql_read(
            request: TabularQueryRequest = Body(..., description="Dataset-centric SQL query payload"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Execute one read-only SQL query against authorized datasets.

            Why this exists:
            - Dataset-scoped queries now run in an ephemeral DuckDB session with
              only authorized views mounted.

            How to use:
            - Send `sql` and optional `dataset_uids` (document uids; one
              spreadsheet uid mounts every table of the workbook).
            """

            try:
                return await self.service.query_read(user, request=request)
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
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
            summary="Locate a keyword across authorized tabular datasets",
            operation_id="search_tabular_values",
        )
        async def search_values(
            request: TabularSearchRequest = Body(..., description="Keyword value-locator payload"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Locate a precise value across the tables of authorized documents.

            Why this exists:
            - The catalog and schemas describe a workbook's structure but not its
              cell values. This finds which table(s) and column(s) hold a value,
              so an agent can then run one targeted `read_query` instead of
              scanning every table.

            How to use:
            - Send a precise `keyword` and, ideally, a `dataset_uids` subset (one
              spreadsheet uid covers all its tables).
            - Matching is case/accent/whitespace-insensitive over every column;
              numeric columns are searchable too. `tables_truncated` /
              `row_truncated` flag a partial result.
            """

            try:
                return await self.service.search_values(user, request=request)
            except MissingTeamIdError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
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
