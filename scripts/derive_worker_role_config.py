#!/usr/bin/env python3
# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Derive one worker-role configuration from an existing local worker configuration.

Running the four ingestion worker groups as separate local processes is the only
way to observe the memory isolation a single multi-role worker cannot show. That
needs four configurations, but four checked-in copies of a full configuration
would drift from each other and from the original the first time anything else
changes. This derives them instead, in target/, and never touches the source.

Only what must differ per role is rewritten:
  - the role itself;
  - the Prometheus port, since four processes cannot share one;
  - the activity concurrency, so a local rich worker runs one extraction at a
    time exactly as its deployment does.

Usage:
    python derive_worker_role_config.py --source <config.yaml> --role rich --output <out.yaml>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Role → (worker_roles value, metrics port, concurrent activities). The ports sit
# next to the 9112 the single-worker setup already uses; the concurrencies mirror
# deploy/charts/fred/values.yaml so a local run reproduces the deployment.
ROLES = {
    "common": ("common", 9112, 3),
    "fast": ("extraction-fast", 9113, 4),
    "medium": ("extraction-medium", 9114, 2),
    "rich": ("extraction-rich", 9115, 1),
}


def derive(source: dict, role: str) -> dict:
    worker_role, metrics_port, activities = ROLES[role]
    derived = yaml.safe_load(yaml.safe_dump(source))  # deep copy through plain data

    scheduler = derived.setdefault("scheduler", {})
    scheduler["worker_roles"] = [worker_role]
    scheduler.setdefault("temporal", {})["ingestion_max_concurrent_activities"] = activities

    prometheus = derived.setdefault("observability", {}).setdefault("kpi", {}).setdefault("prometheus", {})
    prometheus["port"] = metrics_port

    return derived


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Local worker configuration to derive from")
    parser.add_argument("--role", choices=sorted(ROLES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"ERROR: no such configuration: {args.source}", file=sys.stderr)
        return 1

    with open(args.source) as handle:
        source = yaml.safe_load(handle)
    if not isinstance(source, dict):
        print(f"ERROR: {args.source} is not a configuration mapping", file=sys.stderr)
        return 1

    derived = derive(source, args.role)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    header = f"# Derived from {args.source.name} for the '{args.role}' worker role. Do not edit: regenerated on every run.\n"
    with open(args.output, "w") as handle:
        handle.write(header)
        yaml.safe_dump(derived, handle, sort_keys=False)

    worker_role, metrics_port, activities = ROLES[args.role]
    print(f"{args.output} — role={worker_role} metrics_port={metrics_port} max_concurrent_activities={activities}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
