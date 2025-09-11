from __future__ import annotations

import logging
from typing import Dict, List

from fred_core import Action, KeycloakUser, Resource, authorize

from app.application_context import get_history_store
from app.core.chatbot.metric_structures import MetricsResponse

logger = logging.getLogger(__name__)


class AppMonitoringMetricsService:
    """
    Adapts the pragmatic OpenSearch indices report into a MetricsResponse
    so UI code can be shared with the chatbot metrics views.
    """

    def __init__(self):
        self.history_store = get_history_store()

    @authorize(action=Action.READ, resource=Resource.METRICS)
    def get_node_numerical_metrics(
        self,
        user: KeycloakUser,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        return self.history_store.get_chatbot_metrics(
            start=start,
            end=end,
            precision=precision,
            groupby=groupby,
            agg_mapping=agg_mapping,
            user_id=user_id,
        )
