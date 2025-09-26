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
from fred_core.logs.log_structures import (
    LogEventDTO, 
    LogQuery, 
    LogQueryResult, 
    TailFileResponse,
    LogStorageConfig,
    InMemoryLogStorageConfig,
)
from fred_core.logs.base_log_store import BaseLogStore
from fred_core.logs.opensearch_log_store import OpenSearchLogStore
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.logs.log_setup import StoreEmitHandler, log_setup
__all__ = [
    "BaseLogStore",
    "LogEventDTO",
    "LogQuery",
    "LogQueryResult",
    "OpenSearchLogStore",
    "RamLogStore",
    "StoreEmitHandler",
    "TailFileResponse",
    "log_setup",
    "LogStorageConfig",
    "InMemoryLogStorageConfig",
]
