# app/features/kpi/controller.py
import logging

from fastapi import APIRouter, Depends
from fred_core import Action, KeycloakUser, KPIQuery, KPIQueryResult, Resource, authorize_or_raise, get_current_user

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
        async def query(body: KPIQuery, user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.KPIS)
            return self.reader.query(body)
