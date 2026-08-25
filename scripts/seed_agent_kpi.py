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

  • a conversation population (see below) which emits, per conversation, one
    session.created_total and N agent.turn_completed sharing one session_id —
    plus a paired agent.turn_error_total for the few turns that "failed".

Conversation model
------------------
There is a single conversation population, so the same turns feed
`top_agents_by_conversations`, `messages_over_time`, `conversation_depth` and
`conversations_per_user` instead of two disjoint turn sets:

    per-agent turn budget (CONVERSATION_DISTRIBUTION, scaled by --since-days)
      → carved into conversations, each one's length drawn from
        CONVERSATION_LENGTH_DISTRIBUTION
      → the resulting conversations are dealt to a long-tail user population
        drawn from USER_ACTIVITY_DISTRIBUTION
      → each conversation emits 1 session.created_total (control-plane dims)
        + N agent.turn_completed (runtime dims, same session_id)

Trade-off: per-agent turn totals stay exact — the budget is carved, never
exceeded — so `top_agents_by_conversations` keeps showing the table below.
The price is that the *last* conversation carved out of each agent's budget is
truncated to whatever the budget has left, i.e. at most 20 conversations out of
~450 are shorter than drawn. That is invisible in the length histogram.

Turn budget per agent (turns / 30 days, scaled by --since-days):

        Athena             195 turns/month
        Nexus              163
        Orion              122
        DataForge           68
        Aria Assistant      45
        Sentinel Pro        22
        CodeCraft           20
        Meridian            18
        PulseBot            18
        Luminary            18
        QueryMind           18
        Vega                16
        Helios              15
        Aether              14
        NovaMind            13
        Synapse             13
        Cognito             12
        Apex Agent          12
        Zephyr              12
        Eclipse             12

Conversation length — turns per conversation (`conversation_depth`):

        1 turn      : 40 %   (one-shots)
        2–5 turns   : 30 %
        6–10 turns  : 15 %
        11–20 turns : 10 %
        21–40 turns :  5 %   (marathons)

    → median ≈ 2–3 turns, all five dashboard buckets populated.

User activity — share of the user population, by conversations created
(`conversations_per_user`):

        1 conversation    : 35 % of users
        2–5               : 29 %
        6–10              : 17 %
        11–20             : 12 %
        21–50             :  7 %   (power users)

    → ~70 users over 90 days, median ≈ 3 conversations. This split is imposed
      on the population rather than sampled per user, so every bucket is
      non-empty and the median stays put run after run; the power users then
      absorb the few conversations needed to match the planned total exactly.

Events are spread across the last 90 days.

Usage:
    python scripts/seed_agent_kpi.py
    python scripts/seed_agent_kpi.py --since-days 180
    python scripts/seed_agent_kpi.py --dry-run
    python scripts/seed_agent_kpi.py --clear   # delete all seeded docs first
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

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

# Teams a shared (non-personal) conversation can belong to. A conversation that
# is *not* team-scoped runs in its user's own personal space instead, which is
# what `sessions_by_scope` splits on — see PERSONAL_SESSION_SHARE.
SHARED_TEAM_IDS = ["team-alpha", "team-beta", "team-gamma"]
PERSONAL_SESSION_SHARE = 0.35

USER_IDS = [
    "user-aa11",
    "user-bb22",
    "user-cc33",
    "user-dd44",
]

MODEL_NAMES = [
    "gpt-4o",
    "gpt-4o-mini",
    "claude-sonnet-4",
    "mistral-large",
]

RUNTIME_ID = "fred-agents"

# Share of turns that end in an execution error. Mirrors the runtime, which
# emits agent.turn_error_total alongside the turn in that case.
TURN_ERROR_SHARE = 0.02

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

# (weight, min, max, mode) — length of one conversation, in completed turns.
CONVERSATION_LENGTH_DISTRIBUTION = [
    (40, 1, 1, 1),
    (30, 2, 5, 3),
    (15, 6, 10, 7),
    (10, 11, 20, 14),
    ( 5, 21, 40, 26),
]

# (% of users, min, max, mode) — conversations created by one user over the
# window. Unlike the table above these weights are shares of the *population*,
# not of the draws: the population is sized from the conversation count and then
# split by these shares, so the "1" and "2-5" buckets always hold more than half
# the users. That is what pins the dashboard median inside 2-5 instead of
# letting it wander with the sampling luck of a 60-odd draw population.
USER_ACTIVITY_DISTRIBUTION = [
    (35, 1, 1, 1),
    (29, 2, 5, 3),
    (17, 6, 10, 7),
    (12, 11, 20, 14),
    ( 7, 21, 50, 30),
]

# Same buckets as the dashboard presets
# (control_plane_backend/kpi/presets/distribution_utils.py) so `--dry-run`
# output can be compared with the charts line by line.
DASHBOARD_BUCKETS: tuple[tuple[int, int | None, str], ...] = (
    (1, 1, "1"),
    (2, 5, "2-5"),
    (6, 10, "6-10"),
    (11, 20, "11-20"),
    (21, None, "21+"),
)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _ssl_context() -> ssl.SSLContext:
    """Dev-only context: the local OpenSearch uses a self-signed certificate."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _auth_header() -> str:
    creds = f"{OPENSEARCH_USER}:{OPENSEARCH_PASSWORD}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def _req(method: str, path: str, body: Any = None) -> Any:
    """Minimal HTTPS request to OpenSearch (no extra deps required)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": _auth_header(), "Content-Type": "application/json"}

    req = urllib.request.Request(
        OPENSEARCH_URL + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as resp:
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

    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/x-ndjson",
    }
    req = urllib.request.Request(
        OPENSEARCH_URL + "/_bulk", data=payload.encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        result = json.loads(resp.read())
        errors = [i for i in result.get("items", []) if "error" in i.get("index", {})]
        if errors:
            print(f"[WARN] {len(errors)} bulk errors", file=sys.stderr)


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _rand_ts(since: datetime, until: datetime) -> datetime:
    delta = max(0.0, (until - since).total_seconds())
    return since + timedelta(seconds=random.uniform(0, delta))


def _sample_chars(min_c: int, max_c: int, avg_hint: int) -> int:
    """Sample a value that skews toward avg_hint within [min_c, max_c]."""
    # Use a triangular distribution peaking at avg_hint for a realistic shape.
    val = random.triangular(min_c, max_c, avg_hint)
    return max(min_c, min(max_c, round(val)))


def _sample_range(low: int, high: int, mode: int) -> int:
    """Draw an integer in [low, high], triangular around `mode`."""
    if low >= high:
        return low
    return max(low, min(high, round(random.triangular(low, high, mode))))


def _sample_weighted_range(distribution: list[tuple[int, int, int, int]]) -> int:
    """Draw an integer from a `(weight, min, max, mode)` distribution.

    Pick a bucket by weight, then a value inside it — the same idea as
    `_sample_chars`, generalised so the tables above can share one sampler.
    """
    weights = [weight for weight, *_ in distribution]
    _weight, low, high, mode = random.choices(distribution, weights=weights)[0]
    return _sample_range(low, high, mode)


def _bucketize(counts: Sequence[int]) -> list[tuple[str, int]]:
    """Tally `counts` into DASHBOARD_BUCKETS — the presets' exact bucketing."""
    tallies = [0] * len(DASHBOARD_BUCKETS)
    for count in counts:
        for index, (low, high, _label) in enumerate(DASHBOARD_BUCKETS):
            if count >= low and (high is None or count <= high):
                tallies[index] += 1
                break
    return [(label, tallies[i]) for i, (_l, _h, label) in enumerate(DASHBOARD_BUCKETS)]


def _median(counts: Sequence[int]) -> float | None:
    if not counts:
        return None
    ordered = sorted(counts)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Conversation model
# ---------------------------------------------------------------------------

@dataclass
class _PlannedConversation:
    """One conversation carved out of an agent's turn budget, no user yet."""

    agent_id: str
    agent_name: str
    agent_team_id: str
    template_id: str
    turns: int


@dataclass
class Conversation:
    """A seeded conversation: one session doc + `len(turn_times)` turn docs."""

    session_id: str
    agent_id: str
    agent_name: str
    template_id: str
    team_id: str
    scope_type: str  # "personal" | "team", as control-plane emits it
    user_id: str
    model_name: str
    created_at: datetime
    turn_times: list[datetime] = field(default_factory=list)

    @property
    def turns(self) -> int:
        return len(self.turn_times)


def _plan_conversation_lengths(since_days: int) -> list[_PlannedConversation]:
    """Carve every agent's turn budget into conversations.

    The budget comes from CONVERSATION_DISTRIBUTION (scaled to the window) and
    is consumed exactly, so `top_agents_by_conversations` keeps its intended
    per-agent totals — only the last conversation of each agent may be cut
    short by whatever the budget has left.
    """
    scale = since_days / 30.0
    planned: list[_PlannedConversation] = []

    for agent_name, turns_per_month in CONVERSATION_DISTRIBUTION:
        agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"seed-agent-{agent_name}"))
        agent_team_id = random.choice(SHARED_TEAM_IDS)
        template_id = random.choice(TEMPLATE_IDS)

        remaining = max(1, round(turns_per_month * scale))
        while remaining > 0:
            length = min(
                _sample_weighted_range(CONVERSATION_LENGTH_DISTRIBUTION), remaining
            )
            planned.append(
                _PlannedConversation(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    agent_team_id=agent_team_id,
                    template_id=template_id,
                    turns=length,
                )
            )
            remaining -= length

    return planned


def _plan_user_activity(conversation_count: int) -> list[int]:
    """Per-user conversation counts adding up to `conversation_count`.

    The population size follows from the conversations already planned — no
    third number to keep in sync with the two distributions — but its *shape*
    is imposed, not sampled: each bucket of USER_ACTIVITY_DISTRIBUTION gets its
    share of the population, so every bucket of the dashboard histogram is
    guaranteed non-empty and the median cannot drift out of "2-5".
    """
    total_weight = sum(weight for weight, *_ in USER_ACTIVITY_DISTRIBUTION)
    # Mean of a triangular draw is (low + high + mode) / 3.
    expected_mean = (
        sum(
            weight * (low + high + mode) / 3
            for weight, low, high, mode in USER_ACTIVITY_DISTRIBUTION
        )
        / total_weight
    )
    population = max(
        len(USER_ACTIVITY_DISTRIBUTION), round(conversation_count / expected_mean)
    )

    counts: list[int] = []
    power_users: list[int] = []  # indices into `counts`, for the reconciliation
    last_index = len(USER_ACTIVITY_DISTRIBUTION) - 1
    for index, (weight, low, high, mode) in enumerate(USER_ACTIVITY_DISTRIBUTION):
        if index == 0:
            continue  # the one-shot bucket absorbs the rounding residual below
        for _ in range(round(population * weight / total_weight)):
            counts.append(_sample_range(low, high, mode))
            if index == last_index:
                power_users.append(len(counts) - 1)
    counts.extend([1] * max(0, population - len(counts)))

    # Reconcile with the exact conversation count on the power users only: the
    # "21+" bucket is open-ended, so moving conversations in and out of it
    # cannot change any bucket's user count as long as we stay above its floor.
    delta = conversation_count - sum(counts)
    floor = USER_ACTIVITY_DISTRIBUTION[last_index][1]
    position = 0
    while delta > 0 and power_users:
        counts[power_users[position % len(power_users)]] += 1
        delta -= 1
        position += 1
    while delta < 0:
        drained = False
        for index in power_users:
            if delta == 0:
                break
            if counts[index] > floor:
                counts[index] -= 1
                delta += 1
                drained = True
        if not drained:
            break  # dealt with by the caller, which truncates on the leftover

    random.shuffle(counts)  # so user ids are not ordered by activity
    return counts


def _user_id_for(index: int) -> str:
    """Reuse the small fixed pool first, then generate as many as needed."""
    if index < len(USER_IDS):
        return USER_IDS[index]
    return f"user-{index:04d}"


def plan_conversations(since_days: int) -> list[Conversation]:
    """Build the whole conversation population for the window."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=since_days)

    planned = _plan_conversation_lengths(since_days)
    random.shuffle(planned)  # so a user's conversations span several agents

    # The plan is sized to `planned`, but sampling can leave a residual the
    # power-user reconciliation could not absorb: hand it to extra one-shot
    # users so no conversation is dropped (and slice defensively below so no
    # user is dealt a conversation that does not exist).
    user_counts = _plan_user_activity(len(planned))
    user_counts.extend([1] * max(0, len(planned) - sum(user_counts)))

    conversations: list[Conversation] = []
    cursor = 0
    for user_index, conversation_count in enumerate(user_counts):
        if cursor >= len(planned):
            break
        user_id = _user_id_for(user_index)
        for item in planned[cursor : cursor + conversation_count]:
            if random.random() < PERSONAL_SESSION_SHARE:
                team_id, scope_type = f"personal-{user_id}", "personal"
            else:
                team_id, scope_type = item.agent_team_id, "team"

            # Turns are minutes apart; start the conversation early enough that
            # its last turn still falls inside the window.
            gaps = [random.randint(45, 480) for _ in range(item.turns)]
            created_at = _rand_ts(
                window_start, now - timedelta(seconds=sum(gaps))
            )
            turn_times: list[datetime] = []
            cursor_ts = created_at
            for gap in gaps:
                cursor_ts += timedelta(seconds=gap)
                turn_times.append(cursor_ts)

            conversations.append(
                Conversation(
                    session_id=str(uuid.uuid4()),
                    agent_id=item.agent_id,
                    agent_name=item.agent_name,
                    template_id=item.template_id,
                    team_id=team_id,
                    scope_type=scope_type,
                    user_id=user_id,
                    model_name=random.choice(MODEL_NAMES),
                    created_at=created_at,
                    turn_times=turn_times,
                )
            )
        cursor += conversation_count

    return conversations


def _make_session_created_event(conv: Conversation) -> dict[str, Any]:
    """Mirrors control-plane `create_session` (product/service.py)."""
    return {
        "@timestamp": conv.created_at.isoformat(),
        "metric": {"name": "session.created_total", "type": "counter", "unit": "count", "value": 1.0},
        "dims": {
            "service": "control-plane",
            "team_id": conv.team_id,
            "scope_type": conv.scope_type,
            "agent_instance_id": conv.agent_id,
            "actor_type": "human",
            "user_id": conv.user_id,
        },
        "labels": [SEED_LABEL],
    }


def _turn_dims(conv: Conversation, finish_reason: str) -> dict[str, Any]:
    """Mirrors `agent_app._emit_turn_metrics` dims (fred-runtime)."""
    return {
        "service": RUNTIME_ID,
        "session_id": conv.session_id,
        "team_id": conv.team_id,
        "template_agent_id": conv.template_id,
        "agent_instance_id": conv.agent_id,
        "agent_instance_name": conv.agent_name,
        "runtime_id": RUNTIME_ID,
        "model_name": conv.model_name,
        "finish_reason": finish_reason,
        "actor_type": "human",
        "user_id": conv.user_id,
    }


def _make_turn_events(conv: Conversation, ts: datetime) -> list[dict[str, Any]]:
    """One completed turn — plus its error counter when the turn failed."""
    is_error = random.random() < TURN_ERROR_SHARE
    finish_reason = "error" if is_error else "stop"
    dims = _turn_dims(conv, finish_reason)

    events = [
        {
            "@timestamp": ts.isoformat(),
            "metric": {
                "name": "agent.turn_completed",
                "type": "timer",
                "unit": "ms",
                "value": round(random.triangular(600, 40000, 4200), 1),
            },
            "dims": dims,
            "labels": [SEED_LABEL],
        }
    ]
    if is_error:
        events.append(
            {
                "@timestamp": ts.isoformat(),
                "metric": {"name": "agent.turn_error_total", "type": "counter", "unit": "count", "value": 1.0},
                "dims": dict(dims),
                "labels": [SEED_LABEL],
            }
        )
    return events


def build_conversation_events(conversations: list[Conversation]) -> list[dict[str, Any]]:
    """Expand the conversation population into KPI documents."""
    events: list[dict[str, Any]] = []
    for conv in conversations:
        events.append(_make_session_created_event(conv))
        for ts in conv.turn_times:
            events.extend(_make_turn_events(conv, ts))
    return events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_events(since_days: int) -> list[dict[str, Any]]:
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


def _print_distribution(title: str, counts: Sequence[int], unit: str) -> None:
    """Print the dashboard buckets + median for a population of counts."""
    if not counts:
        print(f"    {title}: (empty)")
        return
    median = _median(counts)
    print(f"    {title}: {len(counts)} entries, "
          f"min {min(counts)} / median {median} / max {max(counts)} {unit}")
    for label, value in _bucketize(counts):
        print(f"        {label:<6} {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since-days", type=int, default=90, help="Spread events over this many days (default: 90)")
    parser.add_argument("--dry-run", action="store_true", help="Print event count without indexing")
    parser.add_argument("--clear", action="store_true", help="Delete previously seeded docs and exit")
    args = parser.parse_args()

    if args.clear:
        clear_seeded(dry_run=args.dry_run)
        return

    lifecycle_events = build_events(since_days=args.since_days)
    conversations = plan_conversations(since_days=args.since_days)
    convo_events = build_conversation_events(conversations)
    events = lifecycle_events + convo_events

    agent_total = sum(c for c, *_ in TARGET_DISTRIBUTION)
    per_user: dict[str, int] = {}
    for conv in conversations:
        per_user[conv.user_id] = per_user.get(conv.user_id, 0) + 1

    print(f"Generated {len(events)} total events:")
    print(f"  Lifecycle ({agent_total} agents, all paired with delete):")
    print(f"    • {sum(1 for e in lifecycle_events if e['metric']['name'] == 'agent.created_total')} created")
    print(f"    • {sum(1 for e in lifecycle_events if e['metric']['name'] == 'agent.updated')} updated")
    print(f"    • {sum(1 for e in lifecycle_events if e['metric']['name'] == 'agent.deleted_total')} deleted")
    print(f"  Conversations ({len(CONVERSATION_DISTRIBUTION)} agents, "
          f"{len(conversations)} conversations, {len(per_user)} users):")
    print(f"    • {sum(1 for e in convo_events if e['metric']['name'] == 'session.created_total')} session.created_total")
    print(f"    • {sum(1 for e in convo_events if e['metric']['name'] == 'agent.turn_completed')} agent.turn_completed")
    print(f"    • {sum(1 for e in convo_events if e['metric']['name'] == 'agent.turn_error_total')} agent.turn_error_total")
    personal = sum(1 for c in conversations if c.scope_type == "personal")
    print(f"    • scope split: {personal} personal / {len(conversations) - personal} team")
    _print_distribution(
        "conversation_depth", [c.turns for c in conversations], "turns"
    )
    _print_distribution(
        "conversations_per_user", list(per_user.values()), "conversations"
    )

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
