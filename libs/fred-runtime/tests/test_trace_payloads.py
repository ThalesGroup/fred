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

from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message
from fred_runtime.runtime_support.trace_payloads import (
    final_assistant_message,
    serialize_message,
    serialize_messages,
    serialize_model_output,
    to_langfuse_usage,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


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
