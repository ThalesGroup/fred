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
Runtime + capability migration runner (#1979, RFC §7.1).

Why this module exists:
- fred-runtime owns one Alembic tree (its session-history tables); each
  installed capability package ships ITS OWN, independently-versioned tree
  under a per-capability version table (`cap_<id>_alembic_version`) — never
  rebased against fred-runtime's or another capability's history
- one discovery mechanism serves both registration and migration: installing a
  capability package (its `fred.capabilities` entry point) IS the registration,
  and `run_all_migrations()` upgrades fred-runtime's tree then every discovered
  capability's tree in turn

How to use:
- `python -m fred_runtime migrate` (see `fred_runtime.__main__`)
- the Helm migration job overrides its `command`/`args` to that CLI, so
  deploying the pod applies both fred-runtime's and every installed
  capability's migrations in one hook
"""

from __future__ import annotations

import logging
from pathlib import Path

from .capabilities import CapabilityRegistry

logger = logging.getLogger(__name__)

# fred-runtime's own Alembic tree ships beside the package (libs/fred-runtime/
# alembic), one level above this module's package directory.
RUNTIME_ALEMBIC_DIR = Path(__file__).resolve().parent.parent / "alembic"


def _upgrade(script_location: str, *, label: str) -> None:
    """Run ``alembic upgrade head`` against one script tree (its env.py owns
    metadata, version table, and DB URL)."""

    from alembic import command
    from alembic.config import Config

    logger.info("[MIGRATE] upgrading %s (%s)", label, script_location)
    cfg = Config()
    cfg.set_main_option("script_location", script_location)
    command.upgrade(cfg, "head")
    logger.info("[MIGRATE] %s at head", label)


def run_all_migrations() -> list[str]:
    """
    Upgrade fred-runtime's tree, then every installed capability's tree.

    Discovery reuses the `fred.capabilities` entry points (no separate
    manifest): a capability contributes migrations only when its
    `migrations_location()` returns a script directory. Returns the ordered
    list of labels upgraded, for logging/CLI output.
    """

    upgraded: list[str] = ["fred-runtime"]
    _upgrade(str(RUNTIME_ALEMBIC_DIR), label="fred-runtime")

    # Discover installed capabilities without booting the full pod: migration
    # runs at deploy time and must not require every capability's runtime env
    # (RFC §7.2 gates those at pod boot, not here).
    registry = CapabilityRegistry()
    registry.discover()
    for cap_id, location in registry.migration_locations():
        _upgrade(location, label=f"capability '{cap_id}'")
        upgraded.append(cap_id)

    logger.info("[MIGRATE] complete: %s", ", ".join(upgraded))
    return upgraded
