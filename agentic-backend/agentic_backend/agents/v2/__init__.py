"""
V2 agent definitions.

These agents are intentionally small and explicit. They exist to prove the new
definition/runtime split with real agents before Fred migrates a broader fleet.
"""

from .production.basic_deep import (
    BasicDeepAgentDefinition,
    CorpusInvestigatorDeepV2Definition,
)
from .production.basic_react import BasicReActDefinition
from .production.basic_react.profiles.prometheus_expert_agent import (
    PrometheusExpertV2Definition,
)
from .production.dva_risk_validator import (
    DVARiskValidatorGraph,
    DVARiskValidatorQA,
)

__all__ = [
    "BasicDeepAgentDefinition",
    "CorpusInvestigatorDeepV2Definition",
    "DVARiskValidatorGraph",
    "DVARiskValidatorQA",
    "BasicReActDefinition",
    "PrometheusExpertV2Definition",
]
