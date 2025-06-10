from fastapi import FastAPI, Query, HTTPException
from datetime import datetime
from typing import Optional
from fred.monitoring.metric_store import MetricStore

app = FastAPI()
metric_store = MetricStore()

@app.on_event("startup")
def load_metrics():
    try:
        metric_store.load_from_file("fred/monitoring/logs/monitoring_logs.jsonl")
    except FileNotFoundError:
        print("Fichier de métriques non trouvé, démarrage vide.")


def parse_dates(start: str, end: str) -> tuple[datetime, datetime]:
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        return start_dt, end_dt
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates invalides. Utilise le format ISO 8601.")


@app.get("/metrics/all")
def get_all_metrics(
    start: str = Query(...), end: str = Query(...)
):
    start_dt, end_dt = parse_dates(start, end)
    return metric_store.get_all_by_date_range(start_dt, end_dt)


@app.get("/metrics/numerical")
def get_numerical_metrics(
    start: str = Query(...), end: str = Query(...),
    precision: Optional[str] = Query("minute", description="second, minute, hour, day")
):
    start_dt, end_dt = parse_dates(start, end)
    return metric_store.get_numerical_by_date_range(start_dt, end_dt, precision)


@app.get("/metrics/categorical")
def get_categorical_metrics(
    start: str = Query(...), end: str = Query(...)
):
    start_dt, end_dt = parse_dates(start, end)
    return metric_store.get_categorical_by_date_range(start_dt, end_dt)
