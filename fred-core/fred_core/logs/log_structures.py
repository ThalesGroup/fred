# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from fred_core.common.structures import OpenSearchIndexConfig

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class InMemoryLogStorageConfig(BaseModel):
    type: Literal["in_memory"]


class StdoutLogStorageConfig(BaseModel):
    type: Literal["stdout"]


LogStorageConfig = Annotated[
    Union[InMemoryLogStorageConfig, StdoutLogStorageConfig, OpenSearchIndexConfig],
    Field(discriminator="type"),
]


class LogFilter(BaseModel):
    # Why these: they match what we actually filter by in prod incidents.
    level_at_least: Optional[LogLevel] = None
    logger_like: Optional[str] = None  # substring on logger name
    service: Optional[str] = None  # agentic-backend | knowledge-flow | etc.
    text_like: Optional[str] = None  # free-text contains on message


class LogQuery(BaseModel):
    # Same shape as KPI: time range + filters + limit/order.
    since: str = Field(..., description="ISO or 'now-10m'")
    until: Optional[str] = None
    filters: LogFilter = Field(default_factory=LogFilter)
    limit: int = Field(500, ge=1, le=5000)
    order: Literal["asc", "desc"] = "asc"  # time order


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


class TailFileResponse(BaseModel):
    """
    Why a dedicated response:
    - Tail returns raw JSON lines (already formatted by our file handler).
    - The UI can decide to parse lazily or show plain text.
    """

    lines: list[str] = Field(default_factory=list)
