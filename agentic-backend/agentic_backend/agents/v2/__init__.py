"""
First concrete v2 agent definitions.

These agents are intentionally small and explicit. They exist to prove the new
definition/runtime split with real agents before Fred migrates a broader fleet.
"""

from .basic_react import BasicReActV2Definition
from .artifact_report_demo import ArtifactReportDemoV2Definition
from .rag_expert import RagExpertV2Definition
from .tracking_graph_demo import TrackingGraphDemoDefinition

__all__ = [
    "ArtifactReportDemoV2Definition",
    "BasicReActV2Definition",
    "RagExpertV2Definition",
    "TrackingGraphDemoDefinition",
]
