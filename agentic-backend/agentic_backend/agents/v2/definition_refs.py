"""
Stable v2 definition references.

Why this file exists:
- v2 agents should be addressed by stable ids, not Python module paths
- module/class renames must not force broad YAML/test rewrites
- this registry is the single source of truth for `definition_ref` -> class path
"""

from __future__ import annotations

from types import MappingProxyType

# Canonical v2 references
BASIC_REACT_DEFINITION_REF = "v2.react.basic"
RAG_EXPERT_DEFINITION_REF = "v2.react.rag_expert"
POSTAL_TRACKING_DEFINITION_REF = "v2.demo.postal_tracking"
BID_MGR_DEFINITION_REF = "v2.proto.bid_mgr"
PPT_FILLER_REACT_DEFINITION_REF = "v2.react.ppt_filler"
ARTIFACT_REPORT_DEFINITION_REF = "v2.demo.artifact_report"
AEGIS_GRAPH_SKELETON_DEFINITION_REF = "v2.graph.aegis_skeleton"

_CLASS_PATH_BY_DEFINITION_REF = MappingProxyType(
    {
        BASIC_REACT_DEFINITION_REF: "agentic_backend.agents.v2.basic_react.BasicReActDefinition",
        RAG_EXPERT_DEFINITION_REF: (
            "agentic_backend.agents.v2.basic_react.profiles.rag_expert_agent.RagExpertV2Definition"
        ),
        POSTAL_TRACKING_DEFINITION_REF: "agentic_backend.agents.v2.demos.postal_tracking.Definition",
        BID_MGR_DEFINITION_REF: "agentic_backend.agents.v2.protos.bid_mgr.Definition",
        PPT_FILLER_REACT_DEFINITION_REF: (
            "agentic_backend.agents.v2.ppt_filler_react.PptFillerReActV2Definition"
        ),
        ARTIFACT_REPORT_DEFINITION_REF: (
            "agentic_backend.agents.v2.artifact_report_demo.ArtifactReportDemoV2Definition"
        ),
        AEGIS_GRAPH_SKELETON_DEFINITION_REF: (
            "agentic_backend.agents.v2.aegis_graph_skeleton.AegisGraphV2SkeletonDefinition"
        ),
    }
)


def class_path_for_definition_ref(definition_ref: str) -> str:
    normalized = definition_ref.strip()
    if not normalized:
        raise ValueError("definition_ref cannot be empty.")
    try:
        return _CLASS_PATH_BY_DEFINITION_REF[normalized]
    except KeyError as exc:
        known = ", ".join(sorted(_CLASS_PATH_BY_DEFINITION_REF.keys()))
        raise ValueError(
            f"Unknown v2 definition_ref '{normalized}'. Known refs: {known}"
        ) from exc


def all_v2_definition_refs() -> tuple[str, ...]:
    return tuple(sorted(_CLASS_PATH_BY_DEFINITION_REF.keys()))
