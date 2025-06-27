from pydantic import BaseModel,Field
from typing import Optional,Dict,Any

class NodeMetric(BaseModel):
    timestamp: float
    node_name: str
    latency: float
    user_id: str
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    result_summary: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NumericalMetric(BaseModel):
    """
    Aggregated numerical metrics for a specific time bucket.

    Attributes:
        bucket: Time window label (e.g., '2025-06-12T15:00').
        values: Mapping of metric field names to aggregated values.
    """
    bucket: str  # e.g., "2025-06-11T14:00"
    values: Dict[str, float]  # {"latency": 0.32, "token_usage.total_tokens": 59}


class CategoricalMetric(BaseModel):
    """
    Subset of fields from a metric, focused on categorical dimensions.

    Attributes:
        timestamp: UNIX timestamp of the event.
        user_id: User identifier.
        session_id: Session identifier.
        agent_name: Name of the agent used.
        model_name: Name of the model used.
        model_type: Type or category of the model.
        finish_reason: Why the generation ended.
        id: Unique identifier of the inference.
        system_fingerprint: Deployment hash or version.
        service_tier: Tier or SLA level of the request.
    """
    timestamp: float
    user_id: Optional[str]
    session_id: Optional[str]
    agent_name: Optional[str]
    model_name: Optional[str]
    model_type: Optional[str]
    finish_reason: Optional[str]
    id: Optional[str]
    system_fingerprint: Optional[str]
    service_tier: Optional[str]