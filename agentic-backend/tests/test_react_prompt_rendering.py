from __future__ import annotations

import pytest

from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.core.agents.v2.react.react_prompting import render_prompt_template


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s1", user_id="u1", language="en-US"),
        portable_context=PortableContext(
            request_id="req-s1",
            correlation_id="corr-s1",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id="s1",
            agent_id="test-agent",
        ),
    )


def _render(template: str) -> str:
    return render_prompt_template(template, binding=_binding(), agent_id="test-agent")


def test_known_tokens_are_substituted():
    result = _render(
        "Session {session_id} for {user_id} in {response_language} on {today}."
    )
    assert "{" not in result
    assert "s1" in result
    assert "u1" in result
    assert "English" in result


def test_unknown_simple_key_preserved():
    result = _render("Answer the {question} carefully.")
    assert "{question}" in result


@pytest.mark.parametrize(
    "template",
    [
        # attribute access — was crashing with AttributeError
        "function main(workbook: ExcelScript.Workbook) { let x = workbook.getActiveSheet() }",
        "{toto.toto}",
        # empty braces — was crashing with IndexError
        "function main() { ... }",
        "{}",
        # item access
        "{key[0]}",
    ],
)
def test_code_like_braces_do_not_crash(template: str):
    result = _render(template)
    assert result == template
