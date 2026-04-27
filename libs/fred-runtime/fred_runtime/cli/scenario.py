from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from .history_display import build_hitl_resume_payload
from .pod_client import AgentPodClient


class ScenarioSkipped(RuntimeError):
    """Raised by run_scenario_file when a required env var is absent — callers should skip."""


def _scenario_resolve(value: str, *, run_id: str) -> str:
    """Substitute ${run_id} and ${env:VAR} placeholders; raises ScenarioSkipped when a required env var is absent."""
    result = value.replace("${run_id}", run_id)

    def _env_sub(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var)
        if val is None:
            raise ScenarioSkipped(
                f"Scenario requires env var {var!r} — set it and re-run to include this scenario."
            )
        return val

    return re.sub(r"\$\{env:([^}]+)\}", _env_sub, result)


def _scenario_apply_checks(
    checks: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]],
    final_event: dict[str, Any],
    step_id: str,
    client: AgentPodClient | None = None,
    session_id: str | None = None,
) -> None:
    """
    Assert every declared check against one step's events.

    Check vocabulary:
      kind: <value>                — final_event["kind"] == value
      no_error: true               — no event has key "error"
      content_contains: <text>     — text in final_event["content"]
      content_not_contains: <text> — text not in final_event["content"]
      history_has_messages: true   — session history is non-empty (requires client + session_id)
      kpi_turn_recorded: true      — KPI ring buffer has a record for this session
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
        elif check_name == "history_has_messages":
            assert client and session_id, (
                f"[step:{step_id}] history_has_messages requires a client and session_id"
            )
            messages = client.get_session_messages(session_id)
            if expected:
                assert messages, (
                    f"[step:{step_id}] Expected session {session_id!r} to have history, got empty list"
                )
            else:
                assert not messages, (
                    f"[step:{step_id}] Expected empty history for {session_id!r}, got {len(messages)} messages"
                )
        elif check_name == "kpi_turn_recorded":
            assert client and session_id, (
                f"[step:{step_id}] kpi_turn_recorded requires a client and session_id"
            )
            turns = client.get_kpi_turns(limit=50)
            has_turn = any(t.get("session_id") == session_id for t in turns)
            if expected:
                assert has_turn, (
                    f"[step:{step_id}] Expected a KPI turn record for session {session_id!r}; "
                    f"found none among {len(turns)} buffered turns"
                )
            else:
                assert not has_turn, (
                    f"[step:{step_id}] Expected no KPI turn for session {session_id!r} but found one"
                )
        else:
            raise ValueError(
                f"[step:{step_id}] Unknown check {check_name!r}. "
                "Supported: kind, no_error, content_contains, content_not_contains, "
                "history_has_messages, kpi_turn_recorded"
            )


def _scenario_run_pause(step: dict[str, Any], *, step_id: str, run_id: str) -> None:
    """Print instructions and wait for the tester to press Enter. Skipped when stdin is not a TTY."""
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
    agent_instance_id: str | None,
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
            agent_instance_id=agent_instance_id,
        )
    elif mode == "final":
        events = [
            client.execute(
                agent_id=agent_id,
                message=message,
                session_id=session_id,
                user_id=user_id,
                team_id=team_id,
                agent_instance_id=agent_instance_id,
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
        checks,
        events=events,
        final_event=final_event,
        step_id=step_id,
        client=client,
        session_id=session_id,
    )


def _scenario_run_hitl(
    client: AgentPodClient,
    step: dict[str, Any],
    *,
    agent_id: str,
    agent_instance_id: str | None,
    user_id: str,
    team_id: str | None,
    run_id: str,
    step_id: str,
) -> None:
    """
    Execute a two-phase HITL flow: trigger → awaiting_human → resume → final.

    Step YAML keys:
      message:        trigger message (e.g. "hitl choice")
      session_id:     session identifier (supports ${run_id} placeholder)
      resume_choice:  choice id to select on resume (e.g. "option_a" or "1")
      checks:         applied to the resume events (same vocabulary as turn checks)
    """
    session_id = _scenario_resolve(step["session_id"], run_id=run_id)
    message = _scenario_resolve(step["message"], run_id=run_id)
    resume_choice = str(step.get("resume_choice", "1"))
    checks = step.get("checks", [])

    print(f"\n[step:{step_id}] HITL  session={session_id}")
    print(f"  >> trigger: {message[:80]}")

    trigger_events = client.stream_events(
        agent_id=agent_id,
        message=message,
        session_id=session_id,
        user_id=user_id,
        team_id=team_id,
        agent_instance_id=agent_instance_id,
    )
    hitl_event = next(
        (e for e in reversed(trigger_events) if e.get("kind") == "awaiting_human"),
        None,
    )
    assert hitl_event is not None, (
        f"[step:{step_id}] Expected an awaiting_human event; "
        f"got kinds: {[e.get('kind') for e in trigger_events]}"
    )
    hitl_request = hitl_event.get("request", {})
    checkpoint_id = hitl_request.get("checkpoint_id")
    choices = hitl_request.get("choices", [])
    assert checkpoint_id, (
        f"[step:{step_id}] awaiting_human event missing request.checkpoint_id"
    )
    print(
        f"  << awaiting_human  checkpoint_id={checkpoint_id}  choices={[c.get('id') for c in choices]}"
    )

    resume_payload = build_hitl_resume_payload(
        raw_response=resume_choice, choices=choices
    )
    print(f"  >> resume: {resume_payload}")
    resume_events = client.stream_events(
        agent_id=agent_id,
        message="",
        session_id=session_id,
        user_id=user_id,
        team_id=team_id,
        agent_instance_id=agent_instance_id,
        checkpoint_id=checkpoint_id,
        resume_payload=resume_payload,
    )
    assert resume_events, f"[step:{step_id}] Pod returned no events on HITL resume."
    final_event = resume_events[-1]
    print(
        f"  << kind={final_event.get('kind')} "
        f"content={str(final_event.get('content', ''))[:120]}"
    )
    _scenario_apply_checks(
        checks,
        events=resume_events,
        final_event=final_event,
        step_id=step_id,
        client=client,
        session_id=session_id,
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

    The function raises AssertionError on a failed check and ValueError on a
    malformed scenario; callers decide whether to catch or propagate.
    """
    raw = yaml.safe_load(Path(path).read_text())
    run_id = uuid.uuid4().hex[:8]

    name = raw.get("name", path)
    agent_id = raw["agent_id"]
    user_id = raw.get("user_id", "test-user")
    team_id = team_id_override or raw.get("team_id")

    raw_instance_id = raw.get("agent_instance_id")
    agent_instance_id = (
        _scenario_resolve(str(raw_instance_id), run_id=run_id)
        if raw_instance_id
        else None
    )

    print(f"\n{'=' * 60}")
    print(f"Scenario : {name}")
    print(f"run_id   : {run_id}")
    if agent_instance_id:
        print(f"instance : {agent_instance_id}")
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
                agent_instance_id=agent_instance_id,
                user_id=user_id,
                team_id=team_id,
                run_id=run_id,
                step_id=step_id,
            )
        elif step_type == "hitl":
            _scenario_run_hitl(
                client,
                step,
                agent_id=agent_id,
                agent_instance_id=agent_instance_id,
                user_id=user_id,
                team_id=team_id,
                run_id=run_id,
                step_id=step_id,
            )
        else:
            raise ValueError(f"Unknown step type {step_type!r} in step {step_id!r}")
