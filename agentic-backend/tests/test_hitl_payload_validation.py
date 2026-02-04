import pytest

from agentic_backend.core.chatbot.chat_schema import validate_hitl_payload


def test_valid_minimal_question_choices():
    payload = {
        "question": "Proceed?",
        "choices": [{"id": "yes", "label": "Yes"}],
    }
    validated = validate_hitl_payload(payload)
    assert validated.question == "Proceed?"
    assert validated.choices and validated.choices[0].id == "yes"


def test_duplicate_choice_ids_rejected():
    payload = {
        "question": "Choose",
        "choices": [
            {"id": "dup", "label": "A"},
            {"id": "dup", "label": "B"},
        ],
    }
    with pytest.raises(ValueError):
        validate_hitl_payload(payload)


def test_multiple_defaults_rejected():
    payload = {
        "question": "Pick one",
        "choices": [
            {"id": "a", "label": "A", "default": True},
            {"id": "b", "label": "B", "default": True},
        ],
    }
    with pytest.raises(ValueError):
        validate_hitl_payload(payload)


def test_payload_without_question_or_title_rejected():
    payload = {"choices": [{"id": "a", "label": "A"}]}
    with pytest.raises(ValueError):
        validate_hitl_payload(payload)


def test_payload_accepts_extra_keys():
    payload = {
        "question": "Proceed?",
        "choices": [{"id": "yes", "label": "Yes"}],
        "extra_field": "ok",
    }
    validated = validate_hitl_payload(payload)
    assert validated.model_extra.get("extra_field") == "ok"
