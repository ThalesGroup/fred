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

import operator
from typing import Annotated, List, Optional, Tuple

from flow import AgentFlow
from leader.structures.decision import ExecuteDecision, PlanDecision
from leader.structures.plan import Plan
from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState

class State(MessagesState):
    """State of the assistant."""

    plan: Plan
    experts: Optional[List[AgentFlow]]
    thoughts: Optional[List[str]]
    progress: Optional[List[Tuple[str, List[AnyMessage]]]]
    plan_decision: Optional[PlanDecision]
    expert_decision: Optional[ExecuteDecision]
    traces: Annotated[List[str], operator.add]
    objective: Optional[AnyMessage]
    inital_objective: Optional[AnyMessage]
