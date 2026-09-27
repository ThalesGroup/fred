#!/usr/bin/env python3
"""Capture one managed-instance turn using existing Fred CLI authentication.

Decoded SSE payloads, the authoritative final answer and an evidence summary are
written to a new private directory. Use --help for local endpoint overrides.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

import httpx
from fred_core.cli.auth import (
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    build_cli_token_provider,
    default_keycloak_token_file,
)
from fred_runtime.cli.pod_client import AgentPodClient

# SSE payloads are open dictionaries supplied by the existing CLI client.
Event = dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--team", required=True)
    parser.add_argument("--message", help="omit to read stdin")
    parser.add_argument(
        "--session", help="existing session; otherwise create a fresh one"
    )
    parser.add_argument("--title", default="Agent instance test")
    parser.add_argument("--out-dir", required=True, help="new private output directory")
    parser.add_argument("--fanout-tool", default="task")
    parser.add_argument(
        "--pod-url",
        default=os.getenv("POD_BASE_URL", "http://127.0.0.1:8000/fred/agents/v2"),
    )
    parser.add_argument(
        "--control-plane-url",
        default=os.getenv(
            "CONTROL_PLANE_URL", "http://localhost:9996/control-plane/v1"
        ),
    )
    parser.add_argument(
        "--realm-url",
        default=os.getenv("FRED_REALM_URL", "http://localhost:8080/realms/app"),
    )
    parser.add_argument("--client-id", default=os.getenv("FRED_CLIENT_ID", "app"))
    parser.add_argument("--username", default=os.getenv("FRED_USERNAME"))
    parser.add_argument(
        "--read-timeout", type=float, default=300, help="maximum idle stream seconds"
    )
    return parser.parse_args()


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def redact_event(value: Any, secrets: Iterable[str]) -> Any:
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {
            redact(str(key), secrets): redact_event(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_event(item, secrets) for item in value]
    return value


def write_private(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8") as output:
        os.chmod(path, 0o600)
        output.write(content)


def capture(
    events: Iterable[Event], out_dir: Path, fanout_tool: str, secrets: list[str]
) -> int:
    started = time.monotonic()
    calls: dict[str, Event] = {}
    pending: set[str] = set()
    peak = 0
    final: Event | None = None
    errors: list[str] = []
    awaiting_human = False
    with (out_dir / "events.jsonl").open("x", encoding="utf-8") as trace:
        os.chmod(trace.name, 0o600)
        try:
            for event in events:
                trace.write(
                    json.dumps(redact_event(event, secrets), ensure_ascii=False) + "\n"
                )
                trace.flush()
                kind = event.get("kind")
                call_id = event.get("call_id")
                if kind == "tool_call" and call_id:
                    calls[call_id] = {
                        "tool_name": event.get("tool_name"),
                        "completed": False,
                    }
                    if event.get("tool_name") == fanout_tool:
                        pending.add(call_id)
                        peak = max(peak, len(pending))
                elif kind == "tool_result" and call_id:
                    record = calls.setdefault(
                        call_id, {"tool_name": event.get("tool_name")}
                    )
                    record.update(completed=True, is_error=bool(event.get("is_error")))
                    pending.discard(call_id)
                elif kind == "final":
                    final = event
                elif kind in {"execution_error", "node_error"}:
                    errors.append(str(kind))
                elif kind == "awaiting_human":
                    awaiting_human = True
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            # Exception text can include headers, response bodies or credentials.
            errors.append(type(exc).__name__)
        finally:
            text = str(final.get("content") or "") if final is not None else ""
            write_private(out_dir / "final.md", redact(text, secrets))
            summary = {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "final_received": final is not None,
                "final_chars": len(text),
                "finish_reason": final.get("finish_reason") if final else None,
                "token_usage": final.get("token_usage") if final else None,
                "awaiting_human": awaiting_human,
                "errors": errors,
                "observed_calls": calls,
                "fanout_tool": fanout_tool,
                "peak_outstanding_observed_calls": peak,
                "limitation": "Outstanding SSE calls do not prove simultaneous execution or complete child visibility.",
            }
            write_private(
                out_dir / "summary.json",
                json.dumps(redact_event(summary, secrets), indent=2),
            )
    print(
        f"Captured {len(calls)} tool calls; final_received={final is not None}; errors={len(errors)}"
    )
    return 0 if final is not None and not errors and not awaiting_human else 1


def main() -> int:
    args = parse_args()
    message = args.message if args.message is not None else sys.stdin.read()
    if not message.strip() or args.read_timeout <= 0:
        print("Provide a nonempty message and positive read timeout.", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    # Exclusive creation prevents mixing evidence or following existing artifact symlinks.
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    session = args.session or str(uuid.uuid4())
    password = os.getenv("FRED_PASSWORD")
    auth = KeycloakUserSessionManager(
        config=KeycloakLoginConfig(realm_url=args.realm_url, client_id=args.client_id),
        cache_file=default_keycloak_token_file(),
        log_prefix="[cli]",
    )
    try:
        if args.username and password:
            with contextlib.redirect_stdout(io.StringIO()):
                auth.login(username=args.username, password=password)
        elif args.username and auth.current_username() != args.username:
            raise ValueError("Cached identity mismatch")
        provider = build_cli_token_provider(
            auth_session=auth, static_token=None, log_prefix="[cli]"
        )
        with contextlib.redirect_stdout(io.StringIO()):
            token = provider()
        if not token:
            print(
                "Log in with fred-agents-cli --login or set FRED_USERNAME and FRED_PASSWORD.",
                file=sys.stderr,
            )
            return 2
        secrets = [token, password or ""]
        body = token.split(".")[1]
        user_id = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))[
            "sub"
        ]
        with httpx.Client(
            timeout=httpx.Timeout(args.read_timeout, connect=5.0)
        ) as http:
            headers = {"Authorization": f"Bearer {token}"}
            if args.session:
                response = http.get(
                    f"{args.control_plane_url}/teams/{args.team}/sessions/{session}",
                    headers=headers,
                )
                response.raise_for_status()
                if response.json().get("agent_instance_id") != args.instance:
                    raise ValueError("Session instance mismatch")
            else:
                response = http.post(
                    f"{args.control_plane_url}/teams/{args.team}/sessions",
                    headers=headers,
                    json={
                        "session_id": session,
                        "agent_instance_id": args.instance,
                        "title": args.title,
                    },
                )
                response.raise_for_status()
            write_private(
                out_dir / "run.json",
                json.dumps(
                    {
                        "session_id": session,
                        "team_id": args.team,
                        "agent_instance_id": args.instance,
                    }
                ),
            )

            def current_token() -> str | None:
                with contextlib.redirect_stdout(io.StringIO()):
                    refreshed = provider()
                if refreshed:
                    secrets.append(refreshed)
                return refreshed

            client = AgentPodClient(
                base_url=args.pod_url, http_client=http, token_provider=current_token
            )
            events = client.iter_stream_events(
                agent_id=None,  # type: ignore[arg-type]  # Exactly one execution identity is required.
                agent_instance_id=args.instance,
                message=message,
                session_id=session,
                user_id=user_id,
                team_id=args.team,
            )
            return capture(events, out_dir, args.fanout_tool, secrets)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, RuntimeError) as exc:
        print(
            f"Setup failed ({type(exc).__name__}); check local endpoints, identity and instance/team.",
            file=sys.stderr,
        )
        return 2
    finally:
        auth.close()


if __name__ == "__main__":
    raise SystemExit(main())
