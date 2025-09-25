# app/features/logs/structures.py
# Why: mirror KPI types so readers/writers/controllers are symmetrical.

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

LogLevel = Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]

class LogFilter(BaseModel):
    # Why these: they match what we actually filter by in prod incidents.
    level_at_least: Optional[LogLevel] = None
    logger_like: Optional[str] = None        # substring on logger name
    service: Optional[str] = None            # agentic-backend | knowledge-flow | etc.
    text_like: Optional[str] = None          # free-text contains on message

class LogQuery(BaseModel):
    # Same shape as KPI: time range + filters + limit/order.
    since: str = Field(..., description="ISO or 'now-10m'")
    until: Optional[str] = None
    filters: LogFilter = Field(default_factory=LogFilter)
    limit: int = Field(500, ge=1, le=5000)
    order: Literal["asc","desc"] = "asc"     # time order

class LogEventDTO(BaseModel):
    ts: float
    level: LogLevel
    logger: str
    file: str
    line: int
    msg: str
    service: Optional[str] = None
    extra: Dict[str, Any] | None = None

class LogQueryResult(BaseModel):
    events: List[LogEventDTO] = Field(default_factory=list)
