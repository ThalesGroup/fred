#!/usr/bin/env python3
"""
Generate migration_data.json comparing Kea vs Swift Postgres schemas.

Spins up two ephemeral Postgres containers, applies all Alembic migrations
from each version, then extracts schemas.  The schemas therefore reflect
what the code defines, not whatever state the local dev DBs happen to be in.

Usage:
  python3 generate.py [--rename kea_table:swift_table ...]

Examples:
  python3 generate.py
  python3 generate.py --rename session:session_metadata --rename agent:agent_instance
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo roots
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SWIFT_ROOT = SCRIPT_DIR.parent.parent          # fred-wt-check-postgres-migration-kea-to-swift
KEA_ROOT   = Path("/home/fmuller/Documents/fred-universe/fred")

# ---------------------------------------------------------------------------
# Backends: (project_dir, alembic_version_table)
# ---------------------------------------------------------------------------

SWIFT_BACKENDS = [
    (SWIFT_ROOT / "apps/control-plane-backend",  "alembic_version_control_plane"),
    (SWIFT_ROOT / "apps/knowledge-flow-backend",  "alembic_version_knowledge_flow"),
    (SWIFT_ROOT / "libs/fred-runtime",            "alembic_version"),
]

KEA_BACKENDS = [
    (KEA_ROOT / "control-plane-backend",  "alembic_version_control_plane"),
    (KEA_ROOT / "knowledge-flow-backend", "alembic_version_knowledge_flow"),
    (KEA_ROOT / "agentic-backend",        "alembic_version_agentic"),
]

# ---------------------------------------------------------------------------
# Ephemeral Postgres config
# ---------------------------------------------------------------------------

COMPOSE_FILE = str(SWIFT_ROOT / "scripts/docker-compose.postgres.yml")

# We need two independent DBs (Kea and Swift).  We reuse the same compose
# service but run them sequentially — bring up, migrate, dump, tear down.
PG_USER     = "test"
PG_PASSWORD = "test"
PG_DB       = "test_migrations"
PG_PORT     = 5433
DB_URL      = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@localhost:{PG_PORT}/{PG_DB}"

# Tables that are alembic internals and should not appear in the viewer
EXCLUDE_TABLES = {
    "alembic_version",
    "alembic_version_agentic",
    "alembic_version_control_plane",
    "alembic_version_knowledge_flow",
    "alembic_version_runtime",
}

STRIP_COLS = {"Collation", "Compression", "Stats target", "Description"}


# ---------------------------------------------------------------------------
# Docker / Postgres helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], cwd: str | Path | None = None, env: dict | None = None) -> str:
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=merged_env)
    if result.returncode != 0:
        print(f"[ERROR] {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def compose_up() -> None:
    print("  Starting ephemeral Postgres…", file=sys.stderr)
    run(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--wait"])


def compose_down() -> None:
    print("  Stopping ephemeral Postgres…", file=sys.stderr)
    run(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"])


def psql_query(query: str) -> str:
    """Run a psql query against the ephemeral container."""
    result = subprocess.run(
        [
            "docker", "compose", "-f", COMPOSE_FILE,
            "exec", "-T", "postgres",
            "psql", "-U", PG_USER, "-d", PG_DB, "-c", query,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] psql: {result.stderr}", file=sys.stderr)
        return ""
    return result.stdout.strip()


def wait_for_postgres(retries: int = 20, delay: float = 1.0) -> None:
    for _ in range(retries):
        result = subprocess.run(
            [
                "docker", "compose", "-f", COMPOSE_FILE,
                "exec", "-T", "postgres",
                "pg_isready", "-U", PG_USER, "-d", PG_DB,
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(delay)
    raise RuntimeError("Ephemeral Postgres did not become ready in time")


def reset_db() -> None:
    """Drop and recreate the test database so we get a clean slate."""
    for stmt in (
        f"DROP DATABASE IF EXISTS {PG_DB}",
        f"CREATE DATABASE {PG_DB}",
    ):
        subprocess.run(
            [
                "docker", "compose", "-f", COMPOSE_FILE,
                "exec", "-T", "postgres",
                "psql", "-U", PG_USER, "-d", "postgres", "-c", stmt,
            ],
            capture_output=True,
        )


def run_migrations(backends: list[tuple[Path, str]]) -> None:
    """Apply alembic upgrade head for each backend against the ephemeral DB."""
    for project_dir, _ in backends:
        print(f"  Migrating {project_dir.name}…", file=sys.stderr)
        run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=project_dir,
            env={"DATABASE_URL": DB_URL},
        )


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------


def list_tables() -> list[str]:
    out = psql_query(r"\dt")
    tables = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[2] == "table":
            name = parts[1].strip()
            if name not in EXCLUDE_TABLES:
                tables.append(name)
    return sorted(tables)


def describe_table(table: str) -> str:
    out = psql_query(f"\\d+ {table}")
    if not out:
        return "(table not found)"
    return _strip_columns(out)


# ---------------------------------------------------------------------------
# Column stripping
# ---------------------------------------------------------------------------


def _strip_columns(text: str) -> str:
    lines = text.splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        if "|" in line and any(c in line for c in ("Nullable", "Type", "Column")):
            header_idx = i
            break

    if header_idx is None:
        return text

    header_parts = [p.strip() for p in lines[header_idx].split("|")]
    keep_indices = [i for i, name in enumerate(header_parts) if name not in STRIP_COLS]
    sep_idx = header_idx + 1

    result = []
    in_table = False
    for i, line in enumerate(lines):
        if i == header_idx:
            in_table = True
        if i > sep_idx and "|" not in line:
            in_table = False

        if not in_table:
            result.append(line)
            continue

        parts = line.split("|")
        if len(parts) == len(header_parts):
            result.append("|".join(parts[j] for j in keep_indices))
        elif not line.replace("|", "").replace("+", "").replace("-", "").strip():
            widths = [len(lines[header_idx].split("|")[j]) for j in keep_indices]
            result.append("|".join("-" * w for w in widths))
        else:
            result.append(line)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rename",
        action="append",
        metavar="KEA:SWIFT",
        default=[],
        help="Declare a renamed table, e.g. --rename session:session_metadata",
    )
    args = parser.parse_args()

    renames: dict[str, str] = {}
    for pair in args.rename:
        if ":" not in pair:
            print(f"[WARN] Ignoring bad --rename value: {pair!r}", file=sys.stderr)
            continue
        kea_name, swift_name = pair.split(":", 1)
        renames[kea_name.strip()] = swift_name.strip()

    # ── Kea schemas ──────────────────────────────────────────────────────────
    print("\n=== Kea ===", file=sys.stderr)
    compose_up()
    wait_for_postgres()
    reset_db()
    run_migrations(KEA_BACKENDS)
    kea_tables = set(list_tables())
    print(f"  Tables: {sorted(kea_tables)}", file=sys.stderr)
    kea_schemas: dict[str, str] = {t: describe_table(t) for t in kea_tables}
    compose_down()

    # ── Swift schemas ─────────────────────────────────────────────────────────
    print("\n=== Swift ===", file=sys.stderr)
    compose_up()
    wait_for_postgres()
    reset_db()
    run_migrations(SWIFT_BACKENDS)
    swift_tables = set(list_tables())
    print(f"  Tables: {sorted(swift_tables)}", file=sys.stderr)
    swift_schemas: dict[str, str] = {t: describe_table(t) for t in swift_tables}
    compose_down()

    # ── Build mappings ────────────────────────────────────────────────────────
    rename_targets = set(renames.values())
    mappings: list[dict] = []

    for kea_name, swift_name in renames.items():
        mappings.append({
            "kea_table":    kea_name,
            "swift_table":  swift_name,
            "kind":         "renamed",
            "kea_schema":   kea_schemas.get(kea_name, ""),
            "swift_schema": swift_schemas.get(swift_name, ""),
        })

    for name in sorted(kea_tables & swift_tables):
        mappings.append({
            "kea_table":    name,
            "swift_table":  name,
            "kind":         "same",
            "kea_schema":   kea_schemas[name],
            "swift_schema": swift_schemas[name],
        })

    for name in sorted(kea_tables - swift_tables - set(renames)):
        mappings.append({
            "kea_table":    name,
            "swift_table":  None,
            "kind":         "deleted",
            "kea_schema":   kea_schemas[name],
            "swift_schema": "",
        })

    for name in sorted(swift_tables - kea_tables - rename_targets):
        mappings.append({
            "kea_table":    None,
            "swift_table":  name,
            "kind":         "new",
            "kea_schema":   "",
            "swift_schema": swift_schemas[name],
        })

    # ── Backend ownership map (derived from alembic/env.py imports) ──────────
    # Key: table name in that version. Value: backend name.
    BACKEND_OWNERSHIP: dict[str, dict[str, str]] = {
        # kea table name → kea backend
        "kea": {
            "teammetadata":        "control-plane",
            "session_purge_queue": "control-plane",
            "users":               "control-plane",
            "session":             "agentic",
            "agent":               "agentic",
            "feedbacks":           "agentic",
            "mcp-server":          "agentic",
            "session_attachments": "agentic",
            "tasks":               "agentic",
            "session_history":     "agentic",
            "metadata":            "knowledge-flow",
            "resource":            "knowledge-flow",
            "tag":                 "knowledge-flow",
            "sched_workflow_tasks":"knowledge-flow",
        },
        # swift table name → swift backend
        "swift": {
            "teammetadata":        "control-plane",
            "session_purge_queue": "control-plane",
            "users":               "control-plane",
            "session_metadata":    "control-plane",
            "agent_instance":      "control-plane",
            "default_prompt_usage":"control-plane",
            "prompt":              "control-plane",
            "session_history":     "fred-runtime",
            "metadata":            "knowledge-flow",
            "resource":            "knowledge-flow",
            "tag":                 "knowledge-flow",
            "sched_workflow_tasks":"knowledge-flow",
        },
    }

    # Attach ownership to each mapping
    for m in mappings:
        m["kea_backend"]   = BACKEND_OWNERSHIP["kea"].get(m["kea_table"] or "", None)
        m["swift_backend"] = BACKEND_OWNERSHIP["swift"].get(m["swift_table"] or "", None)

    output = {
        "meta": {"renames": renames},
        "mappings": mappings,
    }

    # ── Write JSON ────────────────────────────────────────────────────────────
    json_path = SCRIPT_DIR / "migration_data.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {json_path}", file=sys.stderr)

    # ── Inject into HTML ──────────────────────────────────────────────────────
    html_path = SCRIPT_DIR / "compare-schemas.html"
    with open(html_path) as f:
        html = f.read()

    data_js = f"window.MIGRATION_DATA = {json.dumps(output, indent=2)};"
    pattern = re.compile(
        r"/\* __MIGRATION_DATA__ \*/|window\.MIGRATION_DATA\s*=\s*\{.*?\};",
        re.DOTALL,
    )
    if not pattern.search(html):
        print(f"[WARN] No injection point found in {html_path} — skipping", file=sys.stderr)
    else:
        with open(html_path, "w") as f:
            f.write(pattern.sub(lambda _: data_js, html, count=1))
        print(f"Injected data into {html_path}", file=sys.stderr)

    counts = {k: sum(1 for m in mappings if m["kind"] == k) for k in ("same", "renamed", "deleted", "new")}
    print(f"  same={counts['same']}  renamed={counts['renamed']}  deleted={counts['deleted']}  new={counts['new']}", file=sys.stderr)

    # ── Inject into migration guide ───────────────────────────────────────────
    guide_path = SCRIPT_DIR / "migration-guide.html"
    if guide_path.exists():
        with open(guide_path) as f:
            guide_html = f.read()
        guide_pattern = re.compile(
            r"/\* __GUIDE_DATA__ \*/|window\.GUIDE_DATA\s*=\s*\{.*?\};",
            re.DOTALL,
        )
        if guide_pattern.search(guide_html):
            guide_js = f"window.GUIDE_DATA = {json.dumps(output, indent=2)};"
            with open(guide_path, "w") as f:
                f.write(guide_pattern.sub(lambda _: guide_js, guide_html, count=1))
            print(f"Injected data into {guide_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
