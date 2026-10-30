# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Tabular operations bound to the authenticated delegated service's document context."""

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.features.document_scope import document_access_context
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
    return TabularService(space_id=context.space_id, document_scope=context.document_scope)


@contextmanager
def tabular_errors():
    try:
        yield
    except PermissionError:
        raise HTTPException(status_code=403, detail="Dataset access refused; call list_tabular_documents for available documents.") from None
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
            tags=["Tabular"],
            summary="Read extraction catalogs and typed tables of selected documents",
            operation_id="describe_tabular_documents",
        )
        async def describe_documents(
            document_uids: Annotated[
                list[str],
                Query(
                    min_length=1,
                    max_length=1000,
                    description="Document UUIDs from listing, encoded as repeated document_uids query parameters. All requested documents must be in scope; 1 to 1000 identifiers.",
                ),
            ],
            person: AssertedUser = Depends(delegated_person),
            service: TabularService = Depends(tabular_service),
        ):
            """Use document UIDs from list_tabular_documents. Returns exact SQL aliases,
            column types, categorical values and numeric ranges; Excel includes its catalog.
            Every requested document must belong to the active document selection. The
            configured max_selected_datasets also bounds the total tables described;
            a workbook may contain multiple tables. CSV markdown is null; Excel
            returns its published extraction catalog. Category/range analysis is
            subject to the same tabular execution budgets."""
            with tabular_errors():
                return await service.describe_documents(person, document_uids=document_uids)

        @router.post("/tabular/query", response_model=RawSQLResponse, tags=["Tabular"], summary="Execute one read-only SELECT on authorized published datasets", operation_id="query_tabular_documents")
        async def query(request: TabularQueryRequest, person: AssertedUser = Depends(delegated_person), service: TabularService = Depends(tabular_service)):
            """Use exact aliases from describe_tabular_documents. dataset_uids narrows the
            active selection; a workbook UID includes all its tables. SQL must reference
            at least one dataset. Execution, memory, row and dataset limits apply.
            Results are row-limited without a truncation flag or pagination token;
            reaching the row limit does not prove completeness. Dataset, memory,
            concurrency and timeout ceilings come from storage.tabular_store.query.
            Retry capacity 503 with bounded backoff; for 504 narrow the query."""
            with tabular_errors():
                return await service.query_read(person, request=request)

        @router.post("/tabular/search", response_model=TabularSearchResponse, tags=["Tabular"], summary="Locate a precise value in authorized published datasets", operation_id="search_tabular_values")
        async def search(request: TabularSearchRequest, person: AssertedUser = Depends(delegated_person), service: TabularService = Depends(tabular_service)):
            """Case/accent/whitespace-insensitive search, including numeric columns.
            Use dataset_uids to narrow the search. The stripped keyword must have at
            least two characters and must remain nonempty after normalization.
            Up to 5 rows per table and 30 matching tables; callers may lower these
            caps. The configured dataset scan ceiling can further restrict work.
            Inspect tables_truncated and each match's rows_truncated; an empty
            matches list with truncation is not proof the value is absent."""
            with tabular_errors():
                return await service.search_values(person, request=request)
