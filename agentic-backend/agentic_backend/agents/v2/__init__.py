"""
First concrete v2 agent definitions.

These agents are intentionally small and explicit. They exist to prove the new
definition/runtime split with real agents before Fred migrates a broader fleet.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .artifact_report_demo import ArtifactReportDemoV2Definition
    from .basic_react import BasicReActV2Definition
    from .basic_react.profiles.rag_expert_agent import RagExpertV2Definition
    from .bid_intake_graph import BidIntakeGraphV2Definition
    from .ppt_filler_react import PptFillerReActV2Definition
    from .tracking_graph_demo import TrackingGraphDemoDefinition

__all__ = [
    "ArtifactReportDemoV2Definition",
    "BasicReActV2Definition",
    "BidIntakeGraphV2Definition",
    "PptFillerReActV2Definition",
    "RagExpertV2Definition",
    "TrackingGraphDemoDefinition",
]


def __getattr__(name: str) -> object:
    """
    Lazily import concrete definitions.

    Why this matters:
    - keeps `agentic_backend.agents.v2` light to import
    - avoids circular import chains when core compatibility modules import
      profile declarations from the agent side
    """

    if name == "ArtifactReportDemoV2Definition":
        from .artifact_report_demo import ArtifactReportDemoV2Definition

        return ArtifactReportDemoV2Definition
    if name == "BasicReActV2Definition":
        from .basic_react import BasicReActV2Definition

        return BasicReActV2Definition
    if name == "BidIntakeGraphV2Definition":
        from .bid_intake_graph import BidIntakeGraphV2Definition

        return BidIntakeGraphV2Definition
    if name == "PptFillerReActV2Definition":
        from .ppt_filler_react import PptFillerReActV2Definition

        return PptFillerReActV2Definition
    if name == "RagExpertV2Definition":
        from .basic_react.profiles.rag_expert_agent import RagExpertV2Definition

        return RagExpertV2Definition
    if name == "TrackingGraphDemoDefinition":
        from .tracking_graph_demo import TrackingGraphDemoDefinition

        return TrackingGraphDemoDefinition
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
