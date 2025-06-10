from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Optional
from fred.monitoring.metric_store import MetricStore
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class MonitoringController:
    def __init__(self, router: APIRouter):
        self.metric_store = MetricStore()

        @router.on_event("startup")
        def load_metrics():
            try:
                self.metric_store.load_from_file("fred/monitoring/logs/monitoring_logs.jsonl")
                logger.info("Metric store loaded successfully.")
            except FileNotFoundError:
                logger.warning("Metric log file not found, starting with empty store.")

        def parse_dates(start: str, end: str) -> tuple[datetime, datetime]:
            try:
                start_dt = datetime.fromisoformat(start)
                end_dt = datetime.fromisoformat(end)
                return start_dt, end_dt
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid dates. Use ISO 8601 format.")

        @router.get("/metrics/all", tags=["Metrics"])
        def get_all_metrics(
            start: str = Query(..., description="Start date in ISO 8601 format"),
            end: str = Query(..., description="End date in ISO 8601 format")
        ):
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_all_by_date_range(start_dt, end_dt)

        @router.get("/metrics/numerical", tags=["Metrics"])
        def get_numerical_metrics(
            start: str = Query(..., description="Start date in ISO 8601 format"),
            end: str = Query(..., description="End date in ISO 8601 format"),
            precision: Optional[str] = Query("minute", description="Granularity: second, minute, hour, day")
        ):
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_numerical_by_date_range(start_dt, end_dt, precision)

        @router.get("/metrics/categorical", tags=["Metrics"])
        def get_categorical_metrics(
            start: str = Query(..., description="Start date in ISO 8601 format"),
            end: str = Query(..., description="End date in ISO 8601 format")
        ):
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_categorical_by_date_range(start_dt, end_dt)
