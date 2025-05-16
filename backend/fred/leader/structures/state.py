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
