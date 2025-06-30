from fastapi import APIRouter, Query, HTTPException
from typing import List, Annotated
from datetime import datetime
from fred.monitoring.metric_store import Precision, Aggregation

def register_metric_routes(router: APIRouter, store, MetricType, NumericalType, CategoricalType, prefix: str):
    def parse_dates(start: str, end: str) -> (datetime, datetime):
        return datetime.fromisoformat(start), datetime.fromisoformat(end)

    @router.get(f"/metrics/{prefix}/all", response_model=List[MetricType])
    def get_metrics(start: Annotated[str, Query()], end: Annotated[str, Query()]):
        start_dt, end_dt = parse_dates(start, end)
        return store.get_by_date_range(start_dt, end_dt)

    @router.get(f"/metrics/{prefix}/numerical",response_model=List[NumericalType])
    def get_node_numerical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()],
            precision: Precision = Precision.hour,
            agg: List[str] = Query(default=[]),
            groupby: List[str] = Query(default=[])):
            start_dt, end_dt = parse_dates(start, end)
            agg_mapping = {}
            for item in agg:
                try:
                    field, op = item.split(":")
                    agg_mapping[field] = op
                except ValueError:
                    raise HTTPException(400, detail=f"Invalid agg parameter format: {item}")

            return store.get_aggregate_numerical_metrics_by_time_and_group(
                start=start_dt,
                end=end_dt,
                precision=precision,
                agg_mapping=agg_mapping,
                groupby_fields=groupby
            )

    @router.get(f"/metrics/{prefix}/categorical", response_model=List[CategoricalType])
    def get_categorical(start: Annotated[str, Query()], end: Annotated[str, Query()]):
        start_dt, end_dt = parse_dates(start, end)
        return store.get_categorical_rows_by_date_range(start_dt, end_dt)
