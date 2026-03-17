# Copyright Thales 2026
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

"""
Stable v2 definition references.

Why this file exists:
- v2 agents should be addressed by stable ids, not Python module paths
- module/class renames must not force broad YAML/test rewrites
- this registry is the single source of truth for `definition_ref` -> class path

This is an intermediate compatibility layer. New code should not be added here; instead, add new definitions in their own modules and add their refs to the registry in this file. After the UI fully migrates to v2 definitions and no longer relies on `AgentSettings`, this layer can be removed and `definition_ref` can directly reference Python paths.
"""

from __future__ import annotations

from types import MappingProxyType

# Canonical v2 references
BASIC_REACT_DEFINITION_REF = "v2.react.basic"
RAG_EXPERT_DEFINITION_REF = "v2.react.rag_expert"
PROMETHEUS_EXPERT_DEFINITION_REF = "v2.react.prometheus_expert"
POSTAL_TRACKING_DEFINITION_REF = "v2.demo.postal_tracking"
BID_MGR_DEFINITION_REF = "v2.proto.bid_mgr"
PPT_FILLER_REACT_DEFINITION_REF = "v2.react.ppt_filler"
ARTIFACT_REPORT_DEFINITION_REF = "v2.demo.artifact_report"
AEGIS_GRAPH_SKELETON_DEFINITION_REF = "v2.graph.aegis_skeleton"

_CLASS_PATH_BY_DEFINITION_REF = MappingProxyType(
    {
        BASIC_REACT_DEFINITION_REF: (
            "agentic_backend.agents.v2.production.basic_react.BasicReActDefinition"
        ),
        RAG_EXPERT_DEFINITION_REF: (
            "agentic_backend.agents.v2.production.basic_react.profiles.rag_expert_agent.RagExpertV2Definition"
        ),
        PROMETHEUS_EXPERT_DEFINITION_REF: (
            "agentic_backend.agents.v2.production.basic_react.profiles.prometheus_expert_agent.PrometheusExpertV2Definition"
        ),
        POSTAL_TRACKING_DEFINITION_REF: "agentic_backend.agents.v2.demos.postal_tracking.Definition",
        BID_MGR_DEFINITION_REF: "agentic_backend.agents.v2.candidate.bid_mgr.Definition",
        PPT_FILLER_REACT_DEFINITION_REF: (
            "agentic_backend.agents.v2.production.ppt_filler_react.PptFillerReActV2Definition"
        ),
        ARTIFACT_REPORT_DEFINITION_REF: (
            "agentic_backend.agents.v2.demos.artifact_report.ArtifactReportDemoV2Definition"
        ),
        AEGIS_GRAPH_SKELETON_DEFINITION_REF: (
            "agentic_backend.agents.v2.candidate.aegis_graph_skeleton.AegisGraphV2SkeletonDefinition"
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
