# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
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
node_metric_type.py

Defines the Pydantic model for NodeMetric.

Represents a single invocation of a LangGraph node,
including latency, user/session info, token usage, model info,
and any custom metadata.
"""

from pydantic import BaseModel,Field
from typing import Optional,Dict,Any

class NodeMetric(BaseModel):
    """
    Single metric record for a LangGraph node execution.

    Attributes:
        timestamp (float): UNIX timestamp of the invocation.
        node_name (str): Name of the LangGraph node function.
        latency (float): Execution latency in seconds.
        user_id (str): User identifier.
        session_id (str): Session identifier.
        agent_name (Optional[str]): Name of the agent (if any).
        model_name (Optional[str]): Name of the model used.
        input_tokens (Optional[int]): Number of input tokens.
        output_tokens (Optional[int]): Number of output tokens.
        total_tokens (Optional[int]): Total tokens used.
        result_summary (Optional[str]): Text summary of the response.
        metadata (Dict[str, Any]): Arbitrary extra metadata.
    """
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