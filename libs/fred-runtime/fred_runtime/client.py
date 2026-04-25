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
"""
Small interactive client for any Fred agent pod exposing the standard app API.

Why this module exists:
- developers need a fast way to exercise pod-hosted agents repeatedly without
  rewriting `curl` commands
- the same client should work for Sentinel today and for future ReAct, Deep,
  or Graph pods that expose the shared `/agents` and `/agents/execute/stream`
  contract

How to use it:
- run `fred-agent-chat` for an interactive REPL
- pass `--base-url` to target another running pod
- pass `--agent` and a message for one-shot usage

Example:
- `fred-agent-chat --agent sentinel.react.v2 "give me a health summary"`
"""

from __future__ import annotations

import argparse
import getpass
import glob as _glob
import json
import logging
import os
import re
import sys
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import yaml
from fred_core.cli.auth import (
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    build_cli_token_provider,
    default_configuration_file,
    default_keycloak_token_file,
    default_pkce_callback_host,
    default_pkce_callback_port,
    load_cli_environment,
    load_configuration_yaml,
    resolve_keycloak_login_config,
)
from fred_core.cli.ui import (
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_WHITE,
    ANSI_YELLOW,
    colorize,
    colors_enabled,
    complete_slash_commands,
    install_readline_completion,
)

logger = logging.getLogger(__name__)

DEFAULT_AGENT_POD_BASE_URL = "http://127.0.0.1:8000/api/v1"
_COMMANDS: tuple[str, ...] = (
    "/help",
    "/agents",
    "/agent",
    "/checkpoints",
    "/checkpoint",
    "/context",
    "/execution-context",
    "/history",
    "/kpi",
    "/login",
    "/login-password",
    "/mode",
    "/scenario",
    "/session",
    "/sessions",
    "/stats",
    "/team",
    "/logout",
    "/quit",
    "/whoami",
)
_ANSI_BOLD = ANSI_BOLD
_ANSI_CYAN = ANSI_CYAN
_ANSI_GREEN = ANSI_GREEN
_ANSI_RED = ANSI_RED
_ANSI_YELLOW = ANSI_YELLOW
_ANSI_DIM = ANSI_DIM
_ANSI_WHITE = ANSI_WHITE
_PROM_SAMPLE_RE = re.compile(
    r"^(?P<name>[^{\s]+)(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?:\s+\d+)?$"
)


@dataclass(slots=True)
class AgentPodClient:
    """
    Minimal synchronous client for the shared Fred pod HTTP contract.

    Why this class exists:
    - chat and smoke workflows only need two operations: list agents and stream
      one execution
    - keeping those calls here makes the CLI reusable for any compatible pod

    How to use it:
    - instantiate with the pod base URL
    - call `list_agents()` to discover agent ids
    - call `execute(...)` for terminal JSON execution
    - call `stream_events(...)` to collect streamed runtime events

    Example:
    - `client = AgentPodClient(base_url="http://127.0.0.1:8010/fred/agents/v2", http_client=httpx.Client())`
    """

    base_url: str
    http_client: httpx.Client
    token_provider: Callable[[], str | None] | None = None
    metrics_url: str | None = None

    def _auth_headers(self) -> dict[str, str]:
        """
        Build the Authorization header set for one pod request.

        Why this exists:
        - the client should inject a fresh bearer token on every request when a
          login session or explicit token provider is configured

        How to use it:
        - called internally before each HTTP request

        Example:
        - `headers = client._auth_headers()`
        """

        if self.token_provider is None:
            return {}
        token = self.token_provider()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def list_agents(self) -> list[str]:
        """
        Fetch the registered agent ids from one running pod.

        Why this function exists:
        - the developer client should discover what a pod currently exposes
        - the `/agents` endpoint is the shared contract surface provided by
          `create_agent_app(...)`

        How to use it:
        - call before selecting an agent interactively
        - call again after changing pod code if you want a fresh list

        Example:
        - `agents = client.list_agents()`
        """

        url = f"{self.base_url}/agents"
        print(f"[chat] connecting to pod: GET {url}")
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not all(
            isinstance(agent_id, str) for agent_id in payload
        ):
            raise RuntimeError("Agent list response must be a JSON array of strings.")
        return payload

    def execute(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        resume_payload: Any = None,
    ) -> dict[str, Any]:
        """
        Execute one agent turn through the non-streaming JSON endpoint.

        Why this function exists:
        - many developer flows only need the terminal payload, not the full SSE
          stream
        - sends a RuntimeExecuteRequest (Phase 1 contract)

        How to use it:
        - pass the target agent id and user message
        - inspect the returned JSON payload for `kind="final"` or `error`
        - pass `resume_payload` to resume a graph agent paused at a HITL gate

        Example:
        - `payload = client.execute(agent_id="sentinel.react.v2", message="hello", session_id="demo", user_id="alice", team_id="fredlab")`
        """
        runtime_context: dict[str, Any] = {"user_id": user_id}
        if team_id:
            runtime_context["team_id"] = team_id
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "input": message,
            "session_id": session_id,
            "runtime_context": runtime_context,
        }
        if resume_payload is not None:
            payload["resume_payload"] = resume_payload
        response = self.http_client.post(
            f"{self.base_url}/agents/execute",
            json=payload,
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("Execute response must be a JSON object.")
        return result

    def stream_events(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        resume_payload: Any = None,
    ) -> list[dict[str, Any]]:
        """
        Execute one agent turn and collect the streamed SSE payloads.

        Why this function exists:
        - the pod streams runtime events over SSE rather than returning one JSON
          document
        - the developer client wants a simple Python list of parsed events

        How to use it:
        - pass the target agent id and user message
        - inspect the returned events for `final` content or runtime errors

        Example:
        - `events = client.stream_events(agent_id="sentinel.react.v2", message="hello", session_id="demo", user_id="alice", team_id="fredlab")`
        """

        events: list[dict[str, Any]] = []
        for event in self.iter_stream_events(
            agent_id=agent_id,
            message=message,
            session_id=session_id,
            user_id=user_id,
            team_id=team_id,
            resume_payload=resume_payload,
        ):
            events.append(event)
        return events

    def iter_stream_events(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        resume_payload: Any = None,
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate streamed runtime events from the SSE endpoint.

        Why this function exists:
        - some callers want to render events live instead of waiting for the
          whole stream to finish
        - `stream_events(...)` can stay as a thin collector over this iterator

        How to use it:
        - iterate over the returned generator and handle each event as it arrives
        - pass `resume_payload` to resume a graph agent paused at a HITL gate

        Example:
        - `for event in client.iter_stream_events(..., team_id="fredlab"): ...`
        """

        runtime_context: dict[str, Any] = {"user_id": user_id}
        if team_id:
            runtime_context["team_id"] = team_id
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "input": message,
            "session_id": session_id,
            "runtime_context": runtime_context,
        }
        if resume_payload is not None:
            payload["resume_payload"] = resume_payload
        with self.http_client.stream(
            "POST",
            f"{self.base_url}/agents/execute/stream",
            json=payload,
            headers=self._auth_headers(),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = (
                    raw_line.decode("utf-8")
                    if isinstance(raw_line, bytes)
                    else raw_line
                )
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ").strip()
                if not data:
                    continue
                event = json.loads(data)
                if not isinstance(event, dict):
                    raise RuntimeError("SSE event payload must be a JSON object.")
                yield event

    def list_sessions(self, user_id: str) -> list[str]:
        """
        Return the session IDs for a user, most recent first.

        Why this function exists:
        - the developer client should be able to list past conversations so the
          user can navigate to an earlier session and inspect or continue it
        - the pod exposes this as ``GET /agents/sessions?user_id=<id>``

        How to use it:
        - call with the current user_id to get a list of session ids
        - the list is ordered most recent first (by last message timestamp)

        Example:
        - `sessions = client.list_sessions(user_id="alice")`
        """

        url = f"{self.base_url}/agents/sessions"
        response = self.http_client.get(
            url, params={"user_id": user_id}, headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Sessions response must be a JSON array.")
        return [str(s) for s in payload]

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """
        Fetch the full conversation history for one session.

        Why this function exists:
        - the developer client should be able to replay or inspect a previous
          conversation without re-running the agent
        - the pod exposes this as ``GET /agents/sessions/{session_id}/messages``

        How to use it:
        - pass a session_id (e.g. from ``list_sessions``)
        - returns a list of ChatMessage dicts ordered by rank ascending

        Example:
        - `messages = client.get_session_messages("session-abc")`
        """

        url = f"{self.base_url}/agents/sessions/{session_id}/messages"
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Messages response must be a JSON array.")
        return payload

    def get_checkpoint_stats(self) -> dict[str, Any]:
        """
        Fetch aggregate checkpoint storage statistics from the pod.

        Why this function exists:
        - developers need a quick storage health check without counting rows
          manually or connecting to the database
        - the pod exposes this as ``GET /agents/checkpoints/_stats``

        How to use it:
        - call from the ``/stats`` REPL command
        - interpret blob_bytes_approx as the dominant storage cost

        Example:
        - `stats = client.get_checkpoint_stats()`
        """
        url = f"{self.base_url}/agents/checkpoints/_stats"
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def list_checkpoint_threads(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """
        List checkpoint threads stored in the pod, newest first.

        Why this function exists:
        - developers need to inspect which sessions have live checkpoint state
          without using the frontend
        - the pod exposes this as ``GET /agents/checkpoints?limit=<n>``

        How to use it:
        - call from the ``/checkpoints`` REPL command
        - each entry has session_id, checkpoint_count, latest_created_at

        Example:
        - `threads = client.list_checkpoint_threads(limit=10)`
        """
        url = f"{self.base_url}/agents/checkpoints"
        response = self.http_client.get(
            url, params={"limit": limit}, headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Checkpoint threads response must be a JSON array.")
        return payload

    def get_checkpoint_thread(self, session_id: str) -> dict[str, Any]:
        """
        Fetch all checkpoints for one session, newest first.

        Why this function exists:
        - developers need a terminal way to inspect checkpoint state for a
          specific session without using the frontend
        - the pod exposes this as ``GET /agents/checkpoints/{session_id}``

        How to use it:
        - pass the session_id (the public-facing conversation identity)
        - returns a dict with session_id and a checkpoints list

        Example:
        - `detail = client.get_checkpoint_thread("session-abc")`
        """
        url = f"{self.base_url}/agents/checkpoints/{session_id}"
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def get_metrics_text(self) -> str:
        """
        Fetch the pod Prometheus exposition text from the configured metrics URL.

        Why this function exists:
        - the CLI `/kpi` command should inspect runtime metrics without asking
          developers to handcraft curl commands repeatedly
        - keeping the HTTP fetch here makes metrics inspection reuse the same
          client lifecycle as the rest of the CLI

        How to use it:
        - configure `metrics_url` when constructing the client
        - call from `/kpi` and then parse the returned exposition text

        Example:
        - `text = client.get_metrics_text()`
        """

        if not self.metrics_url:
            raise RuntimeError(
                "Metrics URL is not configured. Pass `--metrics-url`, export "
                "`FRED_AGENT_METRICS_URL`, or run from a pod project with "
                "configuration.yaml exposing app.metrics_port."
            )
        print(f"[chat] connecting to metrics: GET {self.metrics_url}")
        response = self.http_client.get(
            self.metrics_url,
            headers={"Accept": "text/plain; version=0.0.4"},
        )
        response.raise_for_status()
        return response.text


def default_agent_pod_base_url() -> str:
    """
    Resolve the default pod base URL for the chat client.

    Resolution order:
    1. `FRED_AGENT_POD_URL` environment variable (explicit override).
    2. `app.port` and `app.base_url` from the pod's `configuration.yaml`
       (same file discovered via `CONFIG_FILE` env var or the default path).
    3. Built-in fallback: `http://127.0.0.1:8000/api/v1`.

    Why this function exists:
    - the pod already declares its port and base_url in configuration.yaml;
      duplicating those values in an env var is error-prone
    - reading them here keeps the chat client in sync with the pod config
      automatically

    Example:
    - `base_url = default_agent_pod_base_url()`
    """

    explicit = os.getenv("FRED_AGENT_POD_URL")
    if explicit:
        return normalize_base_url(explicit)

    payload = load_configuration_yaml(default_configuration_file())
    if isinstance(payload, dict):
        app_section = payload.get("app")
        if isinstance(app_section, dict):
            port = app_section.get("port", 8000)
            base = str(app_section.get("base_url", "/api/v1")).rstrip("/")
            return normalize_base_url(f"http://127.0.0.1:{port}{base}")

    return normalize_base_url(DEFAULT_AGENT_POD_BASE_URL)


def default_agent_metrics_url(*, base_url: str | None = None) -> str | None:
    """
    Resolve the default Prometheus metrics URL for the target pod.

    Resolution order:
    1. `FRED_AGENT_METRICS_URL` environment variable (explicit override).
    2. `app.metrics_port` and optional `app.metrics_address` from
       `configuration.yaml`.
    3. `None` when no metrics configuration is available.

    Why this function exists:
    - `/kpi` should discover the pod metrics endpoint from the same config the
      runtime uses, instead of hardcoding another host/port convention
    - wildcard bind addresses like `0.0.0.0` are not directly curlable, so the
      helper rewrites them to the host part of the active pod base URL

    How to use it:
    - call at CLI startup or when building an `AgentPodClient`

    Example:
    - `metrics_url = default_agent_metrics_url(base_url="http://127.0.0.1:8000/pod/v1")`
    """

    explicit = os.getenv("FRED_AGENT_METRICS_URL")
    if explicit:
        return explicit.rstrip("/")

    payload = load_configuration_yaml(default_configuration_file())
    if not isinstance(payload, dict):
        return None
    app_section = payload.get("app")
    if not isinstance(app_section, dict):
        return None

    metrics_port = app_section.get("metrics_port")
    if metrics_port in (None, ""):
        return None

    try:
        port = int(metrics_port)
    except (TypeError, ValueError):
        return None

    parsed_base = urlparse(base_url or default_agent_pod_base_url())
    fallback_host = parsed_base.hostname or "127.0.0.1"
    scheme = parsed_base.scheme or "http"
    raw_host = (
        str(app_section.get("metrics_address", fallback_host)).strip() or fallback_host
    )
    host = fallback_host if raw_host in {"0.0.0.0", "::", "[::]"} else raw_host  # nosec B104 - rewrite wildcard bind address to the active target host for local scraping
    return urlunparse((scheme, f"{host}:{port}", "/metrics", "", "", ""))


def normalize_base_url(base_url: str) -> str:
    """
    Normalize one pod base URL for consistent request construction.

    Why this function exists:
    - manual input often includes a trailing slash
    - the client should build endpoint paths without accidental double slashes

    How to use it:
    - pass any non-empty pod base URL before storing it in the client

    Example:
    - `normalize_base_url("http://localhost:8010/fred/agents/v2/")`
    """

    cleaned = base_url.strip()
    if not cleaned:
        raise ValueError("base_url cannot be empty.")
    return cleaned.rstrip("/")


def completion_candidates(
    line_buffer: str,
    *,
    agent_ids: Sequence[str],
) -> list[str]:
    """
    Return tab-completion candidates for one chat prompt line.

    Why this function exists:
    - developers switch agents frequently while testing pods
    - a pure helper keeps completion logic testable without interactive TTY code

    How to use it:
    - pass the current input line and the latest known agent ids
    - use the returned strings inside a readline completer

    Example:
    - `completion_candidates("/agent sent", agent_ids=["sentinel.react.v2"])`
    """

    stripped = line_buffer.lstrip()
    if stripped.startswith("/agent "):
        prefix = stripped.removeprefix("/agent ").strip()
        return [agent_id for agent_id in agent_ids if agent_id.startswith(prefix)]
    if stripped.startswith("/mode "):
        prefix = stripped.removeprefix("/mode ").strip()
        return [mode for mode in ("final", "stream") if mode.startswith(prefix)]
    if stripped.startswith("/scenario "):
        partial = stripped.removeprefix("/scenario ").strip()
        return _complete_scenario_path(partial)
    if stripped.startswith("/"):
        return complete_slash_commands(stripped, commands=_COMMANDS)
    return []


def _complete_scenario_path(partial: str) -> list[str]:
    """
    Return YAML file paths that complete the partial path typed after /scenario.

    Why this function exists:
    - scenario files live in a subdirectory, not the cwd root
    - two levels of glob depth covers the typical tests/scenarios/ layout
      without listing the entire filesystem

    How it works:
    - readline's delimiter is space so the whole path is one completion word;
      returning the completed path replaces the partial path correctly
    - level 0: <partial>*.yaml              (exact prefix at current dir)
    - level 1: <partial>*/*.yaml            (one directory deeper)
    - level 1b: only added when partial is empty or ends with /,
                so typing "tests/s" only expands at the current level

    Example:
    - `_complete_scenario_path("")`             → ["tests/scenarios/sentinel_checkpointing.yaml", ...]
    - `_complete_scenario_path("tests/scen")`  → ["tests/scenarios/sentinel_checkpointing.yaml", ...]
    - `_complete_scenario_path("tests/scenarios/sentinel_s")` → ["tests/scenarios/sentinel_smoke.yaml"]
    """
    expanded = os.path.expanduser(partial)

    candidates: list[str] = sorted(_glob.glob(expanded + "*.yaml"))

    # Descend up to two levels when the user has not started narrowing yet.
    # This covers the typical tests/scenarios/ layout without recursing the
    # whole project tree.
    if not partial or partial.endswith("/"):
        candidates += sorted(_glob.glob(expanded + "*/*.yaml"))
        candidates += sorted(_glob.glob(expanded + "*/*/*.yaml"))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def print_help() -> None:
    """
    Print the supported interactive chat commands.

    Why this function exists:
    - the chat loop intentionally stays tiny, so discoverability should be in
      one short built-in help block

    How to use it:
    - call from the REPL when the user types `/help`

    Example:
    - `print_help()`
    """

    print("Commands:")
    print(
        "  /help [question]         Show this help, or ask a question in natural language"
    )
    print("  /agents                  Refresh and list available agent ids")
    print("  /agent <agent_id>        Switch the active agent")
    print(
        "  /login                   Log in through browser PKCE and cache the user session"
    )
    print(
        "  /login-password [user]   Use direct username/password login as a local fallback"
    )
    print("  /whoami                  Show the current login state")
    print("  /logout                  Clear the cached login session")
    print("  /mode [final|stream]     Show or change the execution mode")
    print("  /scenario <file>         Run a YAML scenario file against the pod")
    print("  /session <id>            Change the current session id")
    print("  /team [team_id|clear]    Show, set, or clear the current team scope")
    print(
        "  /sessions                List all sessions for the current user (most recent first)"
    )
    print("  /history [session_id]    Show the conversation history for a session")
    print("  /kpi [pattern]           Show a KPI/Prometheus snapshot from the pod")
    print(
        "  /checkpoints [limit]     List checkpoint threads with sizes (default limit=20)"
    )
    print("  /checkpoint <session_id> Inspect all checkpoints for one session")
    print("  /stats                   Show aggregate checkpoint storage statistics")
    print("  /context                 Show current execution context summary")
    print("  /quit                    Exit the chat client")


_CLI_HELP_CONTEXT = (
    "You are an interactive help assistant embedded in the Fred CLI chat tool "
    "(fred-agent-chat). Answer the user's question about how to use the CLI. "
    "Respond in the same language as the user's question. Be concise and practical.\n\n"
    "Available commands:\n"
    "  /help [question]         Show command reference or ask a question in natural language\n"
    "  /agents                  Refresh and list available agent ids\n"
    "  /agent <agent_id>        Switch the active agent\n"
    "  /login                   Log in through browser PKCE and cache the user session\n"
    "  /login-password [user]   Use direct username/password login as a local fallback\n"
    "  /whoami                  Show the current login state\n"
    "  /logout                  Clear the cached login session\n"
    "  /mode [final|stream]     Show or change the execution mode (default: stream)\n"
    "  /scenario <file>         Run a YAML scenario file against the pod\n"
    "  /session <id>            Change the current session id\n"
    "  /team [team_id|clear]    Show, set, or clear the current team scope\n"
    "  /sessions                List all sessions for the current user (most recent first)\n"
    "  /history [session_id]    Show the conversation history for a session\n"
    "  /kpi [pattern]           Show a KPI/Prometheus snapshot from the pod\n"
    "  /checkpoints [limit]     List checkpoint threads with sizes (default limit=20)\n"
    "  /checkpoint <session_id> Inspect all checkpoints for one session\n"
    "  /stats                   Show aggregate checkpoint storage statistics\n"
    "  /context                 Show current execution context summary\n"
    "  /quit                    Exit the chat client\n\n"
    "Any text that does not start with / is sent as a message to the current agent.\n\n"
    "User question: "
)


def _ask_cli_help(
    *,
    question: str,
    client: "AgentPodClient",
    agent_id: str,
    user_id: str,
    team_id: str | None,
    color_enabled: bool,
) -> None:
    compound = _CLI_HELP_CONTEXT + question
    ephemeral_session = f"__help__{uuid.uuid4().hex}"
    try:
        payload = client.execute(
            agent_id=agent_id,
            message=compound,
            session_id=ephemeral_session,
            user_id=user_id,
            team_id=team_id,
        )
    except Exception as exc:
        print(
            colorize(
                f"[help] Pod unavailable ({exc}). Showing command reference instead.",
                color=_ANSI_DIM,
                enabled=color_enabled,
            )
        )
        print_help()
        return
    if "error" in payload:
        print(
            colorize(
                f"[help] Agent error: {payload['error']}. Showing command reference.",
                color=_ANSI_DIM,
                enabled=color_enabled,
            )
        )
        print_help()
        return
    content = payload.get("content")
    if not isinstance(content, str):
        print_help()
        return
    print(content)


def fmt_bytes(n: int) -> str:
    """
    Human-readable byte size with one decimal place.

    Why this exists:
    - checkpoint and blob sizes are displayed in multiple places in the CLI;
      a shared formatter keeps the output consistent

    How to use it:
    - pass any integer byte count; returns e.g. "1.4 KB", "892.7 KB", "2.1 MB"

    Example:
    - `fmt_bytes(1432)` → "1.4 KB"
    """
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def execution_mode_label(*, stream: bool) -> str:
    """
    Return the human-readable label for the current execution mode.

    Why this function exists:
    - the chat client shows and switches between two transport modes repeatedly
    - a small helper keeps that wording consistent across headers and commands

    How to use it:
    - pass the current stream boolean from CLI or interactive state

    Example:
    - `label = execution_mode_label(stream=True)`
    """

    return "stream" if stream else "final"


def parse_mode_command(message: str) -> bool | None:
    """
    Parse one `/mode ...` command into the requested execution mode.

    Why this function exists:
    - interactive command handling should stay easy to test without relying on
      the full REPL loop

    How to use it:
    - pass the raw user input starting with `/mode`
    - returns `True` for stream mode, `False` for final mode, or `None` when
      the command only asks to display the current mode

    Example:
    - `mode = parse_mode_command("/mode stream")`
    """

    command = message.strip()
    if command == "/mode":
        return None
    requested_mode = command.removeprefix("/mode").strip().lower()
    if requested_mode == "stream":
        return True
    if requested_mode == "final":
        return False
    raise ValueError("Unknown mode. Use `/mode`, `/mode final`, or `/mode stream`.")


@dataclass(frozen=True, slots=True)
class PrometheusSample:
    """
    One parsed Prometheus exposition sample line.

    Why this exists:
    - `/kpi` should work from plain text exposition without depending on a full
      Prometheus client/parser stack inside the CLI
    - a small typed record keeps parsing and rendering logic testable offline

    How to use it:
    - build via `parse_prometheus_text_exposition(...)`
    - inspect `name`, `labels`, and `value` when rendering summaries

    Example:
    - `sample = PrometheusSample(name="process_cpu_percent", labels={}, value=12.5)`
    """

    name: str
    labels: dict[str, str]
    value: float


@dataclass(frozen=True, slots=True)
class HistogramSeriesSummary:
    """
    One summarized Prometheus histogram series.

    Why this exists:
    - KPI timers are exposed as Prometheus histograms, but developers usually
      want quick `count/sum/avg` summaries in the CLI instead of raw buckets

    How to use it:
    - build via `summarize_prometheus_histograms(...)`
    - render in `/kpi` output or tests

    Example:
    - `summary = HistogramSeriesSummary(name="agent_tool_latency_ms", labels={"tool_name": "search"}, count=4, sum_value=120.0)`
    """

    name: str
    labels: dict[str, str]
    count: float
    sum_value: float

    @property
    def avg_value(self) -> float:
        """
        Return the average observed value for this histogram series.

        Why this exists:
        - the CLI needs one simple derived latency number without repeating the
          `sum / count` guard everywhere

        How to use it:
        - call after parsing histogram `_sum` and `_count` samples

        Example:
        - `avg = summary.avg_value`
        """

        if self.count <= 0:
            return 0.0
        return self.sum_value / self.count


def parse_prometheus_text_exposition(text: str) -> list[PrometheusSample]:
    """
    Parse Prometheus exposition text into typed sample rows.

    Why this exists:
    - `/kpi` scrapes the plain-text `/metrics` endpoint directly
    - the CLI only needs sample values and labels, not the full Prometheus
      metadata model

    How to use it:
    - pass the raw body returned by `client.get_metrics_text()`
    - ignore comments and malformed lines automatically

    Example:
    - `samples = parse_prometheus_text_exposition(text)`
    """

    samples: list[PrometheusSample] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _PROM_SAMPLE_RE.match(line)
        if match is None:
            continue
        labels = _parse_prometheus_labels(match.group("labels") or "")
        samples.append(
            PrometheusSample(
                name=match.group("name"),
                labels=labels,
                value=float(match.group("value")),
            )
        )
    return samples


def _parse_prometheus_labels(label_block: str) -> dict[str, str]:
    """
    Parse one Prometheus label block into a plain dict.

    Why this exists:
    - exposition lines encode labels inline, and `/kpi` needs them for team,
      session, tool, and phase filtering

    How to use it:
    - pass the inside of `{...}` from one exposition sample

    Example:
    - `_parse_prometheus_labels('phase="tool",team_id="fredlab"')`
    """

    labels: dict[str, str] = {}
    if not label_block:
        return labels
    for part in label_block.split(","):
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = bytes(value[1:-1], "utf-8").decode("unicode_escape")
        labels[key.strip()] = value
    return labels


def summarize_prometheus_histograms(
    samples: Sequence[PrometheusSample],
) -> list[HistogramSeriesSummary]:
    """
    Summarize Prometheus histogram families into `count/sum/avg` rows.

    Why this exists:
    - Prometheus emits histogram buckets as many lines, but developers usually
      need a compact per-series summary when validating runtime KPIs

    How to use it:
    - pass the parsed samples from one `/metrics` scrape
    - render the returned summaries directly in the CLI

    Example:
    - `histograms = summarize_prometheus_histograms(samples)`
    """

    grouped: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, float]] = {}
    label_maps: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, str]] = {}
    for sample in samples:
        suffix = None
        for candidate in ("_count", "_sum"):
            if sample.name.endswith(candidate):
                suffix = candidate
                break
        if suffix is None:
            continue
        base_name = sample.name.removesuffix(suffix)
        filtered_labels = {k: v for k, v in sample.labels.items() if k != "le"}
        key = (base_name, tuple(sorted(filtered_labels.items())))
        grouped.setdefault(key, {})[suffix] = sample.value
        label_maps[key] = filtered_labels

    summaries: list[HistogramSeriesSummary] = []
    for key, values in grouped.items():
        name, _ = key
        if "_count" not in values and "_sum" not in values:
            continue
        summaries.append(
            HistogramSeriesSummary(
                name=name,
                labels=label_maps[key],
                count=values.get("_count", 0.0),
                sum_value=values.get("_sum", 0.0),
            )
        )
    return sorted(
        summaries,
        key=lambda item: (-item.count, item.name, sorted(item.labels.items())),
    )


def filter_prometheus_samples(
    samples: Sequence[PrometheusSample],
    *,
    pattern: str | None = None,
) -> list[PrometheusSample]:
    """
    Filter Prometheus samples by a free-text pattern over names and labels.

    Why this exists:
    - `/kpi` should let developers narrow down metrics without learning PromQL
    - a substring match is enough for laptop debugging and local benchmarks

    How to use it:
    - pass a pattern like `tool`, `session-123`, or `fredlab`
    - leave it empty to keep all samples

    Example:
    - `filtered = filter_prometheus_samples(samples, pattern="team_id=fredlab")`
    """

    if not pattern:
        return list(samples)
    needle = pattern.lower()
    kept: list[PrometheusSample] = []
    for sample in samples:
        haystacks = [sample.name]
        haystacks.extend(f"{key}={value}" for key, value in sample.labels.items())
        if any(needle in haystack.lower() for haystack in haystacks):
            kept.append(sample)
    return kept


def format_metric_value(value: float) -> str:
    """
    Format one Prometheus sample value for compact terminal display.

    Why this exists:
    - `/kpi` mixes counters, gauges, and histogram aggregates and should render
      readable numbers without noisy floating-point tails

    How to use it:
    - pass the numeric sample value to print

    Example:
    - `text = format_metric_value(12.34567)`
    """

    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"


def format_prometheus_labels(
    labels: dict[str, str], *, keys: Sequence[str] | None = None
) -> str:
    """
    Render a compact label string for CLI KPI output.

    Why this exists:
    - Prometheus label sets can be wide, but `/kpi` should foreground the
      execution labels that matter for Fred debugging

    How to use it:
    - pass the label dict from one sample or histogram summary
    - optionally restrict the output order to the most useful keys first

    Example:
    - `text = format_prometheus_labels({"phase": "tool", "team_id": "fredlab"})`
    """

    if not labels:
        return "-"
    ordered_keys = list(keys or ())
    ordered_keys.extend(key for key in labels if key not in ordered_keys)
    parts = [f"{key}={labels[key]}" for key in ordered_keys if key in labels]
    return ", ".join(parts)


def render_kpi_report(
    samples: Sequence[PrometheusSample],
    *,
    color_enabled: bool,
    pattern: str | None = None,
) -> list[str]:
    """
    Render a compact human-readable KPI report from Prometheus samples.

    Why this exists:
    - developers want a terminal-first KPI view without deploying Grafana just
      to validate one pod or laptop benchmark run
    - this function keeps `/kpi` output deterministic and unit-testable

    How to use it:
    - parse the `/metrics` text first, then pass the samples here
    - optionally provide a free-text filter pattern

    Example:
    - `lines = render_kpi_report(samples, color_enabled=True, pattern="tool")`
    """

    filtered = filter_prometheus_samples(samples, pattern=pattern)
    if not filtered:
        return [
            colorize(
                "  No KPI metrics matched the requested filter.",
                color=_ANSI_DIM,
                enabled=color_enabled,
            )
        ]

    histograms = summarize_prometheus_histograms(filtered)
    histogram_bases = {summary.name for summary in histograms}
    value_samples = [
        sample
        for sample in filtered
        if not any(
            sample.name == f"{base}{suffix}"
            for base in histogram_bases
            for suffix in ("_bucket", "_sum", "_count")
        )
    ]

    process_samples = [
        sample for sample in value_samples if sample.name.startswith("process_")
    ]
    counter_samples = [
        sample
        for sample in value_samples
        if sample.name.endswith("_total")
        and not sample.name.startswith("process_")
        and sample.value > 0
    ]
    other_samples = [
        sample
        for sample in value_samples
        if sample not in process_samples
        and sample not in counter_samples
        and not sample.name.endswith("_created")  # epoch-timestamp noise — skip
    ]

    lines: list[str] = []
    title = "  KPI snapshot"
    if pattern:
        title += f" — filter={pattern}"
    lines.append(colorize(title, color=_ANSI_DIM, enabled=color_enabled, bold=True))
    lines.append(colorize("  " + "─" * 72, color=_ANSI_DIM, enabled=color_enabled))

    if histograms:
        # Labels that are always the same across every histogram series → show
        # once as an execution-context block, not repeated on every row.
        # Labels that are obviously implicit (actor_type=system, status=ok) are
        # suppressed entirely; they add no debugging value.
        _SUPPRESS_ALWAYS = {"actor_type", "status"}
        _CONTEXT_KEYS = (
            "session_id",
            "template_agent_id",
            "agent_instance_id",
            "team_id",
            "service",
            "agent_id",
        )
        # Intersection: keep only keys whose value is identical in every series
        if len(histograms) == 1:
            shared_labels = {
                k: v
                for k, v in histograms[0].labels.items()
                if k not in _SUPPRESS_ALWAYS
            }
        else:
            shared_labels = {}
            for key in histograms[0].labels:
                if key in _SUPPRESS_ALWAYS:
                    continue
                val = histograms[0].labels[key]
                if all(s.labels.get(key) == val for s in histograms[1:]):
                    shared_labels[key] = val

        lines.append(
            colorize(
                "  Phase / latency breakdown:",
                color=_ANSI_WHITE,
                enabled=color_enabled,
                bold=True,
            )
        )
        if shared_labels:
            ctx_parts = [
                colorize(k + "=", color=_ANSI_DIM, enabled=color_enabled)
                + colorize(shared_labels[k], color=_ANSI_GREEN, enabled=color_enabled)
                for k in _CONTEXT_KEYS
                if k in shared_labels
            ]
            # also append any shared keys not in _CONTEXT_KEYS (in dim)
            extra_ctx = [
                colorize(f"{k}={v}", color=_ANSI_DIM, enabled=color_enabled)
                for k, v in shared_labels.items()
                if k not in _CONTEXT_KEYS
            ]
            ctx_line = (
                "  "
                + colorize(
                    "context  ", color=_ANSI_DIM, enabled=color_enabled, bold=True
                )
                + "  ".join(ctx_parts + extra_ctx)
            )
            lines.append(ctx_line)

        for summary in histograms[:10]:
            phase = summary.labels.get("phase", "")
            tool = summary.labels.get("tool_name", "")
            phase_label = phase or tool or summary.name
            # Per-row: only labels that differ across series and are not suppressed
            row_labels = {
                k: v
                for k, v in summary.labels.items()
                if k not in _SUPPRESS_ALWAYS
                and k not in shared_labels
                and k not in ("phase", "tool_name")  # already in the phase_label
            }
            row_label_str = format_prometheus_labels(
                row_labels,
                keys=("agent_step", "agent_instance_id", "team_id"),
            )
            lines.append(
                "  "
                + colorize(
                    f"[{phase_label}]",
                    color=_ANSI_CYAN,
                    enabled=color_enabled,
                    bold=True,
                )
                + "  "
                + colorize(
                    f"avg={format_metric_value(summary.avg_value):>7} ms",
                    color=_ANSI_YELLOW,
                    enabled=color_enabled,
                    bold=True,
                )
                + colorize(
                    f"  n={format_metric_value(summary.count):>4}"
                    f"  total={format_metric_value(summary.sum_value):>8} ms",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
                + (
                    colorize(
                        f"  ({row_label_str})", color=_ANSI_DIM, enabled=color_enabled
                    )
                    if row_label_str != "-"
                    else ""
                )
            )

    if process_samples:
        lines.append("")
        lines.append(
            colorize(
                "  Process gauges:", color=_ANSI_DIM, enabled=color_enabled, bold=True
            )
        )
        for sample in sorted(process_samples, key=lambda item: item.name):
            lines.append(
                "  "
                + colorize(
                    sample.name, color=_ANSI_GREEN, enabled=color_enabled, bold=True
                )
                + colorize(
                    f"  value={format_metric_value(sample.value):>8}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  [{format_prometheus_labels(sample.labels, keys=('pool',))}]",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )

    if counter_samples:
        lines.append("")
        lines.append(
            colorize("  Counters:", color=_ANSI_DIM, enabled=color_enabled, bold=True)
        )
        for sample in sorted(
            counter_samples, key=lambda item: (-item.value, item.name)
        )[:10]:
            counter_color = (
                _ANSI_RED
                if any(word in sample.name for word in ("failed", "error"))
                else _ANSI_YELLOW
            )
            lines.append(
                "  "
                + colorize(
                    sample.name, color=counter_color, enabled=color_enabled, bold=True
                )
                + colorize(
                    f"  total={format_metric_value(sample.value):>8}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  [{format_prometheus_labels(sample.labels, keys=('tool_name', 'agent_instance_id', 'team_id', 'session_id', 'error_code'))}]",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )

    if other_samples and not pattern:
        lines.append("")
        lines.append(
            colorize(
                "  Other samples:", color=_ANSI_DIM, enabled=color_enabled, bold=True
            )
        )
        for sample in sorted(other_samples, key=lambda item: item.name)[:5]:
            lines.append(
                "  "
                + colorize(sample.name, color=_ANSI_DIM, enabled=color_enabled)
                + colorize(
                    f"  value={format_metric_value(sample.value):>8}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )

    return lines


# Role → (display label, ANSI color)
_HISTORY_ROLE_STYLE: dict[str, tuple[str, str]] = {
    "user": ("You", _ANSI_GREEN),
    "assistant": ("Assistant", _ANSI_CYAN),
    "tool": ("Tool", _ANSI_YELLOW),
    "system": ("System", _ANSI_DIM),
}

# Channel labels shown in brackets when not "final"
_HISTORY_CHANNEL_LABELS: dict[str, str] = {
    "tool_call": "tool call",
    "tool_result": "tool result",
    "plan": "plan",
    "thought": "thought",
    "observation": "observation",
    "error": "error",
    "system_note": "note",
}


def print_history(
    messages: list[dict[str, Any]],
    *,
    session_id: str,
    color_enabled: bool,
) -> None:
    """
    Render a conversation history to the terminal in a readable form.

    Why this function exists:
    - the raw ChatMessage JSON is too noisy for interactive inspection;
      this function distils it into the essential role/content view that a
      developer or reviewer would want to scan quickly

    How to use it:
    - pass the list returned by ``AgentPodClient.get_session_messages``
    - call from the ``/history`` REPL command

    Example:
    - ``print_history(messages, session_id="abc", color_enabled=True)``

    Output format per message:
    - ``[rank]  Role [channel]  content…``
    - Tool-call messages show the function name and first 80 chars of args
    - Metadata (model, token_usage) appended in dim style when present
    """

    header = colorize(
        f"  History — session {session_id} ({len(messages)} messages)",
        color=_ANSI_DIM,
        enabled=color_enabled,
        bold=True,
    )
    print(header)
    print(colorize("  " + "─" * 60, color=_ANSI_DIM, enabled=color_enabled))

    # Group by exchange_id so turns are visually separated
    current_exchange: str | None = None

    for msg in messages:
        exchange_id: str = msg.get("exchange_id", "")
        if exchange_id and exchange_id != current_exchange:
            current_exchange = exchange_id
            # Brief visual divider between turns
            print()

        rank = msg.get("rank", "?")
        role = msg.get("role", "unknown")
        channel = msg.get("channel", "final")

        label, role_color = _HISTORY_ROLE_STYLE.get(
            role, (role.capitalize(), _ANSI_DIM)
        )
        role_str = colorize(
            f"{label:<10}", color=role_color, enabled=color_enabled, bold=True
        )

        channel_suffix = ""
        if channel != "final":
            ch_label = _HISTORY_CHANNEL_LABELS.get(channel, channel)
            channel_suffix = colorize(
                f" [{ch_label}]", color=_ANSI_DIM, enabled=color_enabled
            )

        rank_str = colorize(f"  [{rank:>3}]", color=_ANSI_DIM, enabled=color_enabled)

        # Extract text content from parts
        parts: list[dict[str, Any]] = msg.get("parts") or []
        lines: list[str] = []
        for part in parts:
            ptype = part.get("type", "")
            if ptype == "text":
                text = part.get("text", "")
                lines.append(text)
            elif ptype == "tool_call":
                name = part.get("name", "?")
                args = part.get("args", {})
                args_preview = json.dumps(args, ensure_ascii=False)
                if len(args_preview) > 80:
                    args_preview = args_preview[:77] + "…"
                lines.append(f"→ {name}({args_preview})")
            elif ptype == "tool_result":
                content = part.get("content", "")
                preview = content[:120] + ("…" if len(content) > 120 else "")
                ok = part.get("ok")
                ok_marker = "" if ok is None else ("✓ " if ok else "✗ ")
                lines.append(f"{ok_marker}{preview}")
            elif ptype == "code":
                lang = part.get("language") or ""
                code = part.get("code", "")
                preview = code.split("\n")[0][:80]
                lines.append(f"[code:{lang}] {preview}")
            else:
                lines.append(f"[{ptype}]")

        content_str = (
            "\n           ".join(lines)
            if lines
            else colorize("(no content)", color=_ANSI_DIM, enabled=color_enabled)
        )

        # Metadata (model, token usage)
        meta: dict[str, Any] = msg.get("metadata") or {}
        meta_parts: list[str] = []
        if meta.get("model"):
            meta_parts.append(meta["model"])
        tu = meta.get("token_usage")
        if tu:
            meta_parts.append(
                f"{tu.get('input_tokens', 0)}↑ {tu.get('output_tokens', 0)}↓"
            )
        meta_str = ""
        if meta_parts:
            meta_str = "  " + colorize(
                "  ".join(meta_parts), color=_ANSI_DIM, enabled=color_enabled
            )

        print(f"{rank_str}  {role_str}{channel_suffix}  {content_str}{meta_str}")

    print()


def print_runtime_event(
    event: dict[str, Any],
    *,
    color_enabled: bool,
    saw_assistant_delta: bool,
) -> bool:
    """
    Render one streamed runtime event in a human-friendly terminal form.

    Why this function exists:
    - developers want a live view in `--stream` mode, not raw JSON by default
    - the rendering should remain generic across agent families and event kinds

    How to use it:
    - call for each event yielded by `iter_stream_events(...)`
    - pass whether assistant deltas were already printed to avoid duplicating
      the final answer content

    Example:
    - `saw_delta = print_runtime_event(event, color_enabled=True, saw_assistant_delta=saw_delta)`
    """

    if "error" in event:
        print(
            colorize(
                f"[error] {event['error']}",
                color=_ANSI_RED,
                enabled=color_enabled,
                bold=True,
            )
        )
        return saw_assistant_delta

    kind = event.get("kind")
    if kind == "assistant_delta":
        delta = event.get("delta")
        if isinstance(delta, str):
            print(delta, end="", flush=True)
            return True
        return saw_assistant_delta
    if kind == "final" and saw_assistant_delta:
        print()
        return False
    if saw_assistant_delta:
        print()
        saw_assistant_delta = False

    if kind == "status":
        status = str(event.get("status", "status"))
        detail = event.get("detail")
        suffix = f": {detail}" if isinstance(detail, str) and detail else ""
        print(
            colorize(
                f"[status] {status}{suffix}",
                color=_ANSI_DIM,
                enabled=color_enabled,
            )
        )
        return saw_assistant_delta
    if kind == "tool_call":
        tool_name = str(event.get("tool_name", "tool"))
        print(
            colorize(
                f"[tool] {tool_name}",
                color=_ANSI_YELLOW,
                enabled=color_enabled,
                bold=True,
            )
        )
        return saw_assistant_delta
    if kind == "tool_result":
        content = event.get("content")
        message = (
            content if isinstance(content, str) and content else "(tool completed)"
        )
        color = _ANSI_RED if event.get("is_error") else _ANSI_GREEN
        print(colorize(f"[tool_result] {message}", color=color, enabled=color_enabled))
        return saw_assistant_delta
    if kind == "awaiting_human":
        req = event.get("request") or {}
        title = req.get("title", "Human input required")
        question = req.get("question", "")
        choices = req.get("choices") or []
        print(
            colorize(
                f"\n[HITL] {title}",
                color=_ANSI_BOLD,
                enabled=color_enabled,
                bold=True,
            )
        )
        if question:
            print(question)
        if choices:
            print()
            for i, choice in enumerate(choices, 1):
                label = choice.get("label", choice.get("id", str(i)))
                print(
                    f"  {colorize(str(i), color=_ANSI_CYAN, enabled=color_enabled, bold=True)}. {label}"
                )
        return saw_assistant_delta
    if kind == "final":
        content = event.get("content")
        if isinstance(content, str):
            print(content)
        else:
            print(json.dumps(event, ensure_ascii=False))
        return saw_assistant_delta
    print(json.dumps(event, ensure_ascii=False))
    return saw_assistant_delta


def run_single_turn(
    *,
    client: AgentPodClient,
    agent_id: str,
    message: str,
    session_id: str,
    user_id: str,
    team_id: str | None,
    verbose: bool,
    stream: bool,
    color_enabled: bool,
    resume_payload: Any = None,
) -> tuple[int, dict[str, Any] | None]:
    """
    Execute one prompt and print the most useful runtime output.

    Returns a tuple of (exit_code, hitl_request) where hitl_request is the
    awaiting_human event payload when the agent is paused at a HITL gate, or
    None when the turn completed normally (final event received).

    Why this function exists:
    - interactive and one-shot modes should share the same runtime behavior
    - developers usually want the final answer, with optional raw event output

    How to use it:
    - pass a prepared `AgentPodClient` plus the target agent id and message
    - set `verbose=True` when you want to inspect intermediate runtime events
    - set `stream=True` when you want live event rendering from SSE
    - pass `resume_payload` to resume from a HITL gate

    Example:
    - `exit_code, hitl = run_single_turn(client=client, agent_id="sentinel.react.v2", message="hello", session_id="demo", user_id="alice", team_id="fredlab", verbose=False, stream=False, color_enabled=False)`
    """

    if not stream:
        payload = client.execute(
            agent_id=agent_id,
            message=message,
            session_id=session_id,
            user_id=user_id,
            team_id=team_id,
            resume_payload=resume_payload,
        )
        if "error" in payload:
            print(
                colorize(
                    f"[error] {payload['error']}",
                    color=_ANSI_RED,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            return 1, None
        if payload.get("kind") == "awaiting_human":
            print_runtime_event(
                payload, color_enabled=color_enabled, saw_assistant_delta=False
            )
            return 0, payload
        if verbose and payload.get("kind") != "final":
            print(json.dumps(payload, ensure_ascii=False))
        content = payload.get("content")
        if not isinstance(content, str):
            print("(no final response)")
            return 1, None
        print(content)
        return 0, None

    saw_assistant_delta = False
    saw_final = False
    pending_hitl: dict[str, Any] | None = None
    for event in client.iter_stream_events(
        agent_id=agent_id,
        message=message,
        session_id=session_id,
        user_id=user_id,
        team_id=team_id,
        resume_payload=resume_payload,
    ):
        if verbose:
            print(json.dumps(event, ensure_ascii=False))
            if event.get("kind") == "final":
                saw_final = True
            elif event.get("kind") == "awaiting_human":
                pending_hitl = event
            continue
        saw_assistant_delta = print_runtime_event(
            event,
            color_enabled=color_enabled,
            saw_assistant_delta=saw_assistant_delta,
        )
        if event.get("kind") == "final":
            saw_final = True
        elif event.get("kind") == "awaiting_human":
            pending_hitl = event
    if saw_assistant_delta:
        print()
    if pending_hitl is not None:
        return 0, pending_hitl
    if not saw_final:
        print("(no final response)")
        return 1, None
    return 0, None


def build_hitl_resume_payload(
    *,
    raw_response: str,
    choices: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> Any:
    """
    Convert one terminal HITL answer into the runtime resume payload shape.

    Why this function exists:
    - the interactive shell accepts either a 1-based menu index or a raw
      choice id, but graph `choice_step(...)` expects a structured
      `{"choice_id": ...}` resume payload
    - centralizing the conversion keeps the bank-transfer and similar demos
      consistent across future client changes

    How to use it:
    - pass the raw text entered by the user plus the choice list shown in the
      awaiting-human event
    - use the returned value as `resume_payload` on the next execute call

    Example:
    - `build_hitl_resume_payload(raw_response="1", choices=[{"id": "confirm"}])`
    """

    selected_choice_id = raw_response
    if raw_response.isdigit():
        idx = int(raw_response) - 1
        if 0 <= idx < len(choices):
            selected_choice_id = str(choices[idx].get("id", raw_response))
    return {"choice_id": selected_choice_id}


def run_interactive_chat(
    *,
    client: AgentPodClient,
    agent_id: str | None,
    session_id: str,
    user_id: str,
    team_id: str | None,
    verbose: bool,
    stream: bool,
    color_enabled: bool,
    auth_session: KeycloakUserSessionManager | None,
    callback_host: str,
    callback_port: int,
) -> int:
    """
    Run the interactive developer chat loop against one running pod.

    Why this function exists:
    - repeated local testing is easier as a small REPL than as repeated `curl`
      commands
    - the same loop works across any pod implementing the shared HTTP contract

    How to use it:
    - start the pod separately
    - call this function from `main()` with the parsed CLI arguments

    Example:
    - `run_interactive_chat(client=client, agent_id=None, session_id="demo", user_id="alice", team_id="fredlab", verbose=False, stream=False, color_enabled=False, auth_session=None, callback_host="127.0.0.1", callback_port=8765)`
    """

    known_agents = client.list_agents()
    if not known_agents:
        print("No agents are registered in the target pod.")
        return 1

    current_agent = agent_id or known_agents[0]
    if current_agent not in known_agents:
        print(f"Unknown agent_id: {current_agent}")
        print("Available agents:")
        for available_agent in known_agents:
            print(f"  {available_agent}")
        return 1

    install_readline_completion(
        lambda line: completion_candidates(line, agent_ids=known_agents)
    )

    print(
        f"Connected to {colorize(client.base_url, color=_ANSI_DIM, enabled=color_enabled)}"
    )
    print(
        f"Current agent: {colorize(current_agent, color=_ANSI_CYAN, enabled=color_enabled, bold=True)}"
    )
    print(
        "Mode: "
        f"{colorize(execution_mode_label(stream=stream), color=_ANSI_GREEN if stream else _ANSI_YELLOW, enabled=color_enabled, bold=True)}"
    )
    if auth_session is not None:
        print(
            "Auth: "
            f"{colorize(auth_session.describe(), color=_ANSI_DIM, enabled=color_enabled)}"
        )
    if team_id:
        print(
            "Team: "
            f"{colorize(team_id, color=_ANSI_GREEN, enabled=color_enabled, bold=True)}"
        )
    print(
        "Use /agents to list agents, /agent <id> to switch, "
        "/team <id> to set team scope, /kpi to inspect metrics, /quit to exit."
    )

    current_session_id = session_id
    current_stream = stream
    current_team_id = team_id
    while True:
        try:
            prompt = (
                f"{colorize(current_agent, color=_ANSI_CYAN, enabled=color_enabled, bold=True)}"
                "> "
            )
            message = input(prompt).strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            continue

        if not message:
            continue
        if message.startswith("/help"):
            question = message.removeprefix("/help").strip()
            if question:
                _ask_cli_help(
                    question=question,
                    client=client,
                    agent_id=current_agent,
                    user_id=user_id,
                    team_id=current_team_id,
                    color_enabled=color_enabled,
                )
            else:
                print_help()
            continue
        if message == "/login":
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings with "
                    "`--keycloak-realm-url` and `--keycloak-client-id`, or run "
                    "from a pod project with configuration.yaml."
                )
                continue
            try:
                auth_session.login_with_pkce(
                    callback_host=callback_host,
                    callback_port=callback_port,
                )
            except (httpx.HTTPError, RuntimeError, OSError) as exc:
                print(f"Login failed: {exc}")
                continue
            print(
                "Logged in as "
                f"{colorize(auth_session.current_username() or 'unknown-user', color=_ANSI_GREEN, enabled=color_enabled, bold=True)}"
            )
            continue
        if message.startswith("/login-password"):
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings with "
                    "`--keycloak-realm-url` and `--keycloak-client-id`, or run "
                    "from a pod project with configuration.yaml."
                )
                continue
            provided_username = message.removeprefix("/login-password").strip()
            username = provided_username or input("Username: ").strip()
            if not username:
                print("Username cannot be empty.")
                continue
            password = getpass.getpass("Password: ")
            try:
                auth_session.login(username=username, password=password)
            except httpx.HTTPError as exc:
                print(f"Login failed: {exc}")
                continue
            print(
                "Logged in as "
                f"{colorize(auth_session.current_username() or username, color=_ANSI_GREEN, enabled=color_enabled, bold=True)}"
            )
            continue
        if message == "/whoami":
            if auth_session is None:
                print("Auth: not configured")
            else:
                print(f"Auth: {auth_session.describe()}")
            continue
        if message == "/logout":
            if auth_session is None:
                print("Auth: not configured")
                continue
            auth_session.logout()
            print("Logged out.")
            continue
        if message == "/agents":
            known_agents = client.list_agents()
            for available_agent in known_agents:
                highlighted = colorize(
                    available_agent,
                    color=_ANSI_CYAN if available_agent == current_agent else _ANSI_DIM,
                    enabled=color_enabled,
                    bold=available_agent == current_agent,
                )
                print(highlighted)
            continue
        if message.startswith("/mode"):
            try:
                requested_mode = parse_mode_command(message)
            except ValueError as exc:
                print(str(exc))
                continue
            if requested_mode is None:
                print(
                    "Mode: "
                    f"{colorize(execution_mode_label(stream=current_stream), color=_ANSI_GREEN if current_stream else _ANSI_YELLOW, enabled=color_enabled, bold=True)}"
                )
                continue
            current_stream = requested_mode
            print(
                "Switched to "
                f"{colorize(execution_mode_label(stream=current_stream), color=_ANSI_GREEN if current_stream else _ANSI_YELLOW, enabled=color_enabled, bold=True)} mode"
            )
            continue
        if message.startswith("/agent "):
            requested_agent = message.removeprefix("/agent ").strip()
            if requested_agent not in known_agents:
                print(f"Unknown agent_id: {requested_agent}")
                continue
            current_agent = requested_agent
            print(
                f"Switched to {colorize(current_agent, color=_ANSI_CYAN, enabled=color_enabled, bold=True)}"
            )
            continue
        if message.startswith("/scenario "):
            scenario_path = message.removeprefix("/scenario ").strip()
            try:
                run_scenario_file(
                    scenario_path,
                    client=client,
                    team_id_override=current_team_id,
                )
                print("All checks passed.")
            except (AssertionError, ValueError, FileNotFoundError) as exc:
                print(f"Scenario failed: {exc}")
            continue
        if message.startswith("/session "):
            current_session_id = message.removeprefix("/session ").strip()
            print(
                f"Session set to {colorize(current_session_id, color=_ANSI_DIM, enabled=color_enabled)}"
            )
            continue
        if message == "/team":
            if current_team_id:
                print(f"Current team: {current_team_id}")
            else:
                print("Current team: none")
            continue
        if message.startswith("/team "):
            next_team = message.removeprefix("/team ").strip()
            if not next_team:
                print("Usage: /team [team_id|clear]")
                continue
            if next_team.lower() in {"clear", "none", "-"}:
                current_team_id = None
                print("Cleared team scope.")
            else:
                current_team_id = next_team
                print(
                    "Team set to "
                    + colorize(
                        current_team_id,
                        color=_ANSI_GREEN,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
            continue
        if message == "/sessions":
            try:
                sessions = client.list_sessions(user_id)
            except Exception as exc:
                print(f"Error fetching sessions: {exc}")
                continue
            if not sessions:
                print("No sessions found for this user.")
            else:
                print(
                    colorize(
                        f"  Sessions for {user_id} ({len(sessions)} total):",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                for i, sid in enumerate(sessions):
                    marker = " ◀ current" if sid == current_session_id else ""
                    prefix_color = (
                        _ANSI_CYAN if sid == current_session_id else _ANSI_DIM
                    )
                    line = colorize(
                        f"  {i + 1:>3}.  {sid}",
                        color=prefix_color,
                        enabled=color_enabled,
                    )
                    print(
                        line
                        + colorize(marker, color=_ANSI_GREEN, enabled=color_enabled)
                    )
            continue
        if message.startswith("/history"):
            target_session = (
                message.removeprefix("/history").strip() or current_session_id
            )
            if not target_session:
                print("No session active. Use /session <id> or /history <session_id>.")
                continue
            try:
                msgs = client.get_session_messages(target_session)
            except Exception as exc:
                print(f"Error fetching history: {exc}")
                continue
            if not msgs:
                print(
                    colorize(
                        f"  Session {target_session} has no stored history yet.",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
            else:
                print_history(
                    msgs, session_id=target_session, color_enabled=color_enabled
                )
            continue
        if message.startswith("/kpi"):
            pattern = message.removeprefix("/kpi").strip() or None
            try:
                metrics_text = client.get_metrics_text()
                metric_samples = parse_prometheus_text_exposition(metrics_text)
            except Exception as exc:
                print(f"Error fetching KPI metrics: {exc}")
                continue
            for line in render_kpi_report(
                metric_samples,
                color_enabled=color_enabled,
                pattern=pattern,
            ):
                print(line)
            continue
        if message.startswith("/checkpoints"):
            arg = message.removeprefix("/checkpoints").strip()
            limit = 20
            if arg:
                try:
                    limit = int(arg)
                except ValueError:
                    print("Usage: /checkpoints [limit]  (limit must be an integer)")
                    continue
            try:
                threads = client.list_checkpoint_threads(limit=limit)
            except Exception as exc:
                print(f"Error fetching checkpoints: {exc}")
                continue
            if not threads:
                print("No checkpoint threads found.")
            else:
                print(
                    colorize(
                        f"  Checkpoint threads ({len(threads)} shown, limit={limit}):",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                print(
                    colorize(
                        f"  {'Thread ID':<36}  {'CPs':>4}  {'Latest':<19}  {'cp struct':>9}  {'blobs':>5}  {'blob data':>9}  {'pend':>4}",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(colorize("  " + "─" * 96, color=_ANSI_DIM, enabled=color_enabled))
                for t in threads:
                    sid = t.get("session_id", "?")
                    count = t.get("checkpoint_count", 0)
                    latest = (t.get("latest_created_at") or "-")[:19]
                    cp_bytes = fmt_bytes(t.get("checkpoint_bytes_total", 0))
                    blob_cnt = t.get("blob_count", 0)
                    blob_bytes = fmt_bytes(t.get("blob_bytes_total", 0))
                    pending = t.get("pending_write_count", 0)
                    marker = " ◀" if sid == current_session_id else ""
                    line_color = _ANSI_CYAN if sid == current_session_id else _ANSI_DIM
                    pending_color = _ANSI_YELLOW if pending > 0 else _ANSI_DIM
                    print(
                        colorize(
                            f"  {sid:<36}", color=line_color, enabled=color_enabled
                        )
                        + colorize(
                            f"  {count:>4}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {latest:<19}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {cp_bytes:>9}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {blob_cnt:>5}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {blob_bytes:>9}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {pending:>4}",
                            color=pending_color,
                            enabled=color_enabled,
                        )
                        + colorize(marker, color=_ANSI_GREEN, enabled=color_enabled)
                    )
            continue
        if message.startswith("/checkpoint "):
            target_session = message.removeprefix("/checkpoint ").strip()
            if not target_session:
                print("Usage: /checkpoint <session_id>")
                continue
            try:
                detail = client.get_checkpoint_thread(target_session)
            except Exception as exc:
                print(f"Error fetching checkpoint detail: {exc}")
                continue
            checkpoints: list[dict[str, Any]] = detail.get("checkpoints") or []
            if not checkpoints:
                print(f"No checkpoints found for session {target_session!r}.")
            else:
                print(
                    colorize(
                        f"  Checkpoints for session {target_session} ({len(checkpoints)} entries):",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                print(
                    colorize(
                        f"  {'step':>4}  {'source':<7}  {'node(s)':<20}  {'cp struct':>9}  {'pend':>4}  {'checkpoint_id':<38}  created",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(
                    colorize("  " + "─" * 110, color=_ANSI_DIM, enabled=color_enabled)
                )
                for cp in checkpoints:
                    cp_id = cp.get("checkpoint_id", "?")
                    step = cp.get("step")
                    step_str = str(step) if step is not None else "?"
                    source = cp.get("source") or "?"
                    nodes = cp.get("node_names") or []
                    node_str = (
                        ", ".join(nodes)
                        if nodes
                        else ("(start)" if source == "input" else "")
                    )
                    node_str = node_str[:20]
                    cp_bytes = fmt_bytes(cp.get("checkpoint_bytes", 0))
                    pending = cp.get("pending_write_count", 0)
                    created = (cp.get("created_at") or "-")[:19]
                    pending_color = _ANSI_YELLOW if pending > 0 else _ANSI_DIM
                    print(
                        colorize(
                            f"  {step_str:>4}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {source:<7}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {node_str:<20}", color=_ANSI_CYAN, enabled=color_enabled
                        )
                        + colorize(
                            f"  {cp_bytes:>9}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {pending:>4}",
                            color=pending_color,
                            enabled=color_enabled,
                        )
                        + colorize(
                            f"  {cp_id:<38}", color=_ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {created}", color=_ANSI_DIM, enabled=color_enabled
                        )
                    )
                print(
                    colorize(
                        "\n  Blob content (channel states) is shared across checkpoints at thread level.",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(
                    colorize(
                        "  Use /checkpoints to see total blob size for this thread.",
                        color=_ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
            continue
        if message == "/stats":
            try:
                stats = client.get_checkpoint_stats()
            except Exception as exc:
                print(f"Error fetching checkpoint stats: {exc}")
                continue
            cp_bytes = fmt_bytes(stats.get("checkpoint_bytes_approx", 0))
            blob_bytes = fmt_bytes(stats.get("blob_bytes_approx", 0))
            total_bytes = fmt_bytes(
                stats.get("checkpoint_bytes_approx", 0)
                + stats.get("blob_bytes_approx", 0)
            )
            pending = stats.get("pending_write_count", 0)
            pending_color = _ANSI_YELLOW if pending > 0 else _ANSI_DIM
            print(
                colorize(
                    "  Checkpoint storage stats:",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(colorize("  " + "─" * 50, color=_ANSI_DIM, enabled=color_enabled))
            print(
                colorize(
                    f"  Threads:              {stats.get('thread_count', 0):>6}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    f"  Checkpoints:          {stats.get('checkpoint_count', 0):>6}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  (pointer structs: {cp_bytes})",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    f"  Blob rows (channels): {stats.get('blob_count', 0):>6}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  (channel states:  {blob_bytes})",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    f"  Pending writes:       {pending:>6}",
                    color=pending_color,
                    enabled=color_enabled,
                )
                + (
                    colorize(
                        "  ⚠ non-zero: interrupted turn writes not cleaned up",
                        color=_ANSI_YELLOW,
                        enabled=color_enabled,
                    )
                    if pending > 0
                    else ""
                )
            )
            print(colorize("  " + "─" * 50, color=_ANSI_DIM, enabled=color_enabled))
            print(
                colorize(
                    f"  Total storage approx: {total_bytes}",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(
                colorize(
                    "\n  Note: blob rows are deduplicated by (channel, version) within a thread.",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    "  Blob data dominates cost and grows with total conversation turns.",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            continue
        if message in {"/context", "/execution-context"}:
            print(
                colorize(
                    "  Execution context summary:",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(colorize("  " + "─" * 50, color=_ANSI_DIM, enabled=color_enabled))
            agent_label = colorize(
                current_agent, color=_ANSI_CYAN, enabled=color_enabled, bold=True
            )
            session_label = (
                colorize(current_session_id, color=_ANSI_GREEN, enabled=color_enabled)
                if current_session_id
                else colorize("none", color=_ANSI_YELLOW, enabled=color_enabled)
            )
            mode_label = colorize(
                execution_mode_label(stream=current_stream),
                color=_ANSI_GREEN if current_stream else _ANSI_YELLOW,
                enabled=color_enabled,
                bold=True,
            )
            user_label = colorize(
                user_id or "anonymous", color=_ANSI_DIM, enabled=color_enabled
            )
            auth_label = (
                colorize(
                    auth_session.describe(), color=_ANSI_DIM, enabled=color_enabled
                )
                if auth_session is not None
                else colorize("not configured", color=_ANSI_DIM, enabled=color_enabled)
            )
            print(f"  Agent:    {agent_label}")
            print(f"  Session:  {session_label}")
            print(f"  User:     {user_label}")
            print(
                "  Team:     "
                + (
                    colorize(
                        current_team_id,
                        color=_ANSI_GREEN,
                        enabled=color_enabled,
                    )
                    if current_team_id
                    else colorize("none", color=_ANSI_YELLOW, enabled=color_enabled)
                )
            )
            print(f"  Mode:     {mode_label}")
            print(f"  Auth:     {auth_label}")
            print(
                f"  Pod URL:  {colorize(client.base_url, color=_ANSI_DIM, enabled=color_enabled)}"
            )
            print(
                "  Metrics:  "
                + colorize(
                    client.metrics_url or "not configured",
                    color=_ANSI_DIM if client.metrics_url else _ANSI_YELLOW,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    "\n  Note: execution_grant is issued by control-plane for production runs.",
                    color=_ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            continue
        if message in {"/quit", "/exit"}:
            return 0

        if message.startswith("/"):
            bare = message.split()[0]
            _USAGE_HINTS: dict[str, str] = {
                "/session": "/session <id>",
                "/team": "/team [team_id|clear]",
                "/agent": "/agent <agent_id>  — use /agents to list available agents",
                "/scenario": "/scenario <file>",
                "/checkpoint": "/checkpoint <thread_id>  — use /checkpoints to list threads",
            }
            if bare in _USAGE_HINTS:
                print(f"Usage: {_USAGE_HINTS[bare]}")
            else:
                print(
                    f"Unknown command: {bare!r}  "
                    "Type /help for available commands, or /help <question> to ask."
                )
            continue

        exit_code, hitl = run_single_turn(
            client=client,
            agent_id=current_agent,
            message=message,
            session_id=current_session_id,
            user_id=user_id,
            team_id=current_team_id,
            verbose=verbose,
            stream=current_stream,
            color_enabled=color_enabled,
        )
        while hitl is not None:
            req = hitl.get("request") or {}
            choices = req.get("choices") or []
            free_text = req.get("free_text", False)
            if free_text:
                try:
                    answer = input("Your answer: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nCancelled.")
                    hitl = None
                    continue
                resume_value: Any = answer
            elif choices:
                try:
                    raw = input("Your choice (number or id): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nCancelled.")
                    hitl = None
                    continue
                resume_value = build_hitl_resume_payload(
                    raw_response=raw,
                    choices=choices,
                )
            else:
                # No choices — just pass the raw user text as resume payload
                try:
                    resume_value = input("Your response: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nCancelled.")
                    hitl = None
                    continue
            exit_code, hitl = run_single_turn(
                client=client,
                agent_id=current_agent,
                message="",
                session_id=current_session_id,
                user_id=user_id,
                team_id=current_team_id,
                verbose=verbose,
                stream=current_stream,
                color_enabled=color_enabled,
                resume_payload=resume_value,
            )
        if exit_code != 0:
            print("The request failed. Use /help for commands or try another agent.")


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------


def _scenario_resolve(value: str, *, run_id: str) -> str:
    """Substitute ${run_id} placeholders in one string."""
    return value.replace("${run_id}", run_id)


def _scenario_apply_checks(
    checks: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]],
    final_event: dict[str, Any],
    step_id: str,
) -> None:
    """
    Assert every declared check against one step's events.

    Check vocabulary:
      kind: <value>                — final_event["kind"] == value
      no_error: true               — no event has key "error"
      content_contains: <text>     — text in final_event["content"]
      content_not_contains: <text> — text not in final_event["content"]
    """
    for check in checks:
        if not isinstance(check, dict) or len(check) != 1:
            raise ValueError(
                f"[step:{step_id}] Each check must be a single-key dict, got: {check!r}"
            )
        (check_name, expected) = next(iter(check.items()))

        if check_name == "kind":
            actual = final_event.get("kind")
            assert actual == expected, (
                f"[step:{step_id}] Expected kind={expected!r}, got {actual!r}.\n"
                f"  Final event: {final_event}"
            )
        elif check_name == "no_error":
            if expected:
                bad = [e for e in events if "error" in e]
                assert not bad, f"[step:{step_id}] Expected no error events, got: {bad}"
        elif check_name == "content_contains":
            content = final_event.get("content", "")
            assert isinstance(content, str) and expected in content, (
                f"[step:{step_id}] Expected content to contain {expected!r}.\n"
                f"  Actual content: {content!r}"
            )
        elif check_name == "content_not_contains":
            content = final_event.get("content", "")
            assert isinstance(content, str) and expected not in content, (
                f"[step:{step_id}] Expected content NOT to contain {expected!r}.\n"
                f"  Actual content: {content!r}"
            )
        else:
            raise ValueError(
                f"[step:{step_id}] Unknown check {check_name!r}. "
                "Supported: kind, no_error, content_contains, content_not_contains"
            )


def _scenario_run_pause(step: dict[str, Any], *, step_id: str, run_id: str) -> None:
    """
    Print instructions and wait for the tester to press Enter.

    Skipped automatically when stdin is not a TTY (e.g. CI).
    """
    message = _scenario_resolve(
        step.get("message", "Manual step required."), run_id=run_id
    )
    print(f"\n[step:{step_id}] PAUSE")
    print(message)

    if not sys.stdin.isatty():
        print(
            f"[step:{step_id}] stdin is not a TTY — skipping pause "
            "(pod-restart durability will not be verified in this run)."
        )
        return

    input("\n  >>> Press Enter to continue... ")
    print(f"[step:{step_id}] Continuing.\n")


def _scenario_run_turn(
    client: AgentPodClient,
    step: dict[str, Any],
    *,
    agent_id: str,
    user_id: str,
    team_id: str | None,
    run_id: str,
    step_id: str,
) -> None:
    """Execute one turn and apply the declared checks."""
    mode = step.get("mode", "final")
    session_id = _scenario_resolve(step["session_id"], run_id=run_id)
    message = _scenario_resolve(step["message"], run_id=run_id)
    checks = step.get("checks", [])

    print(f"\n[step:{step_id}] mode={mode} session={session_id}")
    print(f"  >> {message[:80]}{'…' if len(message) > 80 else ''}")

    if mode == "stream":
        events = client.stream_events(
            agent_id=agent_id,
            message=message,
            session_id=session_id,
            user_id=user_id,
            team_id=team_id,
        )
    elif mode == "final":
        events = [
            client.execute(
                agent_id=agent_id,
                message=message,
                session_id=session_id,
                user_id=user_id,
                team_id=team_id,
            )
        ]
    else:
        raise ValueError(f"[step:{step_id}] Unknown mode {mode!r}.")

    assert events, f"[step:{step_id}] Pod returned no events."
    final_event = events[-1]
    print(
        f"  << kind={final_event.get('kind')} "
        f"content={str(final_event.get('content', ''))[:120]}"
    )
    _scenario_apply_checks(
        checks, events=events, final_event=final_event, step_id=step_id
    )


def run_scenario_file(
    path: Path | str,
    *,
    client: AgentPodClient,
    team_id_override: str | None = None,
) -> None:
    """
    Parse and execute one YAML scenario file against the given pod client.

    Why this function exists:
    - the same runner is shared by `fred-agent-chat --scenario` (CLI) and
      the `fred-agents` pytest integration suite
    - keeping it here means any pod project that depends on fred-runtime
      gets the runner for free

    How to use it:
    - CLI:   fred-agent-chat --scenario path/to/sentinel_smoke.yaml --team-id fredlab
    - pytest: call directly and let AssertionError propagate to pytest

    The function raises AssertionError on a failed check and ValueError on a
    malformed scenario; callers decide whether to catch or propagate.
    """
    raw = yaml.safe_load(Path(path).read_text())
    run_id = uuid.uuid4().hex[:8]

    name = raw.get("name", path)
    agent_id = raw["agent_id"]
    user_id = raw.get("user_id", "test-user")
    team_id = team_id_override or raw.get("team_id")

    print(f"\n{'=' * 60}")
    print(f"Scenario : {name}")
    print(f"run_id   : {run_id}")
    print(f"{'=' * 60}")

    for step in raw["steps"]:
        step_type = step.get("type", "turn")
        step_id = step.get("id", "(unnamed)")

        if step_type == "pause":
            _scenario_run_pause(step, step_id=step_id, run_id=run_id)
        elif step_type == "turn":
            _scenario_run_turn(
                client,
                step,
                agent_id=agent_id,
                user_id=user_id,
                team_id=team_id,
                run_id=run_id,
                step_id=step_id,
            )
        else:
            raise ValueError(f"Unknown step type {step_type!r} in step {step_id!r}")


def build_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the chat client.

    Why this function exists:
    - argument parsing should stay explicit and centralized
    - tests can reuse the same parser behavior without invoking a subprocess

    How to use it:
    - call from `main()` and parse the process argv

    Example:
    - `parser = build_parser()`
    """

    parser = argparse.ArgumentParser(description="Chat with a running Fred agent pod.")
    parser.add_argument(
        "--base-url",
        default=default_agent_pod_base_url(),
        help="Pod base URL. Defaults to app.port + app.base_url from configuration.yaml.",
    )
    parser.add_argument(
        "--metrics-url",
        default=None,
        help=(
            "Prometheus metrics URL used by /kpi. Defaults to app.metrics_port "
            "from configuration.yaml when available."
        ),
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="Optional agent id. Defaults to the first registered agent.",
    )
    parser.add_argument(
        "--session-id",
        default=f"dev-session-{uuid.uuid4().hex[:8]}",
        help="Session id sent to the pod for multi-turn state.",
    )
    parser.add_argument(
        "--user-id",
        default=getpass.getuser(),
        help="User id sent to the pod context.",
    )
    parser.add_argument(
        "--team-id",
        default=os.getenv("FRED_AGENT_TEAM_ID"),
        help="Optional team id sent to the pod context for team-scoped execution.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser-based Keycloak PKCE login before sending requests.",
    )
    parser.add_argument(
        "--login-password",
        action="store_true",
        help="Use direct username/password login as a local fallback.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("FRED_AGENT_USERNAME"),
        help="Optional default username used by `--login-password` and `/login-password`.",
    )
    parser.add_argument(
        "--keycloak-realm-url",
        default=os.getenv("FRED_AGENT_KEYCLOAK_REALM_URL"),
        help="Optional Keycloak realm URL for CLI login discovery.",
    )
    parser.add_argument(
        "--keycloak-client-id",
        default=os.getenv("FRED_AGENT_KEYCLOAK_CLIENT_ID"),
        help="Optional Keycloak client id for CLI login discovery.",
    )
    parser.add_argument(
        "--keycloak-client-secret",
        default=os.getenv("FRED_AGENT_KEYCLOAK_CLIENT_SECRET"),
        help="Optional Keycloak client secret for confidential login clients.",
    )
    parser.add_argument(
        "--keycloak-callback-host",
        default=default_pkce_callback_host(),
        help="Loopback host used for browser PKCE login callbacks.",
    )
    parser.add_argument(
        "--keycloak-callback-port",
        type=int,
        default=default_pkce_callback_port(),
        help="Loopback port used for browser PKCE login callbacks.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print intermediate runtime events in addition to the final answer.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use the SSE endpoint and render events live as they arrive.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI terminal colors in the chat client output.",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        metavar="FILE",
        help=(
            "Run a YAML scenario file against the pod and exit. "
            "Mutually exclusive with interactive and one-shot modes."
        ),
    )
    parser.add_argument(
        "message",
        nargs="*",
        help="Optional one-shot message. Omit it to start interactive mode.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Run the Fred agent pod chat client.

    Why this function exists:
    - it provides one small entrypoint developers can use across local pods,
      CI demos, and manual smoke testing

    How to use it:
    - run `fred-agent-chat` for interactive mode
    - add a trailing message for one-shot execution

    Example:
    - `main(["--agent", "sentinel.react.v2", "hello"])`
    """

    env_file = load_cli_environment(log_prefix="[CHAT CONFIG]")
    parser = build_parser()
    args = parser.parse_args(argv)
    base_url = normalize_base_url(args.base_url)
    metrics_url = (
        args.metrics_url.rstrip("/")
        if args.metrics_url
        else default_agent_metrics_url(base_url=base_url)
    )
    color_enabled = colors_enabled(no_color=args.no_color)

    config_file = default_configuration_file()
    print(f"[chat] env file  : {env_file}")
    print(f"[chat] config    : {config_file} (exists={config_file.exists()})")
    print(f"[chat] pod url   : {base_url}")
    print(f"[chat] metrics   : {metrics_url or 'not configured'}")

    http_client = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0, read=None))
    auth_session = None
    login_config = resolve_keycloak_login_config(
        realm_url=args.keycloak_realm_url,
        client_id=args.keycloak_client_id,
        client_secret=args.keycloak_client_secret,
    )
    if login_config is not None:
        print(
            f"[chat] auth      : keycloak realm={login_config.realm_url}"
            f"  client={login_config.client_id}"
        )
        auth_session = KeycloakUserSessionManager(
            config=login_config,
            cache_file=default_keycloak_token_file(),
            log_prefix="[chat]",
        )
    else:
        print("[chat] auth      : none  (standalone mode — security disabled)")

    # In no-security mode with no explicit --team-id, default to personal so
    # checkpoints, KPIs, and history carry consistent team identity.
    effective_team_id = args.team_id or ("personal" if login_config is None else None)
    if effective_team_id:
        print(f"[chat] team      : {effective_team_id}")

    static_token = os.getenv("FRED_AGENT_TOKEN")

    client = AgentPodClient(
        base_url=base_url,
        http_client=http_client,
        metrics_url=metrics_url,
        token_provider=build_cli_token_provider(
            auth_session=auth_session,
            static_token=static_token,
            log_prefix="[chat]",
        )
        if auth_session is not None or static_token
        else None,
    )

    try:
        if args.login and args.login_password:
            print("Choose only one login mode: `--login` or `--login-password`.")
            return 1
        if args.login:
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings with "
                    "`--keycloak-realm-url` and `--keycloak-client-id`, or run "
                    "from a pod project with configuration.yaml."
                )
                return 1
            auth_session.login_with_pkce(
                callback_host=args.keycloak_callback_host,
                callback_port=args.keycloak_callback_port,
            )
            print(f"Logged in as {auth_session.current_username()}.")
        if args.login_password:
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings with "
                    "`--keycloak-realm-url` and `--keycloak-client-id`, or run "
                    "from a pod project with configuration.yaml."
                )
                return 1
            username = args.username or input("Username: ").strip()
            if not username:
                print("Username cannot be empty.")
                return 1
            password = getpass.getpass("Password: ")
            auth_session.login(username=username, password=password)
            print(f"Logged in as {auth_session.current_username()}.")
        if args.scenario:
            try:
                run_scenario_file(
                    args.scenario,
                    client=client,
                    team_id_override=effective_team_id,
                )
                print("\nAll checks passed.")
                return 0
            except AssertionError as exc:
                print(f"\nScenario FAILED: {exc}")
                return 1
        if args.message:
            agents = client.list_agents()
            active_agent = args.agent or agents[0]
            exit_code, _ = run_single_turn(
                client=client,
                agent_id=active_agent,
                message=" ".join(args.message),
                session_id=args.session_id,
                user_id=args.user_id,
                team_id=effective_team_id,
                verbose=args.verbose,
                stream=args.stream,
                color_enabled=color_enabled,
            )
            return exit_code
        return run_interactive_chat(
            client=client,
            agent_id=args.agent,
            session_id=args.session_id,
            user_id=args.user_id,
            team_id=effective_team_id,
            verbose=args.verbose,
            stream=args.stream,
            color_enabled=color_enabled,
            auth_session=auth_session,
            callback_host=args.keycloak_callback_host,
            callback_port=args.keycloak_callback_port,
        )
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}")
        return 1
    finally:
        http_client.close()
        if auth_session is not None:
            auth_session.close()


__all__ = [
    "AgentPodClient",
    "DEFAULT_AGENT_POD_BASE_URL",
    "KeycloakLoginConfig",
    "KeycloakUserSessionManager",
    "build_parser",
    "completion_candidates",
    "default_agent_metrics_url",
    "default_agent_pod_base_url",
    "main",
    "normalize_base_url",
    "parse_prometheus_text_exposition",
    "render_kpi_report",
    "run_interactive_chat",
    "run_scenario_file",
    "run_single_turn",
    "summarize_prometheus_histograms",
]


if __name__ == "__main__":
    raise SystemExit(main())
