# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Tabular operations bound to the authenticated delegated service's document context."""

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.features.document_scope import document_access_context
from knowledge_flow_backend.features.tabular.diagnostics import TabularDescriptionNotFound, log_description_failure
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularDocumentDescriptionResponse,
    TabularDocumentListResponse,
    TabularDocumentListTableResponse,
    TabularQueryRequest,
    TabularSearchRequest,
    TabularSearchResponse,
)
from knowledge_flow_backend.security.weaver_admission import delegated_person


def tabular_service(context: DocumentAccessContext = Depends(document_access_context)) -> TabularService:
    return TabularService(context=context)


@contextmanager
def tabular_errors():
    try:
        yield
    except PermissionError:
        raise HTTPException(status_code=403, detail="Dataset access refused; call list_tabular_documents for available documents.") from None
    except TabularDescriptionNotFound as exc:
        log_description_failure(exc)
        raise HTTPException(status_code=404, detail="dataset_not_found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dataset_not_found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    # Capacity/timeouts retain the shared 503/504 policy. Infrastructure errors
    # propagate as server failures; never expose their URLs or credentials.


class TabularController:
    def __init__(self, router: APIRouter):
        @router.get(
            "/tabular/documents",
            response_model=list[TabularDocumentListResponse],
            response_model_exclude_none=True,
            tags=["Tabular"],
            summary="List published tabular documents in the active document selection",
            operation_id="list_tabular_documents",
            description="Lists authorized published CSV/Excel documents. Empty selection returns an empty array. No pagination parameter or fixed response-count cap. Excel includes table identities; CSV omits tables in this compact listing. Use describe_tabular_documents to obtain exact SQL aliases and columns.",
        )
        async def list_documents(person: AssertedUser = Depends(delegated_person), service: TabularService = Depends(tabular_service)):
            with tabular_errors():
                documents = await service.list_documents(person)
                return [
                    TabularDocumentListResponse(
                        document_uid=doc.document_uid,
                        document_name=doc.document_name,
                        source_kind=doc.source_kind,
                        tables=[TabularDocumentListTableResponse(query_alias=t.query_alias, sheet=t.sheet, title=t.title) for t in doc.tables] if doc.kind == "spreadsheet" else None,
                    )
                    for doc in documents
                ]

        @router.get(
            "/tabular/documents/schemas",
            response_model=list[TabularDocumentDescriptionResponse],
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
                    max_length=1000,
                    description="Document UUIDs copied exactly from list_tabular_documents, not filenames or SQL table aliases. Repeat the parameter for several documents. All requested documents must be in scope; 1 to 1000 identifiers.",
                ),
            ],
            table_names: Annotated[
                list[str] | None,
                Query(max_length=1000, description="Optional exact query_alias values or unambiguous sheet/title names. Omit or pass an empty list for all tables. Does not rename SQL aliases."),
            ] = None,
            person: AssertedUser = Depends(delegated_person),
            service: TabularService = Depends(tabular_service),
        ):
            """Inspect the catalog, SQL table aliases and column types before querying.

            Pass exact document UIDs from list_tabular_documents; every one must belong
            to the active document selection. Batch several documents when a query will
            join them. For Excel, read the published markdown catalog first, then inspect
            tables[].columns. CSV markdown is null. Describe all tables by default, or
            select table_names to inspect only relevant schemas; the workbook catalog
            stays complete. The configured max_selected_datasets bounds the total tables
            described, and analysis is subject to the same tabular execution budgets.

            Categorical string categorical_values contain all distinct non-null values:
            preserve their exact spelling and format in filters. Numeric min_value and
            max_value are finite observed bounds, not query answers. Use query_alias in
            SQL FROM/JOIN clauses and document UIDs only as document selectors."""
            with tabular_errors():
                return await service.describe_documents(person, document_uids=document_uids, table_names=table_names)

        @router.post("/tabular/query", response_model=RawSQLResponse, tags=["Tabular"], summary="Run one read-only DuckDB SELECT over discovered tables", operation_id="query_tabular_documents")
        async def query(request: TabularQueryRequest, person: AssertedUser = Depends(delegated_person), service: TabularService = Depends(tabular_service)):
            """Run one read-only DuckDB SELECT after describing every document it reads.

            Use exact query_alias values from describe_tabular_documents in FROM/JOIN.
            dataset_uids narrows the active selection; a workbook UID includes all its
            tables. SQL must reference at least one dataset. Execution, memory, row and
            dataset ceilings come from storage.tabular_store.query. Results stop at
            row_limit, without pagination; truncated=true means rows is partial. Compute
            totals and aggregates in SQL instead of inferring them from previews.

            rows=[] with error=null is a successful query with zero matching rows and an
            explicit success message. A zero count or null aggregate is still a row. Reuse
            successful results; inspect types and filters before changing an unexpectedly
            empty query instead of repeating it unchanged.

            HTTP 400 requires correcting SQL or arguments. Retry capacity 503 with bounded
            backoff; for 504 narrow the query."""
            with tabular_errors():
                return await service.query_read(person, request=request)

        @router.post(
            "/tabular/search", response_model=TabularSearchResponse, tags=["Tabular"], summary="Locate a precise value after inspecting document structure", operation_id="search_tabular_values"
        )
        async def search(request: TabularSearchRequest, person: AssertedUser = Depends(delegated_person), service: TabularService = Depends(tabular_service)):
            """Locate a precise value when the inspected catalog cannot identify its table.

            Use only after describe_tabular_documents, as a last-resort value locator
            rather than a structure-discovery or aggregation tool. Matching ignores case,
            accents and whitespace; numeric columns are searchable too. Use dataset_uids
            to narrow the search. The stripped keyword must have at least two characters
            and must remain nonempty after normalization. Up to 5 rows per table and 30
            matching tables; callers may lower these caps. The configured dataset scan
            ceiling can further restrict work. Inspect tables_truncated and each match's
            row_truncated; an empty matches list with truncation is not proof the value is
            absent. Use the located aliases in a subsequent query_tabular_documents."""
            with tabular_errors():
                return await service.search_values(person, request=request)
