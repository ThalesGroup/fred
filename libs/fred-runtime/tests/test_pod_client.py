"""
Offline unit tests for fred_runtime.cli.pod_client.AgentPodClient.

AgentPodClient accepts an injected httpx.Client, which makes it testable
without a running pod. httpx.MockTransport is used to supply canned responses;
no network traffic is issued.

Coverage focus:
- auth header selection (_auth_headers)
- payload construction in execute / evaluate (optional field inclusion)
- response-shape validation (list_agents, execute, iter_stream_events, ...)
- SSE line parsing in iter_stream_events
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from fred_runtime.cli.pod_client import AgentPodClient

BASE_URL = "http://test-pod/fred/agents/v2"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    token_provider: Callable[[], str | None] | None = None,
) -> AgentPodClient:
    return AgentPodClient(
        base_url=BASE_URL,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=token_provider,
    )


class _Capture:
    """Records every request; returns a fixed response."""

    def __init__(self, response: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []
        self._response = response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._response

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> dict[str, Any]:
        return json.loads(self.last.content)


def _json_response(data: Any, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=data)


def _sse_response(*events: dict[str, Any]) -> httpx.Response:
    lines = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    return httpx.Response(200, text=lines, headers={"content-type": "text/event-stream"})


# ---------------------------------------------------------------------------
# _auth_headers
# ---------------------------------------------------------------------------


class TestAuthHeaders:
    def test_no_token_provider_returns_empty(self) -> None:
        c = AgentPodClient(
            base_url=BASE_URL,
            http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))),
        )
        assert c._auth_headers() == {}

    def test_provider_returning_none_returns_empty(self) -> None:
        c = _client(lambda r: httpx.Response(200, json=[]), token_provider=lambda: None)
        assert c._auth_headers() == {}

    def test_provider_returning_token_returns_bearer(self) -> None:
        c = _client(lambda r: httpx.Response(200, json=[]), token_provider=lambda: "my-token")
        assert c._auth_headers() == {"Authorization": "Bearer my-token"}


# ---------------------------------------------------------------------------
# list_agents
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_returns_list_of_strings(self, capsys) -> None:
        c = _client(lambda r: _json_response(["agent-a", "agent-b"]))
        result = c.list_agents()
        assert result == ["agent-a", "agent-b"]

    def test_non_list_response_raises(self, capsys) -> None:
        c = _client(lambda r: _json_response({"not": "a list"}))
        with pytest.raises(RuntimeError, match="JSON array of strings"):
            c.list_agents()

    def test_list_with_non_string_items_raises(self, capsys) -> None:
        c = _client(lambda r: _json_response([1, 2, 3]))
        with pytest.raises(RuntimeError, match="JSON array of strings"):
            c.list_agents()

    def test_http_error_propagates(self, capsys) -> None:
        c = _client(lambda r: httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            c.list_agents()

    def test_auth_header_forwarded(self, capsys) -> None:
        capture = _Capture(_json_response(["a"]))
        c = _client(capture, token_provider=lambda: "tok")
        c.list_agents()
        assert capture.last.headers["authorization"] == "Bearer tok"


# ---------------------------------------------------------------------------
# list_templates
# ---------------------------------------------------------------------------


class TestListTemplates:
    def test_returns_list(self) -> None:
        c = _client(lambda r: _json_response([{"template_agent_id": "t1"}]))
        result = c.list_templates()
        assert result[0]["template_agent_id"] == "t1"

    def test_non_list_response_raises(self) -> None:
        c = _client(lambda r: _json_response({"not": "a list"}))
        with pytest.raises(RuntimeError, match="JSON array"):
            c.list_templates()


# ---------------------------------------------------------------------------
# execute — payload construction and response validation
# ---------------------------------------------------------------------------


class TestExecute:
    def _capture_execute(
        self, **kwargs: Any
    ) -> tuple[dict[str, Any], _Capture]:
        capture = _Capture(_json_response({"output": "done"}))
        c = _client(capture)
        c.execute(
            agent_id="test.agent",
            message="hello",
            session_id="s1",
            user_id="u1",
            **kwargs,
        )
        return capture.last_json(), capture

    def test_minimal_payload(self) -> None:
        body, _ = self._capture_execute()
        assert body["agent_id"] == "test.agent"
        assert body["input"] == "hello"
        assert body["session_id"] == "s1"
        assert body["runtime_context"] == {"user_id": "u1"}
        assert "agent_instance_id" not in body
        assert "checkpoint_id" not in body
        assert "resume_payload" not in body
        assert "inline_tuning" not in body

    def test_team_id_included_when_provided(self) -> None:
        body, _ = self._capture_execute(team_id="team-a")
        assert body["runtime_context"]["team_id"] == "team-a"

    def test_team_id_omitted_when_none(self) -> None:
        body, _ = self._capture_execute(team_id=None)
        assert "team_id" not in body["runtime_context"]

    def test_optional_fields_included_when_provided(self) -> None:
        body, _ = self._capture_execute(
            agent_instance_id="inst-1",
            checkpoint_id="chk-1",
            resume_payload={"step": 2},
            inline_tuning={"prompts.system": "override"},
        )
        assert body["agent_instance_id"] == "inst-1"
        assert body["checkpoint_id"] == "chk-1"
        assert body["resume_payload"] == {"step": 2}
        assert body["inline_tuning"] == {"prompts.system": "override"}

    def test_non_dict_response_raises(self) -> None:
        c = _client(lambda r: _json_response(["not", "a", "dict"]))
        with pytest.raises(RuntimeError, match="JSON object"):
            c.execute(
                agent_id="a", message="m", session_id="s", user_id="u"
            )

    def test_http_error_propagates(self) -> None:
        c = _client(lambda r: httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            c.execute(agent_id="a", message="m", session_id="s", user_id="u")

    def test_url_targets_execute_endpoint(self) -> None:
        capture = _Capture(_json_response({"output": "ok"}))
        _client(capture).execute(
            agent_id="a", message="m", session_id="s", user_id="u"
        )
        assert str(capture.last.url).endswith("/agents/execute")


# ---------------------------------------------------------------------------
# evaluate — payload construction
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_minimal_payload(self) -> None:
        capture = _Capture(_json_response({"output": "eval result"}))
        c = _client(capture)
        result = c.evaluate(
            agent_id="eval.agent", message="q", session_id="s1", user_id="u1"
        )
        body = capture.last_json()
        assert body["agent_id"] == "eval.agent"
        assert body["input"] == "q"
        assert "resume_payload" not in body
        assert result["output"] == "eval result"

    def test_url_targets_evaluate_endpoint(self) -> None:
        capture = _Capture(_json_response({"output": "ok"}))
        _client(capture).evaluate(
            agent_id="a", message="m", session_id="s", user_id="u"
        )
        assert str(capture.last.url).endswith("/agents/evaluate")

    def test_team_id_included_when_provided(self) -> None:
        capture = _Capture(_json_response({"output": "ok"}))
        _client(capture).evaluate(
            agent_id="a", message="m", session_id="s", user_id="u", team_id="t1"
        )
        body = capture.last_json()
        assert body["runtime_context"]["team_id"] == "t1"

    def test_non_dict_response_raises(self) -> None:
        c = _client(lambda r: _json_response([]))
        with pytest.raises(RuntimeError, match="JSON object"):
            c.evaluate(agent_id="a", message="m", session_id="s", user_id="u")


# ---------------------------------------------------------------------------
# iter_stream_events / stream_events — SSE parsing
# ---------------------------------------------------------------------------


class TestIterStreamEvents:
    def _stream(self, *events: dict[str, Any]) -> list[dict[str, Any]]:
        c = _client(lambda r: _sse_response(*events))
        return c.stream_events(
            agent_id="a", message="m", session_id="s", user_id="u"
        )

    def test_single_event_parsed(self) -> None:
        result = self._stream({"kind": "final", "content": "hi"})
        assert result == [{"kind": "final", "content": "hi"}]

    def test_multiple_events_in_order(self) -> None:
        result = self._stream(
            {"kind": "tool_call"},
            {"kind": "tool_result"},
            {"kind": "final", "content": "done"},
        )
        assert [e["kind"] for e in result] == ["tool_call", "tool_result", "final"]

    def test_non_data_lines_skipped(self) -> None:
        body = "comment line\n\ndata: {\"kind\": \"final\"}\n\n: ping\n\n"
        c = _client(lambda r: httpx.Response(200, text=body))
        result = c.stream_events(
            agent_id="a", message="m", session_id="s", user_id="u"
        )
        assert result == [{"kind": "final"}]

    def test_empty_data_line_skipped(self) -> None:
        body = "data: \n\ndata: {\"kind\": \"final\"}\n\n"
        c = _client(lambda r: httpx.Response(200, text=body))
        result = c.stream_events(
            agent_id="a", message="m", session_id="s", user_id="u"
        )
        assert result == [{"kind": "final"}]

    def test_non_dict_sse_event_raises(self) -> None:
        body = 'data: ["not", "a", "dict"]\n\n'
        c = _client(lambda r: httpx.Response(200, text=body))
        with pytest.raises(RuntimeError, match="JSON object"):
            c.stream_events(
                agent_id="a", message="m", session_id="s", user_id="u"
            )

    def test_inline_tuning_forwarded(self) -> None:
        capture = _Capture(_sse_response({"kind": "final"}))
        c = _client(capture)
        c.stream_events(
            agent_id="a",
            message="m",
            session_id="s",
            user_id="u",
            inline_tuning={"settings.verbose": True},
        )
        body = capture.last_json()
        assert body["inline_tuning"] == {"settings.verbose": True}

    def test_http_error_propagates(self) -> None:
        c = _client(lambda r: httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            c.stream_events(
                agent_id="a", message="m", session_id="s", user_id="u"
            )


# ---------------------------------------------------------------------------
# Miscellaneous endpoints
# ---------------------------------------------------------------------------


class TestMiscEndpoints:
    def test_delete_session_messages_returns_count(self) -> None:
        c = _client(lambda r: _json_response({"deleted": 7}))
        assert c.delete_session_messages("sess-1") == 7

    def test_list_sessions_returns_string_list(self) -> None:
        c = _client(lambda r: _json_response(["sess-a", "sess-b"]))
        assert c.list_sessions("u1") == ["sess-a", "sess-b"]

    def test_get_metrics_text_raises_without_url(self) -> None:
        c = AgentPodClient(
            base_url=BASE_URL,
            http_client=httpx.Client(),
        )
        with pytest.raises(RuntimeError, match="Metrics URL"):
            c.get_metrics_text()
