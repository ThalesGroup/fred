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

from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field

from fred_core.common import OpenSearchIndexConfig

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Closed, structurally-derived classification for the generic app-log store
# (see docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6). This is a closed
# vocabulary of exactly what this store can ever hold — "security"/"audit"
# are deliberately not members: the security/audit trail (fred.security.audit)
# is structurally excluded from this store by StoreEmitHandler, never merged
# into it, so a type that included those values would misrepresent what can
# actually appear here. Computed once, in StoreEmitHandler, from the emitting
# LogRecord's logger name — never inferred from message text, so a message
# that happens to contain "[KPI]" or "[AUDIT]" cannot be mistaken for that
# category.
LogCategory = Literal["application", "kpi"]


class InMemoryLogStorageConfig(BaseModel):
    type: Literal["in_memory"]


class StdoutLogStorageConfig(BaseModel):
    type: Literal["stdout"]


LogStorageConfig = Annotated[
    Union[InMemoryLogStorageConfig, StdoutLogStorageConfig, OpenSearchIndexConfig],
    Field(discriminator="type"),
]


class LogEventDTO(BaseModel):
    ts: float
    level: LogLevel
    logger: str
    file: str
    line: int
    msg: str
    service: Optional[str] = None
    extra: Dict[str, Any] | None = None
    category: LogCategory = "application"
