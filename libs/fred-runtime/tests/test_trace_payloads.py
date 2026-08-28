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

"""Shaping of trace payloads: prompt rendering and token-usage translation."""

import json

from fred_runtime.integrations.v2_runtime.adapters import _truncate_payload
from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message
from fred_runtime.runtime_support.trace_payloads import (
    CHAR_USAGE_KEYS,
    final_assistant_message,
    model_request_char_sizes,
    serialize_message,
    serialize_messages,
    serialize_model_output,
    serialize_model_request,
    serialize_tools,
    to_langfuse_usage,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


def test_fred_usage_keys_map_to_langfuse_names() -> None:
    usage = to_langfuse_usage(
        {
            "input_tokens": 812,
            "output_tokens": 96,
            "total_tokens": 908,
            "cache_read_tokens": 400,
            "cache_creation_tokens": 0,
        }
    )

    assert usage == {
        "input": 812,
        "output": 96,
        "total": 908,
        "cache_read_input_tokens": 400,
    }


def test_zero_valued_entries_are_dropped() -> None:
    """A provider reporting no cache usage sends zeros; rendering them is noise."""

    assert to_langfuse_usage(
        {"input_tokens": 5, "output_tokens": 0, "cache_read_tokens": 0}
    ) == {"input": 5}


def test_absent_or_empty_usage_is_none() -> None:
    assert to_langfuse_usage(None) is None
    assert to_langfuse_usage({}) is None
    assert to_langfuse_usage({"input_tokens": 0}) is None


# ---------------------------------------------------------------------------
# Provider coverage — the "works with any model" guarantee
# ---------------------------------------------------------------------------
#
# Providers do not agree on where token usage lives. `runtime_metadata_from_message`
# already normalizes ~a dozen conventions; these cases pin the end-to-end chain
# (provider payload → Fred shape → Langfuse `usage_details`) for the shapes Fred
# actually meets, so a new provider that reports usage at all lands in a trace
# without touching the tracing code.


def _usage_of(message: AIMessage) -> dict[str, int] | None:
    _, token_usage, _ = runtime_metadata_from_message(message)
    return to_langfuse_usage(token_usage)


def test_langchain_standard_usage_metadata_reaches_langfuse() -> None:
    message = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 812, "output_tokens": 96, "total_tokens": 908},
    )

    assert _usage_of(message) == {"input": 812, "output": 96, "total": 908}


def test_openai_compatible_token_usage_reaches_langfuse() -> None:
    """Mistral, and any gateway Fred reaches through the OpenAI wrapper."""

    message = AIMessage(
        content="hi",
        response_metadata={
            "model_name": "mistral-small-latest",
            "token_usage": {
                "prompt_tokens": 812,
                "completion_tokens": 96,
                "total_tokens": 908,
            },
        },
    )

    assert _usage_of(message) == {"input": 812, "output": 96, "total": 908}


def test_anthropic_style_usage_reaches_langfuse() -> None:
    message = AIMessage(
        content="hi",
        response_metadata={"usage": {"input_tokens": 812, "output_tokens": 96}},
    )

    # No total reported by the provider — derived rather than left missing.
    assert _usage_of(message) == {"input": 812, "output": 96, "total": 908}


def test_ollama_style_counters_reach_langfuse() -> None:
    message = AIMessage(
        content="hi",
        response_metadata={
            "usage": {"prompt_eval_count": 812, "eval_count": 96},
        },
    )

    assert _usage_of(message) == {"input": 812, "output": 96, "total": 908}


def test_prompt_cache_hits_are_reported_separately() -> None:
    message = AIMessage(
        content="hi",
        usage_metadata={
            "input_tokens": 812,
            "output_tokens": 96,
            "total_tokens": 908,
            "input_token_details": {"cache_read": 400},
        },
    )

    usage = _usage_of(message)
    assert usage is not None
    assert usage["cache_read_input_tokens"] == 400


def test_a_provider_reporting_nothing_yields_no_usage() -> None:
    """A silent provider leaves the generation without tokens — visibly, not wrongly."""

    assert _usage_of(AIMessage(content="hi")) is None
    assert _usage_of(AIMessage(content="hi", response_metadata={"model": "x"})) is None


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------


def test_roles_use_the_chat_completion_vocabulary() -> None:
    """Langfuse's message viewer renders these roles as a conversation."""

    assert serialize_message(HumanMessage(content="hi"))["role"] == "user"
    assert serialize_message(AIMessage(content="yo"))["role"] == "assistant"
    assert serialize_message(SystemMessage(content="be nice"))["role"] == "system"
    assert (
        serialize_message(ToolMessage(content="42", tool_call_id="c1"))["role"]
        == "tool"
    )


def test_a_separately_held_system_prompt_is_prepended() -> None:
    """Omitting it misrepresents what the model actually received."""

    payload = serialize_messages(
        [HumanMessage(content="hello")], system_prompt="you are fred"
    )

    assert payload == [
        {"role": "system", "content": "you are fred"},
        {"role": "user", "content": "hello"},
    ]


def test_tool_calls_are_kept_with_their_arguments() -> None:
    message = AIMessage(
        content="",
        tool_calls=[{"name": "search", "args": {"query": "fred"}, "id": "call-1"}],
    )

    assert serialize_message(message)["tool_calls"] == [
        {"name": "search", "args": {"query": "fred"}, "id": "call-1"}
    ]


def test_multimodal_blocks_are_reduced_to_text_and_type_names() -> None:
    """A base64 image would blow the payload budget and tell a reader nothing."""

    message = HumanMessage(
        content=[
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]
    )

    assert serialize_message(message)["content"] == "describe this[image_url]"


def test_a_lone_plain_answer_collapses_to_its_text() -> None:
    """A one-element list of dicts around a sentence only hurts readability."""

    assert serialize_model_output([AIMessage(content="the answer")]) == "the answer"


def test_a_tool_calling_answer_keeps_its_structure() -> None:
    output = serialize_model_output(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search", "args": {}, "id": "c1"}],
            )
        ]
    )

    assert isinstance(output, list)
    assert output[0]["tool_calls"][0]["name"] == "search"


def test_the_final_assistant_message_is_the_last_one() -> None:
    messages = [
        AIMessage(content="first"),
        ToolMessage(content="result", tool_call_id="c1"),
        AIMessage(content="last"),
    ]

    found = final_assistant_message(messages)
    assert found is not None and found.content == "last"


def test_no_assistant_message_yields_none() -> None:
    assert final_assistant_message([HumanMessage(content="hi")]) is None


# ---------------------------------------------------------------------------
# Tool definitions (the `tools` request parameter)
# ---------------------------------------------------------------------------


class _QueryArgs(BaseModel):
    sql: str = Field(description="the SQL to run")
    dataset_uids: list[str] | None = None


def _read_query_tool() -> StructuredTool:
    return StructuredTool.from_function(
        func=lambda **kwargs: None,
        name="read_query",
        description="Execute one read-only SQL query",
        args_schema=_QueryArgs,
    )


def test_a_tool_contributes_its_argument_schema() -> None:
    """
    The argument schema reaches the model through `tools` and nowhere else — the
    system prompt names arguments in prose at best, never their types. A capture
    that drops it hides the contract tool calls are generated against (#2412).
    """

    [entry] = serialize_tools([_read_query_tool()])

    assert entry["name"] == "read_query"
    assert entry["description"] == "Execute one read-only SQL query"
    schema = json.loads(entry["parameters"])
    assert schema["properties"]["sql"]["type"] == "string"
    assert schema["required"] == ["sql"]


def test_a_provider_native_tool_dict_is_unwrapped_not_re_encoded() -> None:
    """`ModelRequest.tools` mixes LangChain tools and raw provider dicts."""

    native = {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "search",
            "parameters": {"type": "object"},
        },
    }

    assert serialize_tools([native]) == [
        {
            "name": "web_search",
            "description": "search",
            "parameters": '{"type": "object"}',
        }
    ]


def test_an_mcp_tool_carries_its_dict_schema() -> None:
    """
    `langchain_mcp_adapters` sets `args_schema=tool.inputSchema` — a plain dict,
    not a pydantic class. That branch must reach the trace like any other.
    """

    class _McpStyleTool:
        name = "read_query"
        description = "Execute one read-only SQL query"
        args_schema = {
            "type": "object",
            "properties": {"sql": {"type": "string", "minLength": 1}},
            "required": ["sql"],
        }

    [entry] = serialize_tools([_McpStyleTool()])

    assert json.loads(entry["parameters"])["required"] == ["sql"]


def test_an_argument_schema_is_one_truncatable_string_not_a_nested_tree() -> None:
    """
    `_truncate_payload` emits strings of 64 characters or less verbatim past the
    budget and never walks dict keys. A JSON schema is almost entirely both, so
    left nested it escapes the content cap — measured at 47x a 100-character
    budget before this was a string. Keeping it as one string makes it a single
    truncatable unit, so the cap applies to tools as it does to message content.
    """

    [entry] = serialize_tools([_read_query_tool()])
    assert isinstance(entry["parameters"], str)

    bounded = _truncate_payload({"tools": [entry]}, 100)
    assert len(json.dumps(bounded, ensure_ascii=False)) < 400


def test_an_argument_schema_is_rendered_once_per_class_not_once_per_call() -> None:
    """
    `model_json_schema()` rebuilds the schema every call — 2.1 ms for the five
    Tabular MCP tools, synchronous on the event loop, for a result that cannot
    differ between two calls of the same agent binding. Re-rendering it on every
    model call would put that cost on the per-turn hot path for nothing.
    """

    renders = 0

    class _CountingArgs(BaseModel):
        sql: str

        @classmethod
        def model_json_schema(
            cls, *args: object, **kwargs: object
        ) -> dict[str, object]:  # type: ignore[override]
            nonlocal renders
            renders += 1
            return {"type": "object", "properties": {"sql": {"type": "string"}}}

    tool = StructuredTool.from_function(
        func=lambda **kwargs: None,
        name="counting",
        description="counts renders",
        args_schema=_CountingArgs,
    )

    first = serialize_tools([tool])
    for _ in range(5):
        assert serialize_tools([tool]) == first

    assert renders == 1


def test_a_tool_whose_schema_will_not_render_still_traces() -> None:
    """Tracing may never fail the turn it is observing."""

    class _Exploding:
        name = "boom"
        description = "raises on schema access"

        @staticmethod
        def model_json_schema() -> dict[str, object]:
            raise RuntimeError("no schema for you")

    class _Tool:
        name = "boom"
        description = "raises on schema access"
        args_schema = _Exploding

    [entry] = serialize_tools([_Tool()])

    assert entry["name"] == "boom"
    assert entry["parameters"] is None


def test_a_request_with_tools_carries_messages_and_tools() -> None:
    payload = serialize_model_request(
        [HumanMessage(content="combien de voitures ?")],
        system_prompt="you are fred",
        tools=[_read_query_tool()],
    )

    assert isinstance(payload, dict)
    assert payload["messages"] == [
        {"role": "system", "content": "you are fred"},
        {"role": "user", "content": "combien de voitures ?"},
    ]
    assert [tool["name"] for tool in payload["tools"]] == ["read_query"]


def test_messages_precede_tools_so_truncation_spends_on_them_first() -> None:
    """
    `_truncate_payload` walks a mapping in insertion order. Tools first would
    let schema boilerplate eat the content budget and blank out the question and
    the answer — the regression the list-walks-backwards rule already prevents.
    """

    payload = serialize_model_request(
        [HumanMessage(content="hi")], tools=[_read_query_tool()]
    )

    assert isinstance(payload, dict)
    assert list(payload) == ["messages", "tools"]


def test_a_tool_less_agent_keeps_the_bare_message_list() -> None:
    """No tools, no shape change: same payload and same chat rendering as before."""

    for empty in ([], None):
        payload = serialize_model_request(
            [HumanMessage(content="hello")], system_prompt="you are fred", tools=empty
        )

        assert payload == [
            {"role": "system", "content": "you are fred"},
            {"role": "user", "content": "hello"},
        ]


# ---------------------------------------------------------------------------
# Character sizes reported next to the token counts
# ---------------------------------------------------------------------------


def test_char_usage_keys_never_collide_with_langfuse_token_aggregates() -> None:
    """
    Verified against a live Langfuse 4.7: the server folds any usage-detail key
    it reads as an input or output variant into the aggregate `usage` object. A
    key named `input_chars` was summed into `usage.input`, which then reported
    157 944 "TOKENS" for 32 155 tokens plus 125 789 characters. The `chars_`
    prefix is what keeps the token totals intact, so it is pinned here rather
    than left to whoever next adds a counter.
    """

    for key in CHAR_USAGE_KEYS:
        assert key.startswith("chars_")
        assert not key.startswith(("input", "output", "total"))


def test_each_request_field_is_measured_separately() -> None:
    """
    One aggregate size would not answer the question the split exists for:
    whether a large payload is a long conversation or a large tool catalogue.
    """

    sizes = model_request_char_sizes(
        [HumanMessage(content="combien de voitures ?")],
        system_prompt="you are fred",
        tools=[_read_query_tool()],
    )

    assert set(sizes) == set(CHAR_USAGE_KEYS)
    assert sizes["chars_system"] == len("you are fred")
    assert sizes["chars_messages"] == len("combien de voitures ?")
    # name + description + the JSON argument schema
    assert sizes["chars_tools"] > len("Execute one read-only SQL query")


def test_sizes_are_reported_with_no_tools_and_no_system_prompt() -> None:
    """Every key is always present: a missing key reads as unknown, not as zero."""

    sizes = model_request_char_sizes([HumanMessage(content="hi")])

    assert sizes == {"chars_system": 0, "chars_messages": 2, "chars_tools": 0}


def test_multimodal_content_is_measured_as_the_text_the_trace_shows() -> None:
    """
    A base64 image is reduced to its type name everywhere else in this module;
    measuring the raw blob here would report a size no captured payload matches.
    """

    message = HumanMessage(
        content=[
            {"type": "text", "text": "describe this"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + "A" * 5000},
            },
        ]
    )

    sizes = model_request_char_sizes([message])

    assert sizes["chars_messages"] == len("describe this[image_url]")
