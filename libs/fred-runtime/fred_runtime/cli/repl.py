from __future__ import annotations

import getpass
import uuid
from typing import Any

import httpx
from fred_core.cli.auth import KeycloakUserSessionManager
from fred_core.cli.ui import (
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_WHITE,
    ANSI_YELLOW,
    colorize,
    install_readline_completion,
)

from .completion import completion_candidates
from .history_display import (
    build_hitl_resume_payload,
    print_history,
    run_eval_turn,
    run_single_turn,
)
from .kpi_display import parse_prometheus_text_exposition, render_kpi_report
from .pod_client import AgentPodClient
from .repl_helpers import (
    ExecutionMode,
    _ask_cli_help,
    execution_mode_color,
    execution_mode_label,
    fmt_bytes,
    parse_mode_command,
    print_help,
)


def run_interactive_chat(
    *,
    client: AgentPodClient,
    agent_id: str | None,
    session_id: str,
    user_id: str,
    team_id: str | None,
    verbose: bool,
    stream: bool,
    mode: ExecutionMode = "stream",
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

    # Mutable list — mutated in-place so the closure sees updates without reinstalling
    known_sessions: list[str] = []
    install_readline_completion(
        lambda line: completion_candidates(
            line, agent_ids=known_agents, session_ids=known_sessions
        )
    )

    print(
        f"Connected to {colorize(client.base_url, color=ANSI_DIM, enabled=color_enabled)}"
    )
    print(
        f"Current agent: {colorize(current_agent, color=ANSI_CYAN, enabled=color_enabled, bold=True)}"
    )
    print(
        "Mode: "
        f"{colorize(execution_mode_label(mode), color=execution_mode_color(mode), enabled=color_enabled, bold=True)}"
    )
    if auth_session is not None:
        print(
            "Auth: "
            f"{colorize(auth_session.describe(), color=ANSI_DIM, enabled=color_enabled)}"
        )
    if team_id:
        print(
            "Team: "
            f"{colorize(team_id, color=ANSI_GREEN, enabled=color_enabled, bold=True)}"
        )
    print(
        "Use /agents to list agents, /agent <id> to switch, "
        "/team <id> to set team scope, /kpi to inspect metrics, /quit to exit."
    )

    current_session_id = session_id
    current_mode: ExecutionMode = mode
    current_team_id = team_id
    while True:
        try:
            prompt = (
                f"{colorize(current_agent, color=ANSI_CYAN, enabled=color_enabled, bold=True)}"
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
                f"{colorize(auth_session.current_username() or 'unknown-user', color=ANSI_GREEN, enabled=color_enabled, bold=True)}"
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
                f"{colorize(auth_session.current_username() or username, color=ANSI_GREEN, enabled=color_enabled, bold=True)}"
            )
            continue
        if message == "/whoami":

            def _wfield(label: str, value: str, color: str) -> str:
                return colorize(
                    f"  {label:<10}", color=ANSI_DIM, enabled=color_enabled
                ) + colorize(value, color=color, enabled=color_enabled, bold=True)

            print(
                colorize("  Identity", color=ANSI_DIM, enabled=color_enabled, bold=True)
            )
            print(colorize("  " + "─" * 54, color=ANSI_DIM, enabled=color_enabled))
            print(_wfield("User:", user_id, ANSI_GREEN))
            if auth_session is None:
                print(_wfield("Auth:", "standalone (no authentication)", ANSI_DIM))
            else:
                print(_wfield("Auth:", auth_session.describe(), ANSI_GREEN))
            print(_wfield("Team:", current_team_id or "personal", ANSI_CYAN))
            print(_wfield("Agent:", current_agent, ANSI_CYAN))
            print(_wfield("Session:", current_session_id, ANSI_DIM))
            print(
                _wfield(
                    "Mode:",
                    execution_mode_label(current_mode),
                    execution_mode_color(current_mode),
                )
            )
            print(_wfield("Pod:", client.base_url, ANSI_DIM))
            if auth_session is None:
                print()
                print(
                    colorize(
                        "  ⚠  Standalone mode: history is stored under user_id = "
                        f'"{user_id}" (your Unix username).\n'
                        '     The local UI may send a different user_id (e.g. "admin").\n'
                        "     Override with: fred-agents-cli --user-id admin",
                        color=ANSI_YELLOW,
                        enabled=color_enabled,
                    )
                )
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
                    color=ANSI_CYAN if available_agent == current_agent else ANSI_DIM,
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
                    f"{colorize(execution_mode_label(current_mode), color=execution_mode_color(current_mode), enabled=color_enabled, bold=True)}"
                )
                continue
            current_mode = requested_mode
            print(
                "Switched to "
                f"{colorize(execution_mode_label(current_mode), color=execution_mode_color(current_mode), enabled=color_enabled, bold=True)} mode"
            )
            continue
        if message.startswith("/agent "):
            requested_agent = message.removeprefix("/agent ").strip()
            if requested_agent not in known_agents:
                print(f"Unknown agent_id: {requested_agent}")
                continue
            current_agent = requested_agent
            print(
                f"Switched to {colorize(current_agent, color=ANSI_CYAN, enabled=color_enabled, bold=True)}"
            )
            continue
        if message == "/session-new":
            current_session_id = f"dev-session-{uuid.uuid4().hex[:8]}"
            print(
                "New session: "
                + colorize(
                    current_session_id,
                    color=ANSI_CYAN,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            continue
        if message == "/session":
            print(
                "Current session: "
                + colorize(
                    current_session_id,
                    color=ANSI_CYAN,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(
                colorize(
                    "  /session <N>   switch by index from last /sessions list\n"
                    "  /session <id>  switch by exact session id\n"
                    "  /session-new   start a fresh session",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            continue
        if message.startswith("/session "):
            arg = message.removeprefix("/session ").strip()
            if arg.isdigit():
                idx = int(arg) - 1
                if known_sessions and 0 <= idx < len(known_sessions):
                    current_session_id = known_sessions[idx]
                    print(
                        "Switched to session "
                        + colorize(
                            f"[{idx + 1}] {current_session_id}",
                            color=ANSI_CYAN,
                            enabled=color_enabled,
                            bold=True,
                        )
                    )
                else:
                    total = len(known_sessions)
                    hint = (
                        f"valid range: 1–{total}"
                        if total
                        else "run /sessions first to load the list"
                    )
                    print(f"Index {arg!r} out of range ({hint}).")
            else:
                current_session_id = arg
                print(
                    "Session set to "
                    + colorize(
                        current_session_id,
                        color=ANSI_CYAN,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
            continue
        if message.startswith("/session-info"):
            target_sid = (
                message.removeprefix("/session-info").strip() or current_session_id
            )
            if not target_sid:
                print(
                    "No session active. Use /session <id> or /session-info <session_id>."
                )
                continue
            try:
                info_msgs = client.get_session_messages(target_sid)
            except Exception as exc:
                print(f"Error fetching session: {exc}")
                continue
            if not info_msgs:
                print(
                    colorize(
                        f"  Session {target_sid} has no stored messages.",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                continue

            timestamps = [
                m["timestamp"] for m in info_msgs if isinstance(m.get("timestamp"), str)
            ]
            created_at = min(timestamps) if timestamps else "unknown"
            updated_at = max(timestamps) if timestamps else "unknown"
            exchange_ids = {
                m.get("exchange_id", "") for m in info_msgs if m.get("exchange_id")
            }
            agents_used = sorted(
                {
                    m["metadata"]["agent_id"]
                    for m in info_msgs
                    if isinstance(m.get("metadata"), dict)
                    and m["metadata"].get("agent_id")
                }
            )
            models_used = sorted(
                {
                    m["metadata"]["model"]
                    for m in info_msgs
                    if isinstance(m.get("metadata"), dict)
                    and m["metadata"].get("model")
                }
            )
            total_input = sum(
                ((m.get("metadata") or {}).get("token_usage") or {}).get(
                    "input_tokens", 0
                )
                for m in info_msgs
                if isinstance(m.get("metadata"), dict)
            )
            total_output = sum(
                ((m.get("metadata") or {}).get("token_usage") or {}).get(
                    "output_tokens", 0
                )
                for m in info_msgs
                if isinstance(m.get("metadata"), dict)
            )
            hitl_count = sum(1 for m in info_msgs if m.get("channel") == "hitl_request")
            title = None
            for m in info_msgs:
                if m.get("role") == "user" and m.get("channel") == "final":
                    for p in m.get("parts") or []:
                        if p.get("type") == "text":
                            t = p.get("text", "").strip().replace("\n", " ")
                            title = (t[:72] + "…") if len(t) > 72 else t
                            break
                if title:
                    break

            def _ifield(label: str, value: str, color: str) -> str:
                return colorize(
                    f"  {label:<18}", color=ANSI_DIM, enabled=color_enabled
                ) + colorize(value, color=color, enabled=color_enabled, bold=True)

            print(
                colorize(
                    f"  Session info — {target_sid}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(colorize("  " + "─" * 60, color=ANSI_DIM, enabled=color_enabled))
            if title:
                print(_ifield("Title (first msg):", title, ANSI_WHITE))
            print(_ifield("Created:", created_at, ANSI_DIM))
            print(_ifield("Last activity:", updated_at, ANSI_DIM))
            print(_ifield("Exchanges:", str(len(exchange_ids)), ANSI_CYAN))
            print(_ifield("Messages:", str(len(info_msgs)), ANSI_DIM))
            if hitl_count:
                print(_ifield("HITL gates:", str(hitl_count), ANSI_YELLOW))
            if agents_used:
                print(_ifield("Agents used:", ", ".join(agents_used), ANSI_CYAN))
            if models_used:
                print(_ifield("Models used:", ", ".join(models_used), ANSI_DIM))
            if total_input or total_output:
                print(
                    _ifield(
                        "Tokens:",
                        f"{total_input}↑ in  {total_output}↓ out  "
                        f"({total_input + total_output} total)",
                        ANSI_DIM,
                    )
                )
            print()
            continue

        # ------------------------------------------------------------------
        # Destructive cleanup commands — all require explicit confirmation
        # ------------------------------------------------------------------

        if (
            message.startswith("/delete-session")
            or message.startswith("/delete-checkpoint")
            or message.startswith("/purge-session")
        ):
            if message.startswith("/purge-session"):
                cmd, do_history, do_checkpoint = "purge-session", True, True
            elif message.startswith("/delete-session"):
                cmd, do_history, do_checkpoint = "delete-session", True, False
            else:
                cmd, do_history, do_checkpoint = "delete-checkpoint", False, True

            target_sid = message.removeprefix(f"/{cmd}").strip() or current_session_id
            if not target_sid:
                print(f"Usage: /{cmd} [session_id]  (defaults to current session)")
                continue

            scope = []
            if do_history:
                scope.append("history rows")
            if do_checkpoint:
                scope.append("checkpoint state")
            scope_str = " + ".join(scope)
            warn = colorize(
                f"  ⚠  This will permanently delete {scope_str} for:\n"
                f"     {target_sid}\n"
                "     This cannot be undone.",
                color=ANSI_YELLOW,
                enabled=color_enabled,
            )
            print(warn)
            try:
                confirm = input("  Type 'yes' to confirm: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                continue
            if confirm != "yes":
                print("  Aborted.")
                continue

            errors: list[str] = []
            if do_history:
                try:
                    n = client.delete_session_messages(target_sid)
                    print(
                        colorize(
                            f"  History: deleted {n} row(s).",
                            color=ANSI_GREEN,
                            enabled=color_enabled,
                        )
                    )
                    if target_sid in known_sessions:
                        known_sessions.remove(target_sid)
                    if (
                        target_sid == current_session_id
                        and do_history
                        and not do_checkpoint
                    ):
                        print(
                            colorize(
                                "  Tip: use /session-new to start a fresh session.",
                                color=ANSI_DIM,
                                enabled=color_enabled,
                            )
                        )
                except Exception as exc:
                    errors.append(f"history: {exc}")
            if do_checkpoint:
                try:
                    client.delete_checkpoint(target_sid)
                    print(
                        colorize(
                            "  Checkpoint: purged.",
                            color=ANSI_GREEN,
                            enabled=color_enabled,
                        )
                    )
                except Exception as exc:
                    errors.append(f"checkpoint: {exc}")
            if errors:
                for err in errors:
                    print(
                        colorize(
                            f"  Error — {err}", color=ANSI_RED, enabled=color_enabled
                        )
                    )
            elif do_history and target_sid == current_session_id:
                print(
                    colorize(
                        "  Tip: use /session-new to start a fresh session.",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
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
                        color=ANSI_GREEN,
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
            known_sessions.clear()
            known_sessions.extend(sessions)
            if not sessions:
                print("  No sessions found for this user.")
            else:
                print(
                    colorize(
                        f"  Sessions for {user_id} ({len(sessions)} total):",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                print(colorize("  " + "─" * 60, color=ANSI_DIM, enabled=color_enabled))

                def _first_text(msgs: list[dict[str, Any]], role: str) -> str | None:
                    it = (
                        msgs if role == "user" else reversed(msgs)  # type: ignore[arg-type]
                    )
                    for m in it:
                        if m.get("role") == role and m.get("channel") == "final":
                            for p in m.get("parts") or []:
                                if p.get("type") == "text":
                                    t = p.get("text", "").strip()
                                    t = t.replace("\n", " ")
                                    return (t[:65] + "…") if len(t) > 65 else t
                    return None

                for i, sid in enumerate(sessions):
                    is_current = sid == current_session_id
                    marker = (
                        colorize(" ◀", color=ANSI_GREEN, enabled=color_enabled)
                        if is_current
                        else ""
                    )
                    try:
                        preview_msgs = client.get_session_messages(sid)
                    except Exception:
                        preview_msgs = []
                    msg_count = len(preview_msgs)
                    first_user = _first_text(preview_msgs, "user")
                    last_asst = _first_text(preview_msgs, "assistant")

                    sid_str = colorize(
                        sid,
                        color=ANSI_CYAN if is_current else ANSI_DIM,
                        enabled=color_enabled,
                        bold=is_current,
                    )
                    count_str = colorize(
                        f"({msg_count} msgs)",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                    print(f"\n  {i + 1:>3}.  {sid_str}  {count_str}{marker}")
                    if first_user:
                        print(
                            colorize(
                                "        You: ", color=ANSI_DIM, enabled=color_enabled
                            )
                            + f'"{first_user}"'
                        )
                    if last_asst:
                        print(
                            colorize(
                                "        Bot: ", color=ANSI_DIM, enabled=color_enabled
                            )
                            + colorize(
                                f'"{last_asst}"', color=ANSI_DIM, enabled=color_enabled
                            )
                        )
                print()
            continue
        if message.startswith("/history"):
            remainder = message.removeprefix("/history").strip()
            show_raw = "--raw" in remainder
            if show_raw:
                remainder = remainder.replace("--raw", "").strip()
            target_session = remainder or current_session_id
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
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
            else:
                print_history(
                    msgs,
                    session_id=target_session,
                    color_enabled=color_enabled,
                    raw=show_raw,
                )
            continue
        if message.startswith("/audit"):
            arg = message.removeprefix("/audit").strip()
            try:
                limit_audit = int(arg) if arg else 30
            except ValueError:
                limit_audit = 30
            try:
                events = client.get_audit_events(limit=limit_audit)
            except Exception as exc:
                print(f"Error fetching audit events: {exc}")
                continue
            if not events:
                print(
                    colorize(
                        "  No security audit events recorded since pod started.",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
            else:
                print(
                    colorize(
                        f"  Security audit events ({len(events)} shown):",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                for ev in events:
                    ev_name = ev.get("audit_event", "?")
                    ts = (ev.get("ts") or "-")[:19].replace("T", " ")
                    ev_color = (
                        ANSI_RED
                        if "mismatch" in ev_name or "failed" in ev_name
                        else ANSI_GREEN
                    )
                    parts = [
                        colorize(f"  {ts}", color=ANSI_DIM, enabled=color_enabled),
                        colorize(
                            f"  {ev_name:<28}", color=ev_color, enabled=color_enabled
                        ),
                    ]
                    for key in ("user_id", "agent_instance_id", "action", "reason"):
                        val = ev.get(key)
                        if val:
                            parts.append(
                                colorize(
                                    f"  {key}={val!r}",
                                    color=ANSI_DIM,
                                    enabled=color_enabled,
                                )
                            )
                    print("".join(parts))
            continue
        if message.startswith("/kpi"):
            arg = message.removeprefix("/kpi").strip()
            if arg.startswith("prom"):
                pattern = arg.removeprefix("prom").strip() or None
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
            try:
                limit_kpi = int(arg) if arg else 20
            except ValueError:
                limit_kpi = 20
            try:
                turns = client.get_kpi_turns(limit=limit_kpi)
            except Exception as exc:
                print(f"Error fetching KPI turns: {exc}")
                continue
            if not turns:
                print(
                    colorize(
                        "  No agent.turn_completed events since pod started.",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
            else:
                print(
                    colorize(
                        f"  Recent turns ({len(turns)} shown, /kpi prom [pattern] for Prometheus):",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                print(
                    colorize(
                        f"  {'Timestamp':<19}  {'ms':>6}  {'model':<20}  {'tools':>5}  {'in tok':>6}  {'out tok':>7}  {'status':<12}  session",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(colorize("  " + "─" * 100, color=ANSI_DIM, enabled=color_enabled))
                for t in turns:
                    ts = (t.get("ts") or "-")[:19].replace("T", " ")
                    total_ms = t.get("total_ms") or 0
                    model = str(t.get("model_name") or "-")[:20]
                    tool_count = t.get("tool_count") or 0
                    in_tok = t.get("input_tokens") or "-"
                    out_tok = t.get("output_tokens") or "-"
                    finish = str(t.get("finish_reason") or "ok")[:12]
                    session = str(t.get("session_id") or "-")[:36]
                    is_err = t.get("is_error", False)
                    row_color = ANSI_RED if is_err else ANSI_DIM
                    mark = (
                        current_session_id and t.get("session_id") == current_session_id
                    )
                    print(
                        colorize(f"  {ts}", color=ANSI_DIM, enabled=color_enabled)
                        + colorize(
                            f"  {total_ms:>6}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {model:<20}", color=row_color, enabled=color_enabled
                        )
                        + colorize(
                            f"  {tool_count:>5}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {str(in_tok):>6}",
                            color=ANSI_DIM,
                            enabled=color_enabled,
                        )
                        + colorize(
                            f"  {str(out_tok):>7}",
                            color=ANSI_DIM,
                            enabled=color_enabled,
                        )
                        + colorize(
                            f"  {finish:<12}", color=row_color, enabled=color_enabled
                        )
                        + colorize(
                            f"  {session}",
                            color=ANSI_CYAN if mark else ANSI_DIM,
                            enabled=color_enabled,
                        )
                        + (
                            colorize(" ◀", color=ANSI_GREEN, enabled=color_enabled)
                            if mark
                            else ""
                        )
                    )
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
                        color=ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                print(
                    colorize(
                        f"  {'Thread ID':<36}  {'CPs':>4}  {'Latest':<19}  {'cp struct':>9}  {'blobs':>5}  {'blob data':>9}  {'pend':>4}",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(colorize("  " + "─" * 96, color=ANSI_DIM, enabled=color_enabled))
                for t in threads:
                    sid = t.get("session_id", "?")
                    count = t.get("checkpoint_count", 0)
                    latest = (t.get("latest_created_at") or "-")[:19]
                    cp_bytes = fmt_bytes(t.get("checkpoint_bytes_total", 0))
                    blob_cnt = t.get("blob_count", 0)
                    blob_bytes = fmt_bytes(t.get("blob_bytes_total", 0))
                    pending = t.get("pending_write_count", 0)
                    marker = " ◀" if sid == current_session_id else ""
                    line_color = ANSI_CYAN if sid == current_session_id else ANSI_DIM
                    pending_color = ANSI_YELLOW if pending > 0 else ANSI_DIM
                    print(
                        colorize(
                            f"  {sid:<36}", color=line_color, enabled=color_enabled
                        )
                        + colorize(
                            f"  {count:>4}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {latest:<19}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {cp_bytes:>9}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {blob_cnt:>5}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {blob_bytes:>9}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {pending:>4}",
                            color=pending_color,
                            enabled=color_enabled,
                        )
                        + colorize(marker, color=ANSI_GREEN, enabled=color_enabled)
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
                        color=ANSI_DIM,
                        enabled=color_enabled,
                        bold=True,
                    )
                )
                print(
                    colorize(
                        f"  {'step':>4}  {'source':<7}  {'node(s)':<20}  {'cp struct':>9}  {'pend':>4}  {'checkpoint_id':<38}  created",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(colorize("  " + "─" * 110, color=ANSI_DIM, enabled=color_enabled))
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
                    pending_color = ANSI_YELLOW if pending > 0 else ANSI_DIM
                    print(
                        colorize(
                            f"  {step_str:>4}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {source:<7}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {node_str:<20}", color=ANSI_CYAN, enabled=color_enabled
                        )
                        + colorize(
                            f"  {cp_bytes:>9}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {pending:>4}",
                            color=pending_color,
                            enabled=color_enabled,
                        )
                        + colorize(
                            f"  {cp_id:<38}", color=ANSI_DIM, enabled=color_enabled
                        )
                        + colorize(
                            f"  {created}", color=ANSI_DIM, enabled=color_enabled
                        )
                    )
                print(
                    colorize(
                        "\n  Blob content (channel states) is shared across checkpoints at thread level.",
                        color=ANSI_DIM,
                        enabled=color_enabled,
                    )
                )
                print(
                    colorize(
                        "  Use /checkpoints to see total blob size for this thread.",
                        color=ANSI_DIM,
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
            pending_color = ANSI_YELLOW if pending > 0 else ANSI_DIM
            print(
                colorize(
                    "  Checkpoint storage stats:",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(colorize("  " + "─" * 50, color=ANSI_DIM, enabled=color_enabled))
            print(
                colorize(
                    f"  Threads:              {stats.get('thread_count', 0):>6}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    f"  Checkpoints:          {stats.get('checkpoint_count', 0):>6}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  (pointer structs: {cp_bytes})",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    f"  Blob rows (channels): {stats.get('blob_count', 0):>6}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  (channel states:  {blob_bytes})",
                    color=ANSI_DIM,
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
                        color=ANSI_YELLOW,
                        enabled=color_enabled,
                    )
                    if pending > 0
                    else ""
                )
            )
            print(colorize("  " + "─" * 50, color=ANSI_DIM, enabled=color_enabled))
            print(
                colorize(
                    f"  Total storage approx: {total_bytes}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(
                colorize(
                    "\n  Note: blob rows are deduplicated by (channel, version) within a thread.",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    "  Blob data dominates cost and grows with total conversation turns.",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )
            continue
        if message in {"/context", "/execution-context"}:
            print(
                colorize(
                    "  Execution context summary:",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                    bold=True,
                )
            )
            print(colorize("  " + "─" * 50, color=ANSI_DIM, enabled=color_enabled))
            agent_label = colorize(
                current_agent, color=ANSI_CYAN, enabled=color_enabled, bold=True
            )
            session_label = (
                colorize(current_session_id, color=ANSI_GREEN, enabled=color_enabled)
                if current_session_id
                else colorize("none", color=ANSI_YELLOW, enabled=color_enabled)
            )
            mode_label = colorize(
                execution_mode_label(current_mode),
                color=execution_mode_color(current_mode),
                enabled=color_enabled,
                bold=True,
            )
            user_label = colorize(
                user_id or "anonymous", color=ANSI_DIM, enabled=color_enabled
            )
            auth_label = (
                colorize(auth_session.describe(), color=ANSI_DIM, enabled=color_enabled)
                if auth_session is not None
                else colorize("not configured", color=ANSI_DIM, enabled=color_enabled)
            )
            print(f"  Agent:    {agent_label}")
            print(f"  Session:  {session_label}")
            print(f"  User:     {user_label}")
            print(
                "  Team:     "
                + (
                    colorize(
                        current_team_id,
                        color=ANSI_GREEN,
                        enabled=color_enabled,
                    )
                    if current_team_id
                    else colorize("none", color=ANSI_YELLOW, enabled=color_enabled)
                )
            )
            print(f"  Mode:     {mode_label}")
            print(f"  Auth:     {auth_label}")
            print(
                f"  Pod URL:  {colorize(client.base_url, color=ANSI_DIM, enabled=color_enabled)}"
            )
            print(
                "  Metrics:  "
                + colorize(
                    client.metrics_url or "not configured",
                    color=ANSI_DIM if client.metrics_url else ANSI_YELLOW,
                    enabled=color_enabled,
                )
            )
            print(
                colorize(
                    "\n  Note: execution_grant is issued by control-plane for production runs.",
                    color=ANSI_DIM,
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

        if current_mode == "eval":
            exit_code = run_eval_turn(
                client=client,
                agent_id=current_agent,
                message=message,
                session_id=current_session_id,
                user_id=user_id,
                team_id=current_team_id,
                color_enabled=color_enabled,
            )
        else:
            exit_code, hitl = run_single_turn(
                client=client,
                agent_id=current_agent,
                message=message,
                session_id=current_session_id,
                user_id=user_id,
                team_id=current_team_id,
                verbose=verbose,
                stream=(current_mode == "stream"),
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
                    stream=(current_mode == "stream"),
                    color_enabled=color_enabled,
                    resume_payload=resume_value,
                )
        if exit_code != 0:
            print("The request failed. Use /help for commands or try another agent.")
