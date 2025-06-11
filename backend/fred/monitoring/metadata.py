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
