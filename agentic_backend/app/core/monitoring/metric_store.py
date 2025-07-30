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

"""
metric_store.py

Defines the abstract MetricStore interface and core data models for monitoring.

Includes:
- TokenDetails and TokenUsage models for tracking LLM token breakdowns.
- Precision and Aggregation enums.
- Abstract MetricStore interface specifying required store methods.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from app.core.monitoring.metric_types import CategoricalMetric, NumericalMetric
from pydantic import BaseModel
from enum import Enum


class TokenDetails(BaseModel):
    """
    Detailed breakdown of token categories during model usage.

    Attributes:
        cached_tokens: Number of tokens fetched from cache.
        audio_tokens: Number of tokens for audio processing.
        reasoning_tokens: Number of tokens used for reasoning operations.
        rejected_prediction_tokens: Tokens from predictions that were rejected.
        accepted_prediction_tokens: Tokens from accepted predictions.
    """

    cached_tokens: Optional[int] = 0
    audio_tokens: Optional[int] = 0
    reasoning_tokens: Optional[int] = 0
    rejected_prediction_tokens: Optional[int] = 0
    accepted_prediction_tokens: Optional[int] = 0


class TokenUsage(BaseModel):
    """
    Token usage summary for a single inference.

    Attributes:
        prompt_tokens: Number of tokens in the prompt.
        completion_tokens: Number of tokens in the generated response.
        total_tokens: Sum of prompt and completion tokens.
        prompt_tokens_details: Detailed breakdown of prompt tokens.
        completion_tokens_details: Detailed breakdown of completion tokens.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: Optional[TokenDetails] = None
    completion_tokens_details: Optional[TokenDetails] = None


class Metric(BaseModel):
    """
    Core metric representing one inference or session.

    Attributes:
        timestamp: UNIX timestamp of the event.
        latency: Duration in seconds to complete the inference.
        user_id: Identifier of the user who made the request.
        session_id: Identifier of the session.
        model_type: Type/category of the model used.
        finish_reason: Reason the generation stopped (e.g., 'length', 'stop').
        model_name: Full model identifier (e.g., gpt-4-32k).
        system_fingerprint: Version or hash of the deployed model.
        service_tier: SLA or environment type (e.g., premium, free).
        token_usage: Token usage information associated with the inference.
    """

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


class Precision(str, Enum):
    sec = "sec"
    min = "min"
    hour = "hour"
    day = "day"


class Aggregation(str, Enum):
    avg = "avg"
    max = "max"
    min = "min"
    sum = "sum"


class MetricStore(ABC):
    """
    Abstract base class for a metric storage backend.

    Concrete implementations must define methods for:
    - Storing a metric
    - Filtering metrics by time range
    - Aggregating numerical values
    - Extracting categorical fields
    """

    @abstractmethod
    def add_metric(self, metric: Metric) -> None:
        """Store a single metric instance."""
        pass

    @abstractmethod
    def get_all(self) -> List[Metric]:
        """Return all stored metrics."""
        pass

    @abstractmethod
    def get_by_date_range(self, start: datetime, end: datetime) -> List[Metric]:
        """Return metrics with timestamp between `start` and `end`."""
        pass

    @abstractmethod
    def get_aggregate_numerical_metrics_by_time_and_group(
        self, start: datetime, end: datetime, precision: Precision, agg: Aggregation
    ) -> List[NumericalMetric]:
        """
        Aggregate numerical fields by time buckets and apply an aggregation function.

        Args:
            start: Start datetime.
            end: End datetime.
            precision: Bucket granularity ('sec', 'min', 'hour', 'day').
            agg: Aggregation function ('avg', 'min', 'max', 'sum').
        """
        pass

    @abstractmethod
    def get_categorical_rows_by_date_range(
        self, start: datetime, end: datetime
    ) -> List[CategoricalMetric]:
        """
        Extract categorical fields from metrics in a date range.

        Args:
            start: Start datetime.
            end: End datetime.
        """
        pass
