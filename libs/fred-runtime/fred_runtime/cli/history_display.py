from __future__ import annotations

import json
from typing import Any

from fred_core.cli.ui import (
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_WHITE,
    ANSI_YELLOW,
    colorize,
)

from .pod_client import AgentPodClient

# Role → (display label, ANSI color)
_HISTORY_ROLE_STYLE: dict[str, tuple[str, str]] = {
    "user": ("You", ANSI_GREEN),
    "assistant": ("Assistant", ANSI_CYAN),
    "tool": ("Tool", ANSI_YELLOW),
    "system": ("System", ANSI_DIM),
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
    "hitl_request": "HITL gate",
    "hitl_response": "HITL reply",
}


def print_history(
    messages: list[dict[str, Any]],
    *,
    session_id: str,
    color_enabled: bool,
    raw: bool = False,
) -> None:
    """Render a conversation history to the terminal in a readable form."""
    header = colorize(
        f"  History — session {session_id} ({len(messages)} messages)",
        color=ANSI_DIM,
        enabled=color_enabled,
        bold=True,
    )
    print(header)
    print(colorize("  " + "─" * 60, color=ANSI_DIM, enabled=color_enabled))

    if raw:
        for msg in messages:
            rank = msg.get("rank", "?")
            print(
                colorize(
                    f"\n  ── message [{rank}] ──",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(json.dumps(msg, indent=2, ensure_ascii=False, default=str))
        print()
        return

    current_exchange: str | None = None

    for msg in messages:
        exchange_id: str = msg.get("exchange_id", "")
        if exchange_id and exchange_id != current_exchange:
            current_exchange = exchange_id
            print()

        rank = msg.get("rank", "?")
        role = msg.get("role", "unknown")
        channel = msg.get("channel", "final")

        label, role_color = _HISTORY_ROLE_STYLE.get(role, (role.capitalize(), ANSI_DIM))
        role_str = colorize(
            f"{label:<10}", color=role_color, enabled=color_enabled, bold=True
        )

        channel_suffix = ""
        if channel != "final":
            ch_label = _HISTORY_CHANNEL_LABELS.get(channel, channel)
            channel_suffix = colorize(
                f" [{ch_label}]", color=ANSI_DIM, enabled=color_enabled
            )

        rank_str = colorize(f"  [{rank:>3}]", color=ANSI_DIM, enabled=color_enabled)

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
            elif ptype == "hitl_request":
                title = part.get("title") or part.get("stage") or "HITL gate"
                question = part.get("question", "")
                choices: list[dict[str, Any]] = part.get("choices") or []

                def _dim(s: str) -> str:
                    return colorize(s, color=ANSI_DIM, enabled=color_enabled)

                def _bold_white(s: str) -> str:
                    return colorize(
                        s, color=ANSI_WHITE, enabled=color_enabled, bold=True
                    )

                box_width = 52
                top = (
                    _dim("┌─ ")
                    + _bold_white(title)
                    + _dim(" " + "─" * max(0, box_width - len(title) - 4) + "┐")
                )
                q_display = question[:68] + ("…" if len(question) > 68 else "")
                q_line = _dim("│ ") + q_display
                choice_lines = [
                    _dim("│  ")
                    + colorize(
                        f"{i + 1}.", color=ANSI_CYAN, enabled=color_enabled, bold=True
                    )
                    + f" {c.get('label', c.get('id', '?'))}  "
                    + _dim(f"[{c.get('id', '?')}]")
                    for i, c in enumerate(choices)
                ]
                bottom = _dim("└" + "─" * box_width + "┘")
                sep = "\n           "
                box = sep.join(["", top, q_line] + choice_lines + [bottom])
                lines.append(box)
            elif ptype == "hitl_response":
                choice_id = part.get("choice_id", "")
                label = part.get("label")
                if label:
                    check = colorize(
                        "✓", color=ANSI_GREEN, enabled=color_enabled, bold=True
                    )
                    label_str = colorize(
                        f" {label}", color=ANSI_GREEN, enabled=color_enabled
                    )
                    id_hint = colorize(
                        f"  [{choice_id}]", color=ANSI_DIM, enabled=color_enabled
                    )
                    lines.append(check + label_str + id_hint)
                else:
                    check = colorize(
                        "✓", color=ANSI_GREEN, enabled=color_enabled, bold=True
                    )
                    lines.append(check + f" {choice_id}")
            else:
                lines.append(f"[{ptype}]")

        content_str = (
            "\n           ".join(lines)
            if lines
            else colorize("(no content)", color=ANSI_DIM, enabled=color_enabled)
        )

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
                "  ".join(meta_parts), color=ANSI_DIM, enabled=color_enabled
            )

        print(f"{rank_str}  {role_str}{channel_suffix}  {content_str}{meta_str}")

    print()


def print_runtime_event(
    event: dict[str, Any],
    *,
    color_enabled: bool,
    saw_assistant_delta: bool,
) -> bool:
    """Render one streamed runtime event in a human-friendly terminal form."""
    if "error" in event:
        print(
            colorize(
                f"[error] {event['error']}",
                color=ANSI_RED,
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
                color=ANSI_DIM,
                enabled=color_enabled,
            )
        )
        return saw_assistant_delta
    if kind == "tool_call":
        tool_name = str(event.get("tool_name", "tool"))
        print(
            colorize(
                f"[tool] {tool_name}",
                color=ANSI_YELLOW,
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
        color = ANSI_RED if event.get("is_error") else ANSI_GREEN
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
                color=ANSI_BOLD,
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
                    f"  {colorize(str(i), color=ANSI_CYAN, enabled=color_enabled, bold=True)}. {label}"
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

    Returns (exit_code, hitl_request) where hitl_request is set when the agent
    is paused at a HITL gate, or None when the turn completed normally.
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
                    color=ANSI_RED,
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
    """
    selected_choice_id = raw_response
    if raw_response.isdigit():
        idx = int(raw_response) - 1
        if 0 <= idx < len(choices):
            selected_choice_id = str(choices[idx].get("id", raw_response))
    return {"choice_id": selected_choice_id}
