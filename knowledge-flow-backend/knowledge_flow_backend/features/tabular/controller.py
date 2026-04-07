import logging
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularDatasetResponse,
    TabularDatasetSchemaResponse,
    TabularQueryRequest,
)

logger = logging.getLogger(__name__)


class TabularController:
    """API controller for dataset-centric tabular operations."""

    def __init__(self, router: APIRouter):
        self.service = TabularService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get(
            "/tabular/datasets",
            response_model=List[TabularDatasetResponse],
            tags=["Tabular"],
            summary="List authorized tabular datasets",
            operation_id="list_tabular_datasets",
        )
        async def list_datasets(user: KeycloakUser = Depends(get_current_user)):
            """
            List every tabular dataset visible to the current user.

            Why this exists:
            - The public tabular REST surface is now document-scoped instead of
              database-scoped.

            How to use:
            - Call without parameters to retrieve authorized datasets and their
              SQL aliases.
            """

            authorize_or_raise(user, Action.READ, Resource.DOCUMENTS)
            try:
                return await self.service.list_datasets(user)
            except Exception as e:
                logger.exception("Failed to list tabular datasets")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/datasets/{document_uid}/schema",
            response_model=TabularDatasetSchemaResponse,
            tags=["Tabular"],
            summary="Describe one authorized tabular dataset",
            operation_id="get_tabular_dataset_schema",
        )
        async def describe_dataset(
            document_uid: str = Path(..., description="Document UID of the dataset to describe"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Return the schema for one authorized tabular dataset.

            Why this exists:
            - Schema inspection must follow the same document-level access rules
              as query execution.

            How to use:
            - Pass the dataset document uid from `/tabular/datasets`.
            """

            authorize_or_raise(user, Action.READ, Resource.DOCUMENTS)
            try:
                return await self.service.describe_dataset(user, document_uid=document_uid)
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                logger.exception("Failed to describe tabular dataset %s", document_uid)
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
            - Send `sql` and optional `dataset_uids`.
            """

            authorize_or_raise(user, Action.READ, Resource.DOCUMENTS)
            try:
                return await self.service.query_read(user, request=request)
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Read SQL query failed")
                raise HTTPException(status_code=500, detail=str(e))
