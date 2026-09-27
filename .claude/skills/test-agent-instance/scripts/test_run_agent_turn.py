"""Offline regression tests for evidence preservation and truthful completion."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "run_agent_turn", Path(__file__).with_name("run_agent_turn.py")
)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_final_is_authoritative_and_untruncated(tmp_path):
    answer = "full final answer " * 1000
    events = [
        {"kind": "assistant_delta", "delta": "intermediate text"},
        {"kind": "tool_call", "call_id": "a", "tool_name": "task"},
        {"kind": "tool_call", "call_id": "b", "tool_name": "task"},
        {"kind": "tool_result", "call_id": "b", "is_error": False},
        {"kind": "tool_result", "call_id": "a", "is_error": True},
        {"kind": "final", "content": answer, "token_usage": {"input_tokens": 25}},
    ]
    assert helper.capture(events, tmp_path, "task", []) == 0
    assert (tmp_path / "final.md").read_text() == answer
    assert [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ] == events
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["peak_outstanding_observed_calls"] == 2
    assert summary["observed_calls"]["a"]["is_error"] is True
    assert summary["observed_calls"]["b"]["is_error"] is False
    assert (tmp_path / "final.md").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "ending",
    [
        [],
        [{"kind": "awaiting_human"}],
        [{"kind": "execution_error"}],
        [{"kind": "node_error"}],
    ],
)
def test_incomplete_stream_does_not_claim_delta_as_final(tmp_path, ending):
    assert (
        helper.capture(
            [{"kind": "assistant_delta", "delta": "partial"}, *ending],
            tmp_path,
            "task",
            [],
        )
        == 1
    )
    assert (tmp_path / "final.md").read_text() == ""


def test_transport_failure_preserves_partial_events_without_exception_secrets(tmp_path):
    def events():
        yield {"kind": "status", "status": "running"}
        raise httpx.ReadTimeout("credential-in-exception")

    assert helper.capture(events(), tmp_path, "task", []) == 1
    summary = (tmp_path / "summary.json").read_text()
    assert "ReadTimeout" in summary
    assert "credential-in-exception" not in summary
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 1


def test_known_credentials_redacted_before_json_encoding(tmp_path):
    secret = 'quote"newline\nsecret'
    events = [{"kind": "final", "content": secret, "metadata": {"token": secret}}]
    assert helper.capture(events, tmp_path, "task", [secret]) == 0
    event = json.loads((tmp_path / "events.jsonl").read_text())
    assert event["content"] == "[REDACTED]"
    assert event["metadata"]["token"] == "[REDACTED]"
    assert (tmp_path / "final.md").read_text() == "[REDACTED]"
