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