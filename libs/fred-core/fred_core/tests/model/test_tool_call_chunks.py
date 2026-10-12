# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Lock down the internal LangChain compatibility guard when upgrading models."""

import json
from itertools import product
from unittest.mock import Mock

import pytest
from fred_core.model import tool_call_chunks
from langchain_core.messages import AIMessageChunk, ai
from langchain_core.utils import json as json_utils
from langchain_openai.chat_models.base import _convert_delta_to_message_chunk


@pytest.fixture(autouse=True)
def restore_parser(monkeypatch):
    monkeypatch.setattr(ai, "parse_partial_json", json_utils.parse_partial_json)


def chunk(args, index=0):
    return AIMessageChunk(
        content="",
        tool_call_chunks=[
            {"name": "write", "args": args, "id": "call", "index": index}
        ],
    )


def test_guard_preserves_complete_chunk_metadata_for_fragments():
    documents = [
        json.dumps(
            {"text": 'café\nquoted "text" \\ path', "list": [1, None, {"x": True}]}
        ),
        "{}",
        '{"x":1}',
        ' {"x": "unfinished',
        '{"bad": tru',
    ]
    fragments = ["", " ", "\ufeff{}", "null", "1", "[{}]", "\t\r\n{}", "x" * 1000]
    for document in documents:
        fragments.extend(document[:i] for i in range(len(document) + 1))
        fragments.extend(document[i:] for i in range(len(document)))
    fragments.extend("".join(chars) for chars in product('{}[]"\\ab0 \n', repeat=3))
    expected = [chunk(s).model_dump() for s in fragments]
    tool_call_chunks.install_tool_fragment_guard()
    assert [chunk(s).model_dump() for s in fragments] == expected
    assert json_utils.parse_partial_json("[1") == [1]  # Public parser is untouched.


def test_guard_skips_impossible_object_prefix_without_losing_raw_arguments(monkeypatch):
    tool_call_chunks.install_tool_fragment_guard()
    installed = getattr(ai, "parse_partial_json")
    tool_call_chunks.install_tool_fragment_guard()
    assert getattr(ai, "parse_partial_json") is installed
    parser = Mock(wraps=json_utils.parse_partial_json)
    monkeypatch.setattr(tool_call_chunks, "parse_partial_json", parser)
    argument = "x" * 20000
    delta = {
        "role": "assistant",
        "tool_calls": [
            {
                "index": 0,
                "id": "call",
                "function": {"name": "write", "arguments": argument},
            }
        ],
    }
    result = _convert_delta_to_message_chunk(delta, AIMessageChunk)
    assert isinstance(result, AIMessageChunk)
    assert result.tool_call_chunks[0]["args"] == argument
    assert result.invalid_tool_calls[0]["args"] == argument
    parser.assert_not_called()


def test_fragments_merge_to_the_same_multiple_tool_calls():
    fragments = [
        chunk('{"text":"'),
        chunk("x" * 20000),
        chunk('"}'),
        chunk('{"other":true}', 1),
    ]
    baseline = sum(fragments[1:], fragments[0]).model_dump()
    tool_call_chunks.install_tool_fragment_guard()
    guarded = [
        chunk('{"text":"'),
        chunk("x" * 20000),
        chunk('"}'),
        chunk('{"other":true}', 1),
    ]
    result = sum(guarded[1:], guarded[0])
    assert result.model_dump() == baseline
    assert result.tool_calls[0]["args"] == {"text": "x" * 20000}
    assert result.tool_calls[1]["args"] == {"other": True}


def test_model_factory_installs_guard(monkeypatch):
    from fred_core.model import factory
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    model = FakeListChatModel(responses=["ok"])
    monkeypatch.setattr(factory, "_create_model", lambda cfg: model)
    assert factory.get_model(None) is model
    assert getattr(ai, "parse_partial_json") is tool_call_chunks._parse_object_fragment
