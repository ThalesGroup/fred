from __future__ import annotations

import pytest
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.runtime import (
    HumanChoiceOption,
    HumanInputRequest,
    parse_human_input_answer,
)


def test_ask_user_context_distinguishes_absent_and_disabled() -> None:
    assert "ask_user" not in RuntimeContext().model_dump(exclude_none=True)
    assert (
        RuntimeContext(ask_user=False).model_dump(exclude_none=True)["ask_user"]
        is False
    )
    assert (
        RuntimeContext(ask_user=True).model_dump(exclude_none=True)["ask_user"] is True
    )


def test_human_answer_preserves_choice_and_comment() -> None:
    request = HumanInputRequest(
        question="Where?",
        choices=(HumanChoiceOption(id="a", label="A"),),
        free_text=True,
    )
    answer = parse_human_input_answer(
        {"answer": "a", "choice_id": "a", "text": "Please explain."},
        request,
    )
    assert answer.choice_id == "a"
    assert answer.text == "Please explain."
    assert not answer.skipped


def test_human_answer_accepts_text_only_and_explicit_skip() -> None:
    request = HumanInputRequest(question="Why?", free_text=True)
    assert parse_human_input_answer({"answer": "Because"}, request).text == "Because"
    assert parse_human_input_answer({"skipped": True}, request).skipped


@pytest.mark.parametrize(
    "payload",
    [
        {"choice_id": "missing"},
        {"choice_id": "a", "text": "not allowed"},
        {"skipped": True, "choice_id": "a"},
        {"skipped": "yes"},
    ],
)
def test_invalid_human_answer_is_rejected(payload: dict[str, object]) -> None:
    request = HumanInputRequest(
        question="Choose",
        choices=(HumanChoiceOption(id="a", label="A"),),
    )
    with pytest.raises(ValueError):
        parse_human_input_answer(payload, request)
