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
Offline unit tests for the OpenAI compatibility event transformer.

Tests verify that each Fred RuntimeEvent kind is correctly mapped to an
OpenAI chat.completion.chunk, and that unsupported kinds are dropped.
All tests run without any external services.
"""

from __future__ import annotations

import json

import pytest
from fred_sdk.contracts.openai_compat import (
    OpenAIChatRequest,
    OpenAICompletionChunk,
    OpenAIMessage,
    OpenAIToolCall,
    fred_event_to_openai_chunk,
)

_COMPLETION_ID = "chatcmpl-test"
_MODEL = "my-agent"
_CREATED = 1700000000


def _chunk(event: dict) -> OpenAICompletionChunk | None:
    return fred_event_to_openai_chunk(event, _COMPLETION_ID, _MODEL, _CREATED)


# ---------------------------------------------------------------------------
# assistant_delta
# ---------------------------------------------------------------------------


def test_assistant_delta_maps_to_content_chunk() -> None:
    event = {"kind": "assistant_delta", "delta": "hello", "sequence": 1}
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.id == _COMPLETION_ID
    assert chunk.model == _MODEL
    assert chunk.created == _CREATED
    assert chunk.object == "chat.completion.chunk"
    assert len(chunk.choices) == 1
    assert chunk.choices[0].delta.content == "hello"
    assert chunk.choices[0].finish_reason is None
    assert chunk.fred is None


# ---------------------------------------------------------------------------
# tool_call
# ---------------------------------------------------------------------------


def test_tool_call_maps_to_tool_calls_chunk() -> None:
    event = {
        "kind": "tool_call",
        "call_id": "call-abc",
        "tool_name": "search_knowledge",
        "arguments": {"query": "fred"},
        "sequence": 2,
    }
    chunk = _chunk(event)

    assert chunk is not None
    delta = chunk.choices[0].delta
    assert delta.tool_calls is not None
    assert len(delta.tool_calls) == 1
    tc = delta.tool_calls[0]
    assert isinstance(tc, OpenAIToolCall)
    assert tc.id == "call-abc"
    assert tc.type == "function"
    assert tc.function.name == "search_knowledge"
    assert json.loads(tc.function.arguments) == {"query": "fred"}
    assert chunk.fred is None


def test_tool_call_serialises_to_openai_json_shape() -> None:
    event = {
        "kind": "tool_call",
        "call_id": "call-xyz",
        "tool_name": "fetch_data",
        "arguments": {"limit": 10},
        "sequence": 2,
    }
    chunk = _chunk(event)

    assert chunk is not None
    data = json.loads(chunk.model_dump_json(exclude_none=True))
    tc = data["choices"][0]["delta"]["tool_calls"][0]
    assert tc["id"] == "call-xyz"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "fetch_data"
    assert json.loads(tc["function"]["arguments"]) == {"limit": 10}


# ---------------------------------------------------------------------------
# tool_result
# ---------------------------------------------------------------------------


def test_tool_result_without_sources_returns_empty_delta() -> None:
    event = {
        "kind": "tool_result",
        "call_id": "call-abc",
        "content": "some result",
        "is_error": False,
        "sources": [],
        "sequence": 3,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.choices[0].delta.content is None
    assert chunk.fred is None


def test_tool_result_with_sources_populates_fred_sources() -> None:
    event = {
        "kind": "tool_result",
        "call_id": "call-abc",
        "content": "found it",
        "is_error": False,
        "sources": [
            {
                "title": "Doc A",
                "uid": "uid-1",
                "page": 3,
                "score": 0.92,
                "citation_url": "/documents/uid-1#chunk=42",
            }
        ],
        "sequence": 3,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.fred is not None
    assert len(chunk.fred.sources) == 1
    src = chunk.fred.sources[0]
    assert src.title == "Doc A"
    assert src.uid == "uid-1"
    assert src.page == 3
    assert src.score == 0.92
    assert src.citation_url == "/documents/uid-1#chunk=42"


# ---------------------------------------------------------------------------
# final
# ---------------------------------------------------------------------------


def test_final_sets_finish_reason_stop() -> None:
    event = {
        "kind": "final",
        "content": "done",
        "sources": [],
        "finish_reason": "stop",
        "token_usage": {"input": 10, "output": 5},
        "sequence": 4,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.choices[0].finish_reason == "stop"
    assert chunk.choices[0].delta.content is None
    assert chunk.fred is not None
    assert chunk.fred.token_usage == {"input": 10, "output": 5}
    assert chunk.fred.sources == []


def test_final_with_null_finish_reason_defaults_to_stop() -> None:
    event = {
        "kind": "final",
        "content": "",
        "sources": [],
        "finish_reason": None,
        "sequence": 4,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.choices[0].finish_reason == "stop"


def test_final_with_sources_populates_fred_sources() -> None:
    event = {
        "kind": "final",
        "content": "answer",
        "sources": [{"title": "Doc B", "uid": "uid-2", "score": 0.88}],
        "finish_reason": "stop",
        "sequence": 4,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.fred is not None
    assert len(chunk.fred.sources) == 1
    assert chunk.fred.sources[0].title == "Doc B"


# ---------------------------------------------------------------------------
# awaiting_human
# ---------------------------------------------------------------------------


def test_awaiting_human_sets_stop_and_hitl_payload() -> None:
    hitl_request = {
        "title": "Approve?",
        "question": "Do you want to proceed?",
        "choices": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
        "free_text": False,
        "checkpoint_id": "cp-1",
    }
    event = {
        "kind": "awaiting_human",
        "request": hitl_request,
        "sequence": 5,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.choices[0].finish_reason == "stop"
    assert chunk.fred is not None
    # awaiting_human is now typed as HumanInputRequest, not a raw dict
    from fred_sdk.contracts.runtime import HumanInputRequest

    assert isinstance(chunk.fred.awaiting_human, HumanInputRequest)
    assert chunk.fred.awaiting_human.title == "Approve?"
    assert chunk.fred.awaiting_human.question == "Do you want to proceed?"
    assert chunk.fred.awaiting_human.checkpoint_id == "cp-1"
    assert len(chunk.fred.awaiting_human.choices) == 2


# ---------------------------------------------------------------------------
# node_error
# ---------------------------------------------------------------------------


def test_node_error_sets_stop_and_error_message() -> None:
    event = {
        "kind": "node_error",
        "node_id": "tool_node",
        "error_message": "MCP server timeout",
        "routed_to": "error_handler",
        "sequence": 3,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.choices[0].finish_reason == "stop"
    assert chunk.fred is not None
    assert chunk.fred.node_error == "MCP server timeout"


# ---------------------------------------------------------------------------
# status — should be dropped
# ---------------------------------------------------------------------------


def test_status_event_is_dropped() -> None:
    event = {"kind": "status", "status": "Starting", "detail": None, "sequence": 0}
    assert _chunk(event) is None


# ---------------------------------------------------------------------------
# unknown kind — should be dropped
# ---------------------------------------------------------------------------


def test_unknown_kind_is_dropped() -> None:
    event = {"kind": "future_event_type", "data": "whatever"}
    assert _chunk(event) is None


# ---------------------------------------------------------------------------
# serialisation — exclude_none must produce clean JSON
# ---------------------------------------------------------------------------


def test_chunk_serialises_without_none_fields() -> None:
    event = {"kind": "assistant_delta", "delta": "hi", "sequence": 1}
    chunk = _chunk(event)

    assert chunk is not None
    raw = chunk.model_dump_json(exclude_none=True)
    data = json.loads(raw)

    # fred should be absent entirely when None
    assert "fred" not in data
    # finish_reason should be absent when None
    assert "finish_reason" not in data["choices"][0]


def test_final_chunk_serialises_fred_namespace() -> None:
    event = {
        "kind": "final",
        "content": "done",
        "sources": [{"title": "Doc A", "uid": "u1", "score": 0.9}],
        "finish_reason": "stop",
        "token_usage": {"input": 20, "output": 10},
        "sequence": 5,
    }
    chunk = _chunk(event)

    assert chunk is not None
    raw = chunk.model_dump_json(exclude_none=True)
    data = json.loads(raw)

    assert data["fred"]["token_usage"] == {"input": 20, "output": 10}
    assert data["fred"]["sources"][0]["title"] == "Doc A"


# ---------------------------------------------------------------------------
# OpenAIChatRequest validation
# ---------------------------------------------------------------------------


def test_openai_chat_request_requires_at_least_one_message() -> None:
    with pytest.raises(Exception):
        OpenAIChatRequest(model="my-agent", messages=[])


def test_openai_chat_request_accepts_valid_payload() -> None:
    req = OpenAIChatRequest(
        model="my-agent",
        messages=[OpenAIMessage(role="user", content="hello")],
    )
    assert req.model == "my-agent"
    assert req.stream is True


# ---------------------------------------------------------------------------
# ui_parts — carried in tool_result and final events
# ---------------------------------------------------------------------------


def test_tool_result_with_ui_parts_populates_fred_ui_parts() -> None:
    event = {
        "kind": "tool_result",
        "call_id": "call-abc",
        "content": "map data",
        "is_error": False,
        "sources": [],
        "ui_parts": [
            {
                "type": "link",
                "href": "https://example.com/doc.pdf",
                "title": "Report",
                "kind": "download",
            }
        ],
        "sequence": 3,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.fred is not None
    assert len(chunk.fred.ui_parts) == 1
    from fred_sdk.contracts.context import LinkPart

    part = chunk.fred.ui_parts[0]
    assert isinstance(part, LinkPart)
    assert part.href == "https://example.com/doc.pdf"
    assert part.title == "Report"


def test_final_event_with_geo_ui_part_populates_fred() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
                "properties": {"name": "Paris"},
            }
        ],
    }
    event = {
        "kind": "final",
        "content": "Here is the map.",
        "sources": [],
        "finish_reason": "stop",
        "ui_parts": [{"type": "geo", "geojson": geojson}],
        "sequence": 4,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.fred is not None
    assert len(chunk.fred.ui_parts) == 1
    from fred_sdk.contracts.context import GeoPart

    part = chunk.fred.ui_parts[0]
    assert isinstance(part, GeoPart)
    assert part.geojson["type"] == "FeatureCollection"


def test_awaiting_human_with_typed_hitl_object() -> None:
    from fred_sdk.contracts.runtime import HumanInputRequest

    hitl = HumanInputRequest(
        title="Confirm?",
        question="Are you sure?",
        free_text=True,
        checkpoint_id="cp-99",
    )
    event = {
        "kind": "awaiting_human",
        "request": hitl,
        "sequence": 6,
    }
    chunk = _chunk(event)

    assert chunk is not None
    assert chunk.fred is not None
    assert isinstance(chunk.fred.awaiting_human, HumanInputRequest)
    assert chunk.fred.awaiting_human.title == "Confirm?"
    assert chunk.fred.awaiting_human.checkpoint_id == "cp-99"
