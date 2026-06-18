#!/usr/bin/env python3
"""
Seed fake agent KPI events into OpenSearch for dashboard testing.

Generates:
  • agent.created_total / agent.deleted_total  (always paired so agents_total
    KPI stays neutral) whose system_prompt_chars follow this distribution:

        0–499     : 260 agents  (avg 121)
        500–999   : 108 agents  (avg 832)
        1000–1999 :  75 agents  (avg 1565)
        2000–4999 : 155 agents  (avg 3407)
        5000–9999 :  74 agents  (avg 6470)
        10000+    :  23 agents  (avg 19163)

  • agent.turn_completed  events for top_agents_by_conversations, mimicking:

        Logos              195 turns/month
        Lux                163
        Jarvis             122
        RhinBOT             68
        Lumi Compagnon      45
        T360 Genius         22
        XX                  20
        Buggy               18
        Puitlogs            18
        Best CV agent       18
        Test                18
        test                16
        Cristiano RONALDO   15
        T360 Genius v2      14
        Appel d'offre       13
        Coach Slides STBY   13
        Sapiens             12
        DEV-BOT             12
        X                   12
        Stratégie           12

Events are spread across the last 90 days.

Usage:
    python scripts/seed_agent_kpi.py
    python scripts/seed_agent_kpi.py --since-days 180
    python scripts/seed_agent_kpi.py --dry-run
    python scripts/seed_agent_kpi.py --clear   # delete all seeded docs first
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://localhost:9200")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "Azerty123_")
KPI_INDEX = "kpi-index"

SEED_LABEL = "seed:agent_kpi"  # label added to every seeded doc for easy cleanup

TARGET_DISTRIBUTION = [
    # (count, min_chars, max_chars, avg_chars_hint)
    (260,  1,     477,   121),
    (108,  526,   941,   832),
    ( 75,  1063,  1986,  1565),
    (155,  2014,  4990,  3407),
    ( 74,  5043,  9112,  6470),
    ( 23,  10081, 73826, 19163),
]

TEMPLATE_IDS = [
    "fred-agents:fred.general_assistant",
    "fred-agents:fred.rag_expert",
    "fred-agents:fred.sql_expert",
    "fred-agents:fred.sentinel",
    "fred-agents:fred.react_rag_mcp",
]

TEAM_IDS = [
    "team-alpha",
    "team-beta",
    "team-gamma",
    "personal-demo-user",
]

USER_IDS = [
    "user-aa11",
    "user-bb22",
    "user-cc33",
    "user-dd44",
]

RUNTIME_ID = "fred-agents"

# Target distribution for top_agents_by_conversations (turns per 30 days).
# Scaled proportionally when --since-days differs from 30.
CONVERSATION_DISTRIBUTION = [
    # (agent_name, turns_per_month)
    ("Athena",             195),
    ("Nexus",              163),
    ("Orion",              122),
    ("DataForge",           68),
    ("Aria Assistant",      45),
    ("Sentinel Pro",        22),
    ("CodeCraft",           20),
    ("Meridian",            18),
    ("PulseBot",            18),
    ("Luminary",            18),
    ("QueryMind",           18),
    ("Vega",                16),
    ("Helios",              15),
    ("Aether",              14),
    ("NovaMind",            13),
    ("Synapse",             13),
    ("Cognito",             12),
    ("Apex Agent",          12),
    ("Zephyr",              12),
    ("Eclipse",             12),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req(method: str, path: str, body: Any = None) -> Any:
    """Minimal HTTPS request to OpenSearch (no extra deps required)."""
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    creds = f"{OPENSEARCH_USER}:{OPENSEARCH_PASSWORD}"
    import base64
    auth = base64.b64encode(creds.encode()).decode()

    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    req = urllib.request.Request(
        OPENSEARCH_URL + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode()
        print(f"[ERROR] {method} {path} → {e.code}: {body_txt[:300]}", file=sys.stderr)
        raise


def _bulk_index(docs: list[dict[str, Any]]) -> None:
    """POST a bulk request — each entry is (action_meta, source)."""
    lines = []
    for doc in docs:
        lines.append(json.dumps({"index": {"_index": KPI_INDEX}}))
        lines.append(json.dumps(doc))
    payload = "\n".join(lines) + "\n"

    import ssl, base64
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    creds = f"{OPENSEARCH_USER}:{OPENSEARCH_PASSWORD}"
    auth = base64.b64encode(creds.encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-ndjson",
    }
    data = payload.encode()
    req = urllib.request.Request(
        OPENSEARCH_URL + "/_bulk", data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, context=ctx) as resp:
        result = json.loads(resp.read())
        errors = [i for i in result.get("items", []) if "error" in i.get("index", {})]
        if errors:
            print(f"[WARN] {len(errors)} bulk errors", file=sys.stderr)


def _rand_ts(since: datetime, until: datetime) -> datetime:
    delta = (until - since).total_seconds()
    return since + timedelta(seconds=random.uniform(0, delta))


def _sample_chars(min_c: int, max_c: int, avg_hint: int) -> int:
    """Sample a value that skews toward avg_hint within [min_c, max_c]."""
    # Use a triangular distribution peaking at avg_hint for a realistic shape.
    val = random.triangular(min_c, max_c, avg_hint)
    return max(min_c, min(max_c, round(val)))


def _make_created_event(
    agent_id: str,
    ts: datetime,
    team_id: str,
    user_id: str,
    template_id: str,
    system_prompt_chars: int,
) -> dict[str, Any]:
    return {
        "@timestamp": ts.isoformat(),
        "metric": {"name": "agent.created_total", "type": "counter", "unit": "count", "value": 1.0},
        "dims": {
            "service": "control-plane",
            "team_id": team_id,
            "template_id": template_id,
            "source_runtime_id": RUNTIME_ID,
            "agent_instance_id": agent_id,
            "system_prompt_chars": str(system_prompt_chars),
            "actor_type": "human",
            "user_id": user_id,
        },
        "labels": [SEED_LABEL],
    }


def _make_deleted_event(
    agent_id: str,
    ts: datetime,
    team_id: str,
    user_id: str,
) -> dict[str, Any]:
    return {
        "@timestamp": ts.isoformat(),
        "metric": {"name": "agent.deleted_total", "type": "counter", "unit": "count", "value": 1.0},
        "dims": {
            "service": "control-plane",
            "team_id": team_id,
            "agent_instance_id": agent_id,
            "actor_type": "human",
            "user_id": user_id,
        },
        "labels": [SEED_LABEL],
    }


def _make_turn_event(
    agent_id: str,
    agent_name: str,
    ts: datetime,
    team_id: str,
    user_id: str,
) -> dict[str, Any]:
    return {
        "@timestamp": ts.isoformat(),
        "metric": {"name": "agent.turn_completed", "type": "counter", "unit": "count", "value": 1.0},
        "dims": {
            "service": "control-plane",
            "team_id": team_id,
            "agent_instance_id": agent_id,
            "agent_instance_name": agent_name,
            "actor_type": "human",
            "user_id": user_id,
        },
        "labels": [SEED_LABEL],
    }


def build_conversation_events(since_days: int) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=since_days)
    scale = since_days / 30.0

    events: list[dict[str, Any]] = []

    for agent_name, turns_per_month in CONVERSATION_DISTRIBUTION:
        agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"seed-agent-{agent_name}"))
        turn_count = max(1, round(turns_per_month * scale))
        team_id = random.choice(TEAM_IDS)

        for _ in range(turn_count):
            ts = _rand_ts(window_start, now)
            user_id = random.choice(USER_IDS)
            events.append(_make_turn_event(agent_id, agent_name, ts, team_id, user_id))

    return events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_events(since_days: int, delete_pct: float) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=since_days)

    # Some agents are created before the window to test the "alive but old" logic.
    very_old_start = now - timedelta(days=since_days * 2)

    events: list[dict[str, Any]] = []

    for count, min_c, max_c, avg_hint in TARGET_DISTRIBUTION:
        for _ in range(count):
            agent_id = str(uuid.uuid4())
            team_id = random.choice(TEAM_IDS)
            user_id = random.choice(USER_IDS)
            template_id = random.choice(TEMPLATE_IDS)
            chars = _sample_chars(min_c, max_c, avg_hint)

            # 20 % of agents are created before the window (should still appear).
            if random.random() < 0.20:
                created_ts = _rand_ts(very_old_start, window_start)
            else:
                created_ts = _rand_ts(window_start, now)

            events.append(_make_created_event(agent_id, created_ts, team_id, user_id, template_id, chars))

            # Some agents get updated (prompt may change).
            if random.random() < 0.30 and created_ts < now - timedelta(days=1):
                updated_chars = _sample_chars(min_c, max_c, avg_hint)
                updated_ts = _rand_ts(created_ts + timedelta(hours=1), now)
                events.append({
                    "@timestamp": updated_ts.isoformat(),
                    "metric": {"name": "agent.updated", "type": "counter", "unit": "count", "value": 1.0},
                    "dims": {
                        "service": "control-plane",
                        "team_id": team_id,
                        "agent_instance_id": agent_id,
                        "system_prompt_chars": str(updated_chars),
                        "actor_type": "human",
                        "user_id": user_id,
                    },
                    "labels": [SEED_LABEL],
                })

            # Always emit a paired delete so seeded agents never affect agents_total KPI.
            deleted_ts = created_ts + timedelta(seconds=random.randint(60, 3600))
            events.append(_make_deleted_event(agent_id, deleted_ts, team_id, user_id))

    return events


def clear_seeded(dry_run: bool) -> None:
    print(f"Deleting all documents with label '{SEED_LABEL}' from {KPI_INDEX}…")
    body = {"query": {"term": {"labels": SEED_LABEL}}}
    if dry_run:
        result = _req("POST", f"/{KPI_INDEX}/_count", body)
        print(f"[dry-run] would delete {result['count']} documents")
    else:
        result = _req("POST", f"/{KPI_INDEX}/_delete_by_query", body)
        print(f"Deleted {result.get('deleted', 0)} documents.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since-days", type=int, default=90, help="Spread events over this many days (default: 90)")
    parser.add_argument("--dry-run", action="store_true", help="Print event count without indexing")
    parser.add_argument("--clear", action="store_true", help="Delete previously seeded docs and exit")
    args = parser.parse_args()

    if args.clear:
        clear_seeded(dry_run=args.dry_run)
        return

    lifecycle_events = build_events(since_days=args.since_days, delete_pct=0.15)
    convo_events = build_conversation_events(since_days=args.since_days)
    events = lifecycle_events + convo_events

    agent_total = sum(c for c, *_ in TARGET_DISTRIBUTION)
    print(f"Generated {len(events)} total events:")
    print(f"  Lifecycle ({agent_total} agents, all paired with delete):")
    print(f"    • {sum(1 for e in lifecycle_events if e['metric']['name'] == 'agent.created_total')} created")
    print(f"    • {sum(1 for e in lifecycle_events if e['metric']['name'] == 'agent.updated')} updated")
    print(f"    • {sum(1 for e in lifecycle_events if e['metric']['name'] == 'agent.deleted_total')} deleted")
    print(f"  Conversations ({len(CONVERSATION_DISTRIBUTION)} agents):")
    print(f"    • {len(convo_events)} agent.turn_completed events")

    if args.dry_run:
        print("[dry-run] skipping indexing")
        return

    # Bulk index in chunks of 500.
    chunk_size = 500
    for i in range(0, len(events), chunk_size):
        chunk = events[i : i + chunk_size]
        _bulk_index(chunk)
        print(f"  indexed {min(i + chunk_size, len(events))}/{len(events)}", end="\r")

    print()
    _req("POST", f"/{KPI_INDEX}/_refresh")
    print("Done. Index refreshed.")


if __name__ == "__main__":
    main()
