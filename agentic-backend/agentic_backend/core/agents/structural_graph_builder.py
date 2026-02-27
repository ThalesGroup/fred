# Copyright Thales 2025
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

from dataclasses import dataclass, field
from typing import Any, Hashable, Mapping, Sequence

from langgraph.graph import START, StateGraph


@dataclass(frozen=True)
class StructuralEdge:
    source: str
    target: str


@dataclass(frozen=True)
class StructuralConditional:
    source: str
    routes: Mapping[str, str]
    default_choice: str | None = None

    def selected_choice(self) -> str:
        if self.default_choice is not None:
            return self.default_choice
        try:
            return next(iter(self.routes))
        except StopIteration as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"StructuralConditional for source={self.source} has no routes"
            ) from exc


@dataclass(frozen=True)
class StructuralGraphSpec:
    state_schema: type[Any]
    nodes: Sequence[str]
    start_node: str
    edges: Sequence[StructuralEdge] = field(default_factory=tuple)
    conditionals: Sequence[StructuralConditional] = field(default_factory=tuple)


def build_structural_state_graph(
    *,
    spec: StructuralGraphSpec,
    owner_name: str,
) -> StateGraph:
    """
    Build a non-executing StateGraph for visualization-only structural rendering.

    The generated nodes and routers raise if executed. This is intentional:
    the graph exists to provide a safe Mermaid view without activating runtime
    dependencies (MCP, tool discovery, etc.).
    """
    builder = StateGraph(spec.state_schema)

    for node_id in spec.nodes:
        builder.add_node(node_id, _make_placeholder_node(owner_name, node_id))

    builder.add_edge(START, spec.start_node)

    for conditional in spec.conditionals:
        path_map: dict[Hashable, str] = {}
        for route_key, target_node in conditional.routes.items():
            path_map[route_key] = target_node
        builder.add_conditional_edges(
            conditional.source,
            _make_static_router(conditional.selected_choice()),
            path_map,
        )

    for edge in spec.edges:
        builder.add_edge(edge.source, edge.target)

    return builder


def _make_placeholder_node(owner_name: str, node_id: str):
    def node_action(state: Any) -> dict[str, Any]:
        raise RuntimeError(
            f"{owner_name} structural graph placeholder node '{node_id}' cannot execute. "
            "Use initialize_runtime() and runtime invocation methods."
        )

    return node_action


def _make_static_router(choice: str):
    def route(state: Any) -> str:
        return choice

    return route
