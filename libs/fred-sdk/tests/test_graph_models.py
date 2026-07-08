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
Offline unit tests for graph-related validators in fred_sdk.contracts.models.

Covers:
- GraphConditionalDefinition.validate_default_route
- GraphDefinition.validate_topology:
    unique node ids, entry node exists, edge endpoints, conditional targets,
    parallel group constraints, on_error references
"""

from __future__ import annotations

import pytest
from fred_sdk.contracts.models import (
    GraphConditionalDefinition,
    GraphDefinition,
    GraphEdgeDefinition,
    GraphNodeDefinition,
    GraphRouteDefinition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(node_id: str, *, on_error: str | None = None) -> GraphNodeDefinition:
    return GraphNodeDefinition(node_id=node_id, title=node_id, on_error=on_error)


def _edge(source: str, target: str) -> GraphEdgeDefinition:
    return GraphEdgeDefinition(source=source, target=target)


def _route(key: str, target: str) -> GraphRouteDefinition:
    return GraphRouteDefinition(route_key=key, target=target)


def _conditional(
    source: str,
    *routes: GraphRouteDefinition,
    default_route_key: str | None = None,
) -> GraphConditionalDefinition:
    return GraphConditionalDefinition(
        source=source, routes=routes, default_route_key=default_route_key
    )


def _minimal_graph(*extra_nodes: GraphNodeDefinition) -> GraphDefinition:
    """One-node graph: just 'start'."""
    return GraphDefinition(
        state_model_name="State",
        entry_node="start",
        nodes=(_node("start"), *extra_nodes),
    )


# ---------------------------------------------------------------------------
# GraphConditionalDefinition.validate_default_route
# ---------------------------------------------------------------------------


class TestGraphConditionalDefaultRoute:
    def test_no_default_route_valid(self) -> None:
        c = _conditional("router", _route("yes", "a"), _route("no", "b"))
        assert c.default_route_key is None

    def test_valid_default_route_key(self) -> None:
        c = _conditional(
            "router",
            _route("yes", "a"),
            _route("no", "b"),
            default_route_key="no",
        )
        assert c.default_route_key == "no"

    def test_unknown_default_route_key_rejected(self) -> None:
        with pytest.raises(Exception, match="default_route_key"):
            _conditional(
                "router",
                _route("yes", "a"),
                default_route_key="missing",
            )


# ---------------------------------------------------------------------------
# GraphDefinition.validate_topology — node uniqueness
# ---------------------------------------------------------------------------


class TestGraphTopologyNodeUniqueness:
    def test_valid_single_node(self) -> None:
        g = _minimal_graph()
        assert len(g.nodes) == 1

    def test_duplicate_node_ids_rejected(self) -> None:
        with pytest.raises(Exception, match="unique node_id"):
            GraphDefinition(
                state_model_name="State",
                entry_node="start",
                nodes=(_node("start"), _node("start")),
            )


# ---------------------------------------------------------------------------
# GraphDefinition.validate_topology — entry node
# ---------------------------------------------------------------------------


class TestGraphTopologyEntryNode:
    def test_unknown_entry_node_rejected(self) -> None:
        with pytest.raises(Exception, match="entry_node"):
            GraphDefinition(
                state_model_name="State",
                entry_node="missing",
                nodes=(_node("start"),),
            )


# ---------------------------------------------------------------------------
# GraphDefinition.validate_topology — edges
# ---------------------------------------------------------------------------


class TestGraphTopologyEdges:
    def test_valid_edge(self) -> None:
        g = GraphDefinition(
            state_model_name="State",
            entry_node="a",
            nodes=(_node("a"), _node("b")),
            edges=(_edge("a", "b"),),
        )
        assert len(g.edges) == 1

    def test_edge_unknown_source_rejected(self) -> None:
        with pytest.raises(Exception, match="edge source"):
            GraphDefinition(
                state_model_name="State",
                entry_node="a",
                nodes=(_node("a"),),
                edges=(_edge("ghost", "a"),),
            )

    def test_edge_unknown_target_rejected(self) -> None:
        with pytest.raises(Exception, match="edge target"):
            GraphDefinition(
                state_model_name="State",
                entry_node="a",
                nodes=(_node("a"),),
                edges=(_edge("a", "ghost"),),
            )


# ---------------------------------------------------------------------------
# GraphDefinition.validate_topology — conditionals
# ---------------------------------------------------------------------------


class TestGraphTopologyConditionals:
    def test_valid_conditional(self) -> None:
        g = GraphDefinition(
            state_model_name="State",
            entry_node="router",
            nodes=(_node("router"), _node("path_a"), _node("path_b")),
            conditionals=(
                _conditional("router", _route("a", "path_a"), _route("b", "path_b")),
            ),
        )
        assert len(g.conditionals) == 1

    def test_conditional_unknown_source_rejected(self) -> None:
        with pytest.raises(Exception, match="conditional source"):
            GraphDefinition(
                state_model_name="State",
                entry_node="a",
                nodes=(_node("a"), _node("b")),
                conditionals=(_conditional("ghost", _route("x", "b")),),
            )

    def test_conditional_unknown_target_rejected(self) -> None:
        with pytest.raises(Exception, match="conditional target"):
            GraphDefinition(
                state_model_name="State",
                entry_node="a",
                nodes=(_node("a"),),
                conditionals=(_conditional("a", _route("x", "ghost")),),
            )


# ---------------------------------------------------------------------------
# GraphDefinition.validate_topology — parallel groups
# ---------------------------------------------------------------------------


class TestGraphTopologyParallelGroups:
    def _graph_with_group(self, group: tuple[str, ...]) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="fanout",
            nodes=(
                _node("fanout"),
                _node("fanin"),
                _node("worker_a"),
                _node("worker_b"),
            ),
            parallel_groups=(group,),
        )

    def test_valid_parallel_group(self) -> None:
        g = self._graph_with_group(("fanout", "fanin", "worker_a", "worker_b"))
        assert len(g.parallel_groups) == 1

    def test_too_few_entries_rejected(self) -> None:
        with pytest.raises(Exception, match="at least 4"):
            self._graph_with_group(("fanout", "fanin", "worker_a"))

    def test_unknown_node_in_group_rejected(self) -> None:
        with pytest.raises(Exception, match="unknown node"):
            self._graph_with_group(("fanout", "fanin", "worker_a", "ghost"))

    def test_duplicate_members_rejected(self) -> None:
        with pytest.raises(Exception, match="duplicate member"):
            self._graph_with_group(("fanout", "fanin", "worker_a", "worker_a"))

    def test_fanout_as_member_rejected(self) -> None:
        with pytest.raises(Exception, match="fan_out and fan_in"):
            self._graph_with_group(("fanout", "fanin", "fanout", "worker_b"))


# ---------------------------------------------------------------------------
# GraphDefinition.validate_topology — on_error references
# ---------------------------------------------------------------------------


class TestGraphTopologyOnError:
    def test_valid_on_error(self) -> None:
        g = GraphDefinition(
            state_model_name="State",
            entry_node="main",
            nodes=(_node("main", on_error="err_handler"), _node("err_handler")),
        )
        assert g.nodes[0].on_error == "err_handler"

    def test_unknown_on_error_rejected(self) -> None:
        with pytest.raises(Exception, match="on_error"):
            GraphDefinition(
                state_model_name="State",
                entry_node="main",
                nodes=(_node("main", on_error="ghost"),),
            )
