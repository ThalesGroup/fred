#!/usr/bin/env python3
"""Run one turn against a managed agent instance and report what it did.

Posts to /agents/execute/stream with `agent_instance_id` + `runtime_context.team_id`,
prints a timestamped event trace, and summarises any tool fan-out. Writes the raw
events and the final answer to files so a large answer never floods the caller.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from fred_core.cli.auth import (
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    build_cli_token_provider,
    default_keycloak_token_file,
)
from fred_runtime.cli.pod_client import AgentPodClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instance", required=True, help="agent_instance_id to execute")
    p.add_argument("--team", required=True, help="team_id owning the instance")
    p.add_argument("--message", help="turn text; omit to read stdin")
    p.add_argument("--session", default=None, help="session id (default: a fresh uuid4)")
    p.add_argument("--title", default="Agent instance test", help="session title in the UI")
    p.add_argument("--out-dir", default="./agent-turn", help="where events.jsonl and final.md land")
    p.add_argument("--fanout-tool", default="run_subagent", help="tool to summarise per call")
    p.add_argument("--head", type=int, default=2000, help="chars of the final answer to print")
    p.add_argument("--pod-url", default=os.getenv("POD_BASE_URL", "http://127.0.0.1:8000/fred/agents/v2"))
    p.add_argument("--control-plane-url", default=os.getenv("CONTROL_PLANE_URL", "http://localhost:9996/control-plane/v1"))
    p.add_argument("--realm-url", default=os.getenv("FRED_REALM_URL", "http://localhost:8080/realms/app"))
    p.add_argument("--client-id", default=os.getenv("FRED_CLIENT_ID", "app"))
    p.add_argument("--username", default=os.getenv("FRED_USERNAME"))
    p.add_argument("--password", default=os.getenv("FRED_PASSWORD"))
    p.add_argument(
        "--no-register",
        action="store_true",
        help="skip control-plane session creation (the turn then runs but stays invisible in the UI)",
    )
    return p.parse_args()


def claims(token: str) -> dict:
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def short(value: object, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return (t := " ".join(text.split()))[:limit] + ("…" if len(t) > limit else "")


def main() -> int:
    args = parse_args()
    session = args.session or str(uuid.uuid4())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path, final_path = out_dir / "events.jsonl", out_dir / "final.md"

    auth = KeycloakUserSessionManager(
        config=KeycloakLoginConfig(realm_url=args.realm_url, client_id=args.client_id),
        cache_file=default_keycloak_token_file(),
        log_prefix="[cli]",
    )
    if args.username and args.password:
        auth.login(username=args.username, password=args.password)
    token = auth.get_access_token()
    if not token:
        return exit_with(
            "no usable token. Pass --username/--password (or FRED_USERNAME/FRED_PASSWORD), "
            "or cache a session with `fred-agents-cli --login`."
        )

    user_id = claims(token)["sub"]
    print(f"[cli] identity  : {auth.current_username()}  sub={user_id}")
    print(f"[cli] instance  : {args.instance}  team={args.team}")
    print(f"[cli] session   : {session}")
    print(f"[cli] out       : {out_dir}")

    # The runtime writes session_history; session_metadata belongs to the control
    # plane and is what the UI's session list reads. Without this the turn runs
    # correctly and is simply invisible in the frontend.
    if not args.no_register:
        r = httpx.post(
            f"{args.control_plane_url}/teams/{args.team}/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_id": session, "agent_instance_id": args.instance, "title": args.title},
            timeout=10.0,
        )
        print(f"[cli] register  : control-plane session -> {r.status_code}")
        if r.status_code >= 400:
            print(f"[cli] register  : {r.text[:300]}")
    print(flush=True)

    client = AgentPodClient(
        base_url=args.pod_url,
        http_client=httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0, read=None)),
        token_provider=build_cli_token_provider(
            auth_session=auth, static_token=None, log_prefix="[cli]"
        ),
    )

    message = args.message if args.message is not None else sys.stdin.read()
    started = time.monotonic()
    calls: dict[str, dict] = {}
    batches: list[list[str]] = []
    in_flight: set[str] = set()
    peak = 0
    final_text = ""
    error: str | None = None

    with trace_path.open("w", encoding="utf-8") as trace:
        for event in client.iter_stream_events(
            agent_id=None,  # type: ignore[arg-type]
            agent_instance_id=args.instance,
            message=message,
            session_id=session,
            user_id=user_id,
            team_id=args.team,
        ):
            now = time.monotonic() - started
            trace.write(json.dumps(event, ensure_ascii=False) + "\n")
            trace.flush()
            kind = event.get("kind")

            if kind == "tool_call":
                call_id, name = event["call_id"], event["tool_name"]
                calls[call_id] = {"name": name, "at": now, "args": event.get("arguments", {})}
                if name == args.fanout_tool:
                    # A batch is the run of calls issued while none is outstanding,
                    # so a true parallel fan-out lands as one batch of N.
                    if not in_flight:
                        batches.append([])
                    batches[-1].append(call_id)
                    in_flight.add(call_id)
                    peak = max(peak, len(in_flight))
                print(f"[{now:7.1f}s] → {name}  {short(event.get('arguments', {}))}", flush=True)

            elif kind == "tool_result":
                rec = calls.get(event["call_id"], {})
                rec["done"], rec["error"] = now, bool(event.get("is_error"))
                rec["chars"] = len(event.get("content") or "")
                in_flight.discard(event["call_id"])
                flag = "ERR" if rec.get("error") else "ok "
                print(
                    f"[{now:7.1f}s] ← {rec.get('name', event.get('tool_name'))} {flag} "
                    f"{rec['chars']} chars  {short(event.get('content', ''), 100)}",
                    flush=True,
                )

            elif kind == "thought_end" and event.get("conclusion"):
                print(f"[{now:7.1f}s] ~ thought: {short(event['conclusion'])}", flush=True)

            elif kind == "status":
                print(f"[{now:7.1f}s] · {event.get('status')} {event.get('detail') or ''}", flush=True)

            elif kind == "final":
                final_text = event.get("content", "")
                usage = event.get("token_usage") or {}
                print(
                    f"[{now:7.1f}s] ✓ final ({len(final_text)} chars, "
                    f"finish_reason={event.get('finish_reason')}, "
                    f"in={usage.get('input_tokens')} out={usage.get('output_tokens')})",
                    flush=True,
                )

            elif kind in {"execution_error", "node_error"}:
                error = short(event, 400)
                print(f"[{now:7.1f}s] ✗ {kind}: {error}", flush=True)

    final_path.write_text(final_text, encoding="utf-8")
    report(args, calls, batches, peak, time.monotonic() - started, error, final_text, final_path)
    return 1 if error else 0


def exit_with(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def report(args, calls, batches, peak, elapsed, error, final_text, final_path) -> None:
    fanout = {cid: r for cid, r in calls.items() if r["name"] == args.fanout_tool}
    print("\n" + "=" * 72)
    print("TURN REPORT")
    print("=" * 72)
    print(f"wall clock          : {elapsed:.1f}s")
    print(f"tool calls total    : {len(calls)}")
    print(f"{args.fanout_tool} calls : {len(fanout)}")
    if fanout:
        print(f"peak concurrent     : {peak}")
        print(f"batches             : {[len(b) for b in batches]}  (a parallel fan-out is one batch)")
        errs = sum(1 for r in fanout.values() if r.get("error"))
        print(f"completed / errored : {sum(1 for r in fanout.values() if 'done' in r)} / {errs}")
        print("\nper child:")
        for i, rec in enumerate(fanout.values(), 1):
            dur = f"{rec['done'] - rec['at']:6.1f}s" if "done" in rec else "  n/a "
            state = "ERR" if rec.get("error") else "ok "
            print(f"  {i:2}. {state} {dur} {rec.get('chars', 0):6} chars  {short(rec['args'], 110)}")
    if error:
        print(f"\nERROR: {error}")
    print(f"\nfinal answer        : {len(final_text)} chars -> {final_path}")
    print("-" * 72)
    print(final_text[: args.head])
    if len(final_text) > args.head:
        print(f"\n… truncated, read {final_path} for the rest")


if __name__ == "__main__":
    raise SystemExit(main())
