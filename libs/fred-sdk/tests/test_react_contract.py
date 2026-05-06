"""
Offline unit tests for fred_sdk.contracts.react_contract.

Covers:
- ReActMessageRole enum values
- ReActToolCall construction and defaults
- ReActMessage validators (tool_calls role constraint, tool_call_id role constraint)
- ReActInput validators (non-empty messages, at least one USER message)
- ReActOutput construction
"""

from __future__ import annotations

import pytest

from fred_sdk.contracts.react_contract import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActOutput,
    ReActToolCall,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(content: str = "hello") -> ReActMessage:
    return ReActMessage(role=ReActMessageRole.USER, content=content)


def _assistant(content: str = "ok") -> ReActMessage:
    return ReActMessage(role=ReActMessageRole.ASSISTANT, content=content)


def _system(content: str = "you are helpful") -> ReActMessage:
    return ReActMessage(role=ReActMessageRole.SYSTEM, content=content)


def _tool(content: str = "result", *, call_id: str = "c1") -> ReActMessage:
    return ReActMessage(
        role=ReActMessageRole.TOOL, content=content, tool_call_id=call_id
    )


# ---------------------------------------------------------------------------
# ReActToolCall
# ---------------------------------------------------------------------------


class TestReActToolCall:
    def test_minimal_construction(self) -> None:
        tc = ReActToolCall(call_id="c1", name="search")
        assert tc.call_id == "c1"
        assert tc.name == "search"
        assert tc.arguments == {}

    def test_with_arguments(self) -> None:
        tc = ReActToolCall(call_id="c1", name="search", arguments={"q": "cats"})
        assert tc.arguments == {"q": "cats"}

    def test_empty_call_id_rejected(self) -> None:
        with pytest.raises(Exception):
            ReActToolCall(call_id="", name="search")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(Exception):
            ReActToolCall(call_id="c1", name="")


# ---------------------------------------------------------------------------
# ReActMessage — basic construction
# ---------------------------------------------------------------------------


class TestReActMessageConstruction:
    def test_user_message(self) -> None:
        m = _user("what is 2+2?")
        assert m.role == ReActMessageRole.USER
        assert m.content == "what is 2+2?"
        assert m.tool_calls == ()

    def test_empty_content_allowed(self) -> None:
        m = ReActMessage(role=ReActMessageRole.USER, content="")
        assert m.content == ""

    def test_system_message(self) -> None:
        m = _system()
        assert m.role == ReActMessageRole.SYSTEM


# ---------------------------------------------------------------------------
# ReActMessage — tool_calls constraint
# ---------------------------------------------------------------------------


class TestReActMessageToolCallsConstraint:
    def test_assistant_may_have_tool_calls(self) -> None:
        tc = ReActToolCall(call_id="c1", name="search")
        m = ReActMessage(role=ReActMessageRole.ASSISTANT, content="", tool_calls=(tc,))
        assert len(m.tool_calls) == 1

    def test_user_with_tool_calls_rejected(self) -> None:
        tc = ReActToolCall(call_id="c1", name="search")
        with pytest.raises(Exception, match="assistant messages"):
            ReActMessage(role=ReActMessageRole.USER, content="hi", tool_calls=(tc,))

    def test_tool_role_with_tool_calls_rejected(self) -> None:
        tc = ReActToolCall(call_id="c1", name="search")
        with pytest.raises(Exception, match="assistant messages"):
            ReActMessage(
                role=ReActMessageRole.TOOL,
                content="result",
                tool_call_id="c1",
                tool_calls=(tc,),
            )

    def test_system_with_tool_calls_rejected(self) -> None:
        tc = ReActToolCall(call_id="c1", name="search")
        with pytest.raises(Exception, match="assistant messages"):
            ReActMessage(role=ReActMessageRole.SYSTEM, content="sys", tool_calls=(tc,))


# ---------------------------------------------------------------------------
# ReActMessage — tool_call_id constraint
# ---------------------------------------------------------------------------


class TestReActMessageToolCallIdConstraint:
    def test_tool_message_may_have_call_id(self) -> None:
        m = _tool("result", call_id="c1")
        assert m.tool_call_id == "c1"

    def test_user_with_call_id_rejected(self) -> None:
        with pytest.raises(Exception, match="tool messages"):
            ReActMessage(role=ReActMessageRole.USER, content="hi", tool_call_id="c1")

    def test_assistant_with_call_id_rejected(self) -> None:
        with pytest.raises(Exception, match="tool messages"):
            ReActMessage(
                role=ReActMessageRole.ASSISTANT, content="ok", tool_call_id="c1"
            )


# ---------------------------------------------------------------------------
# ReActInput validators
# ---------------------------------------------------------------------------


class TestReActInputValidation:
    def test_single_user_message_valid(self) -> None:
        inp = ReActInput(messages=(_user(),))
        assert len(inp.messages) == 1

    def test_multi_turn_transcript_valid(self) -> None:
        inp = ReActInput(
            messages=(
                _system(),
                _user("question"),
                _assistant("answer"),
                _user("follow-up"),
            )
        )
        assert len(inp.messages) == 4

    def test_empty_messages_rejected(self) -> None:
        with pytest.raises(Exception, match="at least one message"):
            ReActInput(messages=())

    def test_no_user_message_rejected(self) -> None:
        with pytest.raises(Exception, match="at least one user message"):
            ReActInput(messages=(_system(), _assistant()))

    def test_only_tool_messages_rejected(self) -> None:
        with pytest.raises(Exception, match="at least one user message"):
            ReActInput(messages=(_tool(),))


# ---------------------------------------------------------------------------
# ReActOutput
# ---------------------------------------------------------------------------


class TestReActOutput:
    def test_construction(self) -> None:
        final = _assistant("final answer")
        out = ReActOutput(final_message=final, transcript=(_user(), final))
        assert out.final_message.content == "final answer"
        assert len(out.transcript) == 2
