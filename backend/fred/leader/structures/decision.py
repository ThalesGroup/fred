from typing import Literal

from pydantic import BaseModel


class PlanDecision(BaseModel):
    """Decision after evaluation."""

    action: Literal["planning", "respond"]


class ExecuteDecision(BaseModel):
    """
    Decision before expert execution.
    """

    # Add your custom expert flows here to include them in Fred
    expert: Literal[
        "GeneralistExpert", 
        "DocumentsExpert",
        "TechnicalKubernetesExpert", 
        "TheoreticalKubernetesExpert", 
        "KedaExpert",
        "MonitoringExpert",
        "K8SOperatorExpert"]