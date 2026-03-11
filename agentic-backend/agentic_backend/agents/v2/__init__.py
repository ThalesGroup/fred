"""
First concrete v2 agent definitions.

These agents are intentionally small and explicit. They exist to prove the new
definition/runtime split with real agents before Fred migrates a broader fleet.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .candidate.aegis_graph_skeleton import AegisGraphV2SkeletonDefinition
    from .candidate.bid_mgr import Definition as BidMgrDefinition
    from .demos.artifact_report import ArtifactReportDemoV2Definition
    from .demos.postal_tracking import Definition as PostalTrackingDefinition
    from .production.basic_react import BasicReActDefinition
    from .production.basic_react.profiles.rag_expert_agent import RagExpertV2Definition

__all__ = [
    "AegisGraphV2SkeletonDefinition",
    "ArtifactReportDemoV2Definition",
    "BasicReActDefinition",
    "BidMgrDefinition",
    "PostalTrackingDefinition",
    "RagExpertV2Definition",
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
    if name == "BasicReActDefinition":
        from .production.basic_react import BasicReActDefinition

        return BasicReActDefinition
    if name == "BidMgrDefinition":
        from .candidate.bid_mgr import Definition as BidMgrDefinition

        return BidMgrDefinition
    if name == "PostalTrackingDefinition":
        from .demos.postal_tracking import Definition as PostalTrackingDefinition

        return PostalTrackingDefinition
    if name == "RagExpertV2Definition":
        from .production.basic_react.profiles.rag_expert_agent import (
            RagExpertV2Definition,
        )

        return RagExpertV2Definition
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
