# app/features/kpi/controller.py
import logging

from fastapi import APIRouter, Depends, HTTPException
from fred_core import KeycloakUser, KPIQuery, KPIQueryResult, get_current_user

from app.application_context import get_app_context

logger = logging.getLogger(__name__)


class KPIController:
    """
    Minimal controller exposing a single KPI query endpoint.
    Uses the fred_core reader abstraction.
    """

    def __init__(
        self,
        router: APIRouter,
    ):
        # Init the writer store (creates index if needed)

        # Reader wraps the same OS client + index
        self.reader = get_app_context().get_kpi_store()

        @router.post("/kpi/query", response_model=KPIQueryResult, tags=["KPI"])
        async def query(body: KPIQuery, _: KeycloakUser = Depends(get_current_user)):
            return self.reader.query(body)
