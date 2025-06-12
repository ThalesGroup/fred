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

from typing import Optional, Dict, List, Any
from pydantic import BaseModel


class TokenDetails(BaseModel):
    accepted_prediction_tokens: Optional[int] = 0
    rejected_prediction_tokens: Optional[int] = 0
    reasoning_tokens: Optional[int] = 0
    audio_tokens: Optional[int] = 0
    cached_tokens: Optional[int] = 0


class TokenUsage(BaseModel):
    completion_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    completion_tokens_details: Optional[TokenDetails] = None
    prompt_tokens_details: Optional[TokenDetails] = None


class ContentFilterResult(BaseModel):
    filtered: Optional[bool] = None
    severity: Optional[str] = None
    detected: Optional[bool] = None


class PromptFilterResult(BaseModel):
    prompt_index: Optional[int] = None
    content_filter_results: Dict[str, ContentFilterResult]


class MetaData(BaseModel):
    token_usage: Optional[TokenUsage] = None
    model_name: Optional[str] = None
    system_fingerprint: Optional[str] = None
    id: Optional[str] = None
    service_tier: Optional[str] = None
    prompt_filter_results: Optional[List[PromptFilterResult]] = None
    finish_reason: Optional[str] = None
    logprobs: Optional[Any] = None
    content_filter_results: Optional[Dict[str, ContentFilterResult]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    latency: Optional[float] = None
    timestamp: Optional[float] = None
    model_type: Optional[str] = None

class NumericalMetric(BaseModel):
    bucket: str  # e.g., "2025-06-11T14:00"
    values: Dict[str, float]  # {"latency": 0.32, "token_usage.total_tokens": 59}

class CategoricalMetric(BaseModel):
    timestamp: float
    user_id: Optional[str]
    session_id: Optional[str]
    model_name: Optional[str]
    model_type: Optional[str]
    finish_reason: Optional[str]
    id: Optional[str]
    system_fingerprint: Optional[str]
    service_tier: Optional[str]