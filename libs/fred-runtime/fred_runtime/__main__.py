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

"""
`python -m fred_runtime <command>` — the pod-side operational CLI (#1979).

Commands:
- `migrate` — upgrade fred-runtime's Alembic tree, then every installed
  capability's own tree (RFC §7.1). The Helm migration job points its
  `command`/`args` here so deploying the pod runs all migrations.
- `dump-openapi <capability_id>` — print one capability router's OpenAPI JSON
  (RFC §9.1), the `schemaFile` input for that capability's frontend codegen.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys


def _cmd_migrate(_args: argparse.Namespace) -> int:
    from .migrations import run_all_migrations

    upgraded = run_all_migrations()
    print(f"migrated: {', '.join(upgraded)}")
    return 0


def _cmd_dump_openapi(args: argparse.Namespace) -> int:
    from .capabilities import CapabilityRegistry
    from .capabilities.openapi_dump import dump_capability_openapi

    registry = CapabilityRegistry()
    registry.discover()
    if args.capability_id not in registry:
        print(
            f"capability '{args.capability_id}' is not installed "
            f"(installed: {', '.join(registry.ids()) or 'none'})",
            file=sys.stderr,
        )
        return 2
    document = dump_capability_openapi(registry.capability(args.capability_id))
    print(json.dumps(document, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    parser = argparse.ArgumentParser(prog="fred_runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="run fred-runtime + capability migrations")

    dump = sub.add_parser(
        "dump-openapi", help="print one capability router's OpenAPI document"
    )
    dump.add_argument("capability_id", help="the capability manifest id")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _cmd_migrate(args)
    if args.command == "dump-openapi":
        return _cmd_dump_openapi(args)
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
