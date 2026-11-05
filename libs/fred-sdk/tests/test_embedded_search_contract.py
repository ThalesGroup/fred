# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The embedded Rust agent's search events are valid Fred runtime events."""

import json
from pathlib import Path

from fred_core.store import VectorSearchHit
from fred_sdk.contracts.runtime import FinalRuntimeEvent, ToolResultRuntimeEvent


def fixture():
    return json.loads(
        (Path(__file__).parent / "fixtures/embedded_search_turn.json").read_text()
    )


def test_fixture_hits_are_knowledge_flow_hits():
    for hit in fixture()["knowledge_flow_hits"]:
        VectorSearchHit.model_validate(hit)


def test_final_carries_the_whole_citable_hit():
    data = fixture()
    event = FinalRuntimeEvent.model_validate(data["final"])
    assert [source.uid for source in event.sources] == ["doc-1"]
    assert event.sources[0].citation_url == "/documents/doc-1"
    assert event.sources[0].tag_names == ["guide"]


def test_tool_result_has_the_shape_of_the_python_search_capability():
    event = ToolResultRuntimeEvent.model_validate(fixture()["tool_result"])
    content = json.loads(event.content)
    assert content["query"] == "manual question"
    assert all(
        set(hit) == {"uid", "title", "content", "file_name", "page", "section", "score"}
        for hit in content["hits"]
    )
