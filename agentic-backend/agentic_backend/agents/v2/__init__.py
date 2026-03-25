"""
First concrete v2 agent definitions.

These agents are intentionally small and explicit. They exist to prove the new
definition/runtime split with real agents before Fred migrates a broader fleet.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .candidate.aegis_graph_skeleton import AegisGraphV2SkeletonDefinition
    from .candidate.dva_risk_validator_assistant_v2_1 import (
        DVARiskValidatorGraph,
        DVARiskValidatorQA,
    )
    from .demos.artifact_report import ArtifactReportDemoV2Definition

    # from .demos.postal_tracking import Definition as PostalTrackingDefinition
    from .production.basic_deep import (
        BasicDeepAgentDefinition,
        CorpusInvestigatorDeepV2Definition,
    )
    from .production.basic_react import BasicReActDefinition

__all__ = [
    "AegisGraphV2SkeletonDefinition",
    "ArtifactReportDemoV2Definition",
    "BasicDeepAgentDefinition",
    "CorpusInvestigatorDeepV2Definition",
    "DVARiskValidatorGraph",
    "DVARiskValidatorQA",
    "BasicReActDefinition",
]


def __getattr__(name: str) -> object:
    """
    Lazily import concrete definitions.

    Why this matters:
    - keeps `agentic_backend.agents.v2` light to import
    - avoids circular import chains when core compatibility modules import
      profile declarations from the agent side
    """

    if name == "AegisGraphV2SkeletonDefinition":
        from .candidate.aegis_graph_skeleton import AegisGraphV2SkeletonDefinition

        return AegisGraphV2SkeletonDefinition
    if name == "ArtifactReportDemoV2Definition":
        from .demos.artifact_report import ArtifactReportDemoV2Definition

        return ArtifactReportDemoV2Definition
    if name == "DVARiskValidatorGraph":
        from .candidate.dva_risk_validator_assistant_v2_1 import (
            DVARiskValidatorGraph,
        )

        return DVARiskValidatorGraph
    if name == "DVARiskValidatorQA":
        from .candidate.dva_risk_validator_assistant_v2_1 import DVARiskValidatorQA

        return DVARiskValidatorQA
    if name == "BasicDeepAgentDefinition":
        from .production.basic_deep import BasicDeepAgentDefinition

        return BasicDeepAgentDefinition
    if name == "CorpusInvestigatorDeepV2Definition":
        from .production.basic_deep import CorpusInvestigatorDeepV2Definition

        return CorpusInvestigatorDeepV2Definition
    if name == "BasicReActDefinition":
        from .production.basic_react import BasicReActDefinition

        return BasicReActDefinition

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
