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

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from fred.monitoring.metric_types import CategoricalMetric, NumericalMetric


class TokenDetails(BaseModel):
    cached_tokens: Optional[int] = 0
    audio_tokens: Optional[int] = 0
    reasoning_tokens: Optional[int] = 0
    rejected_prediction_tokens: Optional[int] = 0
    accepted_prediction_tokens: Optional[int] = 0


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: Optional[TokenDetails] = None
    completion_tokens_details: Optional[TokenDetails] = None

class Metric(BaseModel):
    timestamp: float
    latency: float
    user_id: str
    session_id: str
    model_type: str

    # Optional fields for downstream analysis
    finish_reason: Optional[str] = None
    model_name: Optional[str] = None
    system_fingerprint: Optional[str] = None
    service_tier: Optional[str] = None
    token_usage: Optional[TokenUsage] = None

class MetricStore(ABC):
    @abstractmethod
    def add_metric(self, metric: Metric) -> None:
        pass

    @abstractmethod
    def get_all(self) -> List[Metric]:
        pass

    @abstractmethod
    def get_by_date_range(self, start: datetime, end: datetime) -> List[Metric]:
        pass

    @abstractmethod
    def get_numerical_aggregated_by_precision(
        self, start: datetime, end: datetime, precision: str, agg: str
    ) -> List[NumericalMetric]:
        pass

    @abstractmethod
    def get_categorical_rows_by_date_range(
        self, start: datetime, end: datetime
    ) -> List[CategoricalMetric]:
        pass

