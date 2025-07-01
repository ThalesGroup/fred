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
tool_metric_type.py

Defines the Pydantic model for ToolMetric.

Represents a single invocation of a Tool,
including latency, user/session identifiers, and timestamp.
"""

from pydantic import BaseModel
from typing import Optional,Dict

class ToolMetric(BaseModel):
    """
    Single metric record for a Tool execution.

    Attributes:
        timestamp (float): UNIX timestamp of the execution.
        user_id (Optional[str]): Identifier of the user.
        session_id (Optional[str]): Identifier of the session.
        tool_name (str): Name of the tool.
        latency (float): Execution latency in seconds.
    """
    timestamp: float
    user_id: Optional[str]
    session_id: Optional[str]
    tool_name: str
    latency: float