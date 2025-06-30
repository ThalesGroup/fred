from pydantic import BaseModel
from typing import Optional,Dict

class ToolMetric(BaseModel):
    timestamp: float
    user_id: Optional[str]
    session_id: Optional[str]
    tool_name: str
    latency: float