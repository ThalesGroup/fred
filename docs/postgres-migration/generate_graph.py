#!/usr/bin/env python3
"""
Generate migration graph data from Alembic migration files and inject into graph.html.

Reads revision/down_revision/docstring from every *.py migration file in each
backend, builds a DAG, then injects it into graph.html as window.GRAPH_DATA.

Usage:
  python3 generate_graph.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo roots and backends
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SWIFT_ROOT = SCRIPT_DIR.parent.parent
KEA_ROOT   = Path("/home/fmuller/Documents/fred-universe/fred")

BACKENDS = {
    "kea": [
        (KEA_ROOT / "control-plane-backend/alembic/versions",   "control-plane"),
        (KEA_ROOT / "knowledge-flow-backend/alembic/versions",  "knowledge-flow"),
        (KEA_ROOT / "agentic-backend/alembic/versions",         "agentic"),
    ],
    "swift": [
        (SWIFT_ROOT / "apps/control-plane-backend/alembic/versions",  "control-plane"),
        (SWIFT_ROOT / "apps/knowledge-flow-backend/alembic/versions", "knowledge-flow"),
        (SWIFT_ROOT / "libs/fred-runtime/alembic/versions",           "fred-runtime"),
    ],
}

# ---------------------------------------------------------------------------
# Migration file parsing
# ---------------------------------------------------------------------------

_REVISION_RE    = re.compile(r'^revision\s*(?::\s*str\s*)?=\s*["\']([^"\']+)["\']', re.M)
# Capture everything from `down_revision = ` up to (but not including) `branch_labels`
# so multi-line tuples like `(\n    "abc"\n)` are fully captured.
_DOWN_REV_RE    = re.compile(
    r'^down_revision\s*(?::[^=]+)?\s*=\s*(.*?)(?=\nbranch_labels)',
    re.M | re.DOTALL,
)
_CREATE_DATE_RE = re.compile(r'Create Date:\s*(\S+)', re.M)


def _parse_down_revision(raw: str) -> list[str]:
    """Return a list of parent revision IDs from the raw down_revision value."""
    raw = raw.strip()
    # None / empty
    if raw in ("None", ""):
        return []
    # Tuple literal: ("abc", "def") or ("abc",)
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, tuple):
            return [v for v in val if v]
        if isinstance(val, str):
            return [val] if val else []
    except (ValueError, SyntaxError):
        pass
    # Bare string on multiple lines (pragma comments etc.)
    ids = re.findall(r'["\']([a-f0-9]{12})["\']', raw)
    return ids


def _extract_description(source: str) -> str:
    """Return the first non-blank line of the module docstring."""
    stripped = source.lstrip()
    if not stripped.startswith('"""') and not stripped.startswith("'''"):
        return ""
    quote = stripped[:3]
    end = stripped.find(quote, 3)
    if end == -1:
        return ""
    docstring = stripped[3:end].strip()
    first_line = docstring.splitlines()[0].strip() if docstring else ""
    return first_line


def parse_migration_file(path: Path) -> dict | None:
    source = path.read_text(encoding="utf-8")

    rev_match = _REVISION_RE.search(source)
    if not rev_match:
        return None
    revision = rev_match.group(1)

    down_match = _DOWN_REV_RE.search(source)
    parents = _parse_down_revision(down_match.group(1).strip() if down_match else "")

    date_match = _CREATE_DATE_RE.search(source)
    create_date = date_match.group(1) if date_match else ""

    description = _extract_description(source)

    return {
        "id":          revision,
        "filename":    path.stem,
        "description": description,
        "create_date": create_date,
        "parents":     parents,
    }


# ---------------------------------------------------------------------------
# Graph building
# ---------------------------------------------------------------------------


def build_version_graph(version: str) -> dict:
    """Return graph data for one version (kea or swift)."""
    backends_data = []

    for versions_dir, backend_name in BACKENDS[version]:
        nodes = []
        if not versions_dir.exists():
            print(f"[WARN] Missing: {versions_dir}", file=sys.stderr)
            backends_data.append({"name": backend_name, "nodes": nodes})
            continue

        for path in sorted(versions_dir.glob("*.py")):
            if path.name.startswith("__"):
                continue
            node = parse_migration_file(path)
            if node:
                nodes.append(node)

        print(f"  {version}/{backend_name}: {len(nodes)} migrations", file=sys.stderr)
        backends_data.append({"name": backend_name, "nodes": nodes})

    return {"version": version, "backends": backends_data}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Building migration graphs…", file=sys.stderr)
    output = {
        "kea":   build_version_graph("kea"),
        "swift": build_version_graph("swift"),
    }

    # Write JSON sidecar
    json_path = SCRIPT_DIR / "graph_data.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {json_path}", file=sys.stderr)

    # Inject into HTML
    html_path = SCRIPT_DIR / "graph.html"
    if not html_path.exists():
        print(f"[WARN] {html_path} not found — skipping injection", file=sys.stderr)
        return

    with open(html_path) as f:
        html = f.read()

    data_js = f"window.GRAPH_DATA = {json.dumps(output, indent=2)};"
    pattern = re.compile(
        r"/\* __GRAPH_DATA__ \*/|window\.GRAPH_DATA\s*=\s*\{.*?\};",
        re.DOTALL,
    )
    if not pattern.search(html):
        print(f"[WARN] No injection point found in {html_path}", file=sys.stderr)
    else:
        with open(html_path, "w") as f:
            f.write(pattern.sub(lambda _: data_js, html, count=1))
        print(f"Injected data into {html_path}", file=sys.stderr)

    total = sum(
        len(b["nodes"])
        for v in output.values()
        for b in v["backends"]
    )
    print(f"  Total migrations: {total}", file=sys.stderr)


if __name__ == "__main__":
    main()
