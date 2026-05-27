"""
restore_agent_ownership.py

Recovers OpenFGA agent ownership tuples from PostgreSQL data after an
in-memory store loss. Two recovery strategies:

  1. Team agents   — agent.payload_json->>'team_id' is a UUID
                     -> tuple: team:<id> owner agent:<id>
  2. Personal agents — unique (user_id, agent_id) pairs from sessions
                       where team_id = 'personal'
                     -> tuple: user:<id> owner agent:<id>

Prerequisites (must be in PATH):
  - kubectl   (configured for the target cluster)
  - fga       (OpenFGA CLI)

No third-party packages required — stdlib only.

Usage:
  python restore_agent_ownership.py [options]

  --dry-run          Print tuples that would be written; do not write anything.
  --skip-team        Skip team-agent recovery.
  --skip-personal    Skip personal-agent recovery.

Configuration is set via constants at the top of the file (or override via
environment variables of the same name).
"""

import argparse
import json
import os
import subprocess
import sys

# ── Configuration ─────────────────────────────────────────────────────────────
# Edit these values before running, or export them as environment variables.

POSTGRES_POD_NAME = os.environ.get("POSTGRES_POD_NAME", "fred-postgres-0")
KUBE_NAMESPACE    = os.environ.get("KUBE_NAMESPACE",    "fred")

PG_USER     = os.environ.get("PG_USER",     "fred")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "change-me")
PG_DATABASE = os.environ.get("PG_DATABASE", "fred")

FGA_API_URL   = os.environ.get("FGA_API_URL",   "https://fga.your-prod.example.com")
FGA_API_TOKEN = os.environ.get("FGA_API_TOKEN", "change-me")
FGA_STORE_NAME = os.environ.get("FGA_STORE_NAME", "fred")
# Set FGA_STORE_ID to skip the store-name lookup entirely.
FGA_STORE_ID  = os.environ.get("FGA_STORE_ID",  "")

# ── Helpers ───────────────────────────────────────────────────────────────────

def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)

def info(msg: str) -> None:
    print(f"    {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"    [WARN] {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"    [OK]   {msg}", flush=True)

def die(msg: str) -> None:
    print(f"\n[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd: list[str], env: dict | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command, return the CompletedProcess (stdout/stderr captured)."""
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(cmd, capture_output=True, text=True, env=merged_env, timeout=timeout)


def pg_query(sql: str) -> list[tuple[str, ...]]:
    """
    Execute a SQL query inside the postgres pod via kubectl exec.
    Returns a list of tuples (one per row), tab-separated columns.
    """
    cmd = [
        "kubectl", "exec",
        "-n", KUBE_NAMESPACE,
        POSTGRES_POD_NAME,
        "--",
        "env", f"PGPASSWORD={PG_PASSWORD}",
        "psql",
        "-U", PG_USER,
        "-d", PG_DATABASE,
        "-t",        # tuples only (no header/footer)
        "-A",        # unaligned output
        "-F", "\t",  # tab separator
        "-c", sql,
    ]
    result = run(cmd)
    if result.returncode != 0:
        die(f"psql failed (exit {result.returncode}):\n{result.stderr}")

    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = tuple(c.strip() for c in line.split("\t"))
        rows.append(parts)
    return rows


def fga_write(user: str, relation: str, obj: str, dry_run: bool) -> None:
    """Write a single ownership tuple to OpenFGA."""
    cmd = [
        "fga", "tuple", "write",
        user, relation, obj,
        "--store-id",     FGA_STORE_ID,
        "--api-url",      FGA_API_URL,
        "--on-duplicate", "ignore",
    ]
    if FGA_API_TOKEN:
        cmd += ["--api-token", FGA_API_TOKEN]

    if dry_run:
        info(f"[DRY-RUN] {' '.join(cmd)}")
        return

    try:
        result = run(cmd)
    except subprocess.TimeoutExpired:
        warn(f"Timeout writing tuple: {user} {relation} {obj} — skipping")
        return

    if result.returncode != 0:
        die(
            f"fga write failed for '{user} {relation} {obj}':\n"
            f"{result.stdout}{result.stderr}"
        )
    else:
        ok(f"Written: {user} {relation} {obj}")


# ── Step 1: Resolve store ID ──────────────────────────────────────────────────

def resolve_store_id() -> str:
    global FGA_STORE_ID

    step("Resolving OpenFGA store")

    if FGA_STORE_ID:
        info(f"Using provided store ID: {FGA_STORE_ID}")
        return FGA_STORE_ID

    info(f"Looking up store '{FGA_STORE_NAME}' at {FGA_API_URL} ...")

    cmd = ["fga", "store", "list", "--api-url", FGA_API_URL]
    if FGA_API_TOKEN:
        cmd += ["--api-token", FGA_API_TOKEN]

    result = run(cmd)
    if result.returncode != 0:
        die(f"fga store list failed:\n{result.stderr}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        die(f"Could not parse fga store list output:\n{result.stdout}")

    stores = data.get("stores", [])
    match = next((s for s in stores if s.get("name") == FGA_STORE_NAME), None)
    if not match:
        names = [s.get("name") for s in stores]
        die(f"No store named '{FGA_STORE_NAME}' found. Available: {names}")

    store_id = match["id"]
    info(f"Resolved store ID: {store_id}")
    return store_id


# ── Step 2: Team agents ───────────────────────────────────────────────────────

def recover_team_agents(dry_run: bool) -> None:
    step("Recovering team-owned agents (payload_json->>'team_id' IS NOT NULL)")

    sql = """
SELECT id, payload_json->>'team_id' AS team_id
FROM agent
WHERE payload_json->>'team_id' IS NOT NULL
  AND payload_json->>'team_id' <> '';
"""
    rows = pg_query(sql)
    count = 0
    skipped = 0

    for parts in rows:
        if len(parts) < 2:
            warn(f"Unexpected row: {parts}")
            skipped += 1
            continue
        agent_id, team_id = parts[0], parts[1]
        if not agent_id or not team_id:
            skipped += 1
            continue
        fga_write(f"team:{team_id}", "owner", f"agent:{agent_id}", dry_run)
        count += 1

    info(f"Team agents processed: {count}  |  skipped (bad rows): {skipped}")


# ── Step 3: Personal agents ───────────────────────────────────────────────────

def recover_personal_agents(dry_run: bool) -> None:
    step("Recovering personal agents from sessions (team_id = 'personal')")

    sql = """
SELECT DISTINCT s.user_id, s.agent_id
FROM session s
WHERE s.team_id = 'personal'
  AND s.agent_id IS NOT NULL
  AND s.agent_id <> ''
  AND EXISTS (SELECT 1 FROM agent a WHERE a.id = s.agent_id);
"""
    rows = pg_query(sql)
    count = 0
    skipped = 0

    for parts in rows:
        if len(parts) < 2:
            warn(f"Unexpected row: {parts}")
            skipped += 1
            continue
        user_id, agent_id = parts[0], parts[1]
        if not user_id or not agent_id:
            skipped += 1
            continue
        fga_write(f"user:{user_id}", "owner", f"agent:{agent_id}", dry_run)
        count += 1

    info(f"Personal agents processed: {count}  |  skipped (bad rows): {skipped}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore OpenFGA agent ownership tuples from PostgreSQL."
    )
    parser.add_argument("--dry-run",       action="store_true", help="Preview only, no writes.")
    parser.add_argument("--skip-team",     action="store_true", help="Skip team-agent recovery.")
    parser.add_argument("--skip-personal", action="store_true", help="Skip personal-agent recovery.")
    args = parser.parse_args()

    global FGA_STORE_ID
    FGA_STORE_ID = resolve_store_id()

    if not args.skip_team:
        recover_team_agents(args.dry_run)

    if not args.skip_personal:
        recover_personal_agents(args.dry_run)

    step("Done")
    if args.dry_run:
        print("\n[DRY-RUN mode — no tuples were written]")
    else:
        print("\nAgent ownership recovery complete.")


if __name__ == "__main__":
    main()
