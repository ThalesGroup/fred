import httpx

from agentic_backend.core.chatbot.chatbot_controller import _summarize_error


def test_summarize_error_empty_message_falls_back_to_type_name():
    """httpx timeouts stringify to "" — the summary must not be empty (it would
    render as a blank "Détail :" in the UI)."""
    summary = _summarize_error(httpx.ReadTimeout(""))
    assert summary == "ReadTimeout"


def test_summarize_error_keeps_message_when_present():
    summary = _summarize_error(ValueError("bad payload"))
    assert summary == "ValueError: bad payload"
