from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Optional
from fred.monitoring.metric_store import MetricStore,get_metric_store
import logging
from typing import List, Dict, Any
from statistics import mean
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)
router = APIRouter()

class MetricStoreController:
    def __init__(self, router: APIRouter):
        self.metric_store = get_metric_store()

        def parse_dates(start: str, end: str) -> tuple[datetime, datetime]:
            try:
                return datetime.fromisoformat(start), datetime.fromisoformat(end)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid dates. Use ISO 8601 format.")

        def filter_metrics_by_date(metrics: List[Dict[str, Any]], start: datetime, end: datetime) -> List[Dict[str, Any]]:
            return [
                m for m in metrics
                if "timestamp" in m and start.timestamp() <= m["timestamp"] <= end.timestamp()
            ]

        @router.get("/metrics/all", tags=["Metrics"])
        def get_all_metrics(
            start: str = Query(..., description="Start date in ISO 8601 format"),
            end: str = Query(..., description="End date in ISO 8601 format")
        ):
            start_dt, end_dt = parse_dates(start, end)
            all_data = self.metric_store.all()
            return filter_metrics_by_date(all_data, start_dt, end_dt)



        @router.get("/metrics/numerical", tags=["Metrics"])
        def get_numerical_metrics(
            start: str = Query(..., description="Start date in ISO 8601 format"),
            end: str = Query(..., description="End date in ISO 8601 format"),
            precision: str = Query("hour", enum=["sec", "min", "hour", "day"]),
            agg: str = Query("avg", enum=["avg", "max","sum"])
        ):
            start_dt, end_dt = parse_dates(start, end)
            all_data = self.metric_store.all()
            filtered = filter_metrics_by_date(all_data, start_dt, end_dt)

            numeric_fields = [
                "latency",
                "token_usage.total_tokens",
                "token_usage.prompt_tokens",
                "token_usage.completion_tokens",
                "token_usage.completion_tokens_details.accepted_prediction_tokens",
                "token_usage.completion_tokens_details.audio_tokens",
                "token_usage.completion_tokens_details.reasoning_tokens",
                "token_usage.completion_tokens_details.rejected_prediction_tokens",
                "token_usage.prompt_tokens_details.audio_tokens",
                "token_usage.prompt_tokens_details.cached_tokens"
            ]

            # Crée des groupes de timestamps arrondis
            def round_timestamp(ts: float) -> str:
                dt = datetime.fromtimestamp(ts)
                if precision == "sec":
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                elif precision == "min":
                    return dt.strftime("%Y-%m-%d %H:%M")
                elif precision == "hour":
                    return dt.strftime("%Y-%m-%d %H:00")
                elif precision == "day":
                    return dt.strftime("%Y-%m-%d")
                return dt.isoformat()

            buckets = defaultdict(lambda: defaultdict(list))

            for m in filtered:
                ts = m.get("timestamp")
                if not isinstance(ts, (int, float)):
                    continue
                bucket_key = round_timestamp(ts)

                for field in numeric_fields:
                    try:
                        val = m
                        for part in field.split("."):
                            val = val[part]
                        if isinstance(val, (int, float)):
                            buckets[bucket_key][field].append(val)
                    except (KeyError, TypeError):
                        continue

            result = []

            for bucket_time, field_values in sorted(buckets.items()):
                bucket_entry = {"bucket": bucket_time}
                for field, values in field_values.items():
                    if agg == "avg":
                        bucket_entry[field] = round(mean(values), 4)
                    elif agg == "min":
                        bucket_entry[field] = round(min(values), 4)
                    elif agg == "max":
                        bucket_entry[field] = round(max(values), 4)
                    elif agg == "sum":
                        bucket_entry[field] = round(sum(values), 4)
                result.append(bucket_entry)

            return result


        @router.get("/metrics/categorical", tags=["Metrics"])
        def get_categorical_metrics_as_rows(
            start: str = Query(..., description="Start date in ISO 8601 format"),
            end: str = Query(..., description="End date in ISO 8601 format")
        ):
            start_dt, end_dt = parse_dates(start, end)
            all_data = self.metric_store.all()
            filtered = filter_metrics_by_date(all_data, start_dt, end_dt)

            # Liste des champs catégoriques à extraire pour chaque requête
            categorical_fields = [
                "timestamp", "user_id", "session_id",
                "model_name", "model_type", "finish_reason",
                "id", "system_fingerprint", "service_tier"
            ]

            result = []
            for metric in filtered:
                row = {
                    field: metric.get(field, None)
                    for field in categorical_fields
                }
                result.append(row)

            return result
