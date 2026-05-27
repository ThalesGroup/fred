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

from fred_core.logs.base_log_store import BaseLogStore
from fred_core.logs.log_structures import LogEventDTO, LogQuery, LogQueryResult


class NullLogStore(BaseLogStore):
    """
    No-op log store used when stdout-only logging is desired.
    Keeps the logging pipeline satisfied without persisting or querying logs.
    """

    def ensure_ready(self) -> None:  # pragma: no cover - trivial
        return

    def index_event(self, event: LogEventDTO) -> None:  # pragma: no cover - no-op
        return

    def bulk_index(self, events: list[LogEventDTO]) -> None:  # pragma: no cover
        return

    def query(self, q: LogQuery) -> LogQueryResult:  # pragma: no cover
        return LogQueryResult(events=[])
