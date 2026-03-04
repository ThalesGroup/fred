"""
First concrete v2 agent definitions.

These agents are intentionally small and explicit. They exist to prove the new
definition/runtime split with real agents before Fred migrates a broader fleet.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .aegis_graph_skeleton import AegisGraphV2SkeletonDefinition
    from .artifact_report_demo import ArtifactReportDemoV2Definition
    from .basic_react import BasicReActDefinition
    from .basic_react.profiles.rag_expert_agent import RagExpertV2Definition
    from .demos.postal_tracking import Definition as PostalTrackingDefinition
    from .ppt_filler_react import PptFillerReActV2Definition
    from .protos.bid_mgr import Definition as BidMgrDefinition

__all__ = [
    "AegisGraphV2SkeletonDefinition",
    "ArtifactReportDemoV2Definition",
    "BasicReActDefinition",
    "BidMgrDefinition",
    "PostalTrackingDefinition",
    "PptFillerReActV2Definition",
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
        from .aegis_graph_skeleton import AegisGraphV2SkeletonDefinition

        return AegisGraphV2SkeletonDefinition
    if name == "ArtifactReportDemoV2Definition":
        from .artifact_report_demo import ArtifactReportDemoV2Definition

        return ArtifactReportDemoV2Definition
    if name == "BasicReActDefinition":
        from .basic_react import BasicReActDefinition

        return BasicReActDefinition
    if name == "BidMgrDefinition":
        from .protos.bid_mgr import Definition as BidMgrDefinition

        return BidMgrDefinition
    if name == "PostalTrackingDefinition":
        from .demos.postal_tracking import Definition as PostalTrackingDefinition

        return PostalTrackingDefinition
    if name == "PptFillerReActV2Definition":
        from .ppt_filler_react import PptFillerReActV2Definition

        return PptFillerReActV2Definition
    if name == "RagExpertV2Definition":
        from .basic_react.profiles.rag_expert_agent import RagExpertV2Definition

        return RagExpertV2Definition
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
