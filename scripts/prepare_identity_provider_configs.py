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

# /// script
# dependencies = ["jsonschema>=4.0,<5", "pyyaml>=6.0"]
# ///

"""Prepare complete local identity-provider configs from the existing examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema
import yaml

APPLICATIONS = ("control-plane-backend", "knowledge-flow-backend", "fred-agents")
DEFAULT_PROFILES = ("keycloak", "generic_oidc", "mock_oidc")
PROFILES = (*DEFAULT_PROFILES, "entra")
ENTRA_CLIENTS = {
    "control-plane-backend": "control_plane_client",
    "knowledge-flow-backend": "knowledge_flow_client",
    "fred-agents": "runtime_client",
}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES_DIR = ROOT.parent / "fred-deployment-factory" / "examples" / "identity-providers"


def merge(target: dict[str, Any], overlay: dict[str, Any]) -> None:
    """YAML mappings have arbitrary values; replace scalar and list settings."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value


def prepare(
    profile: str,
    output_dir: Path,
    entra: dict[str, str] | None = None,
    examples_dir: Path = DEFAULT_EXAMPLES_DIR,
) -> list[Path]:
    pending: list[tuple[Path, str]] = []
    for application in APPLICATIONS:
        config_dir = ROOT / "apps" / application / "config"
        config = yaml.safe_load((config_dir / "configuration_prod.yaml").read_text())
        if profile != "keycloak":
            overlay = yaml.safe_load(
                (
                    examples_dir / application / f"configuration_{profile}.example.yaml"
                ).read_text()
            )
            merge(config, overlay)
        if profile == "entra":
            if entra is None:
                raise ValueError("Entra requires tenant and client IDs")
            security = config["security"]
            issuer = f"https://login.microsoftonline.com/{entra['tenant']}/v2.0"
            security["user"].update(
                realm_url=issuer,
                client_id=entra["ui_client"],
                audience=entra["api_client"],
            )
            security["m2m"].update(
                realm_url=issuer,
                client_id=entra[ENTRA_CLIENTS[application]],
            )
            security["delegation"]["audience"] = entra["api_client"]
        schema = json.loads(
            (config_dir / "schema/configuration.schema.json").read_text()
        )
        jsonschema.validate(config, schema)
        output = output_dir.resolve() / profile / f"configuration_{application}.yaml"
        pending.append((output, yaml.safe_dump(config, sort_keys=False)))
        if application == "control-plane-backend":
            catalog = Path(config["policies"]["purge_catalog_path"])
            if not catalog.is_absolute():
                pending.append(
                    (output.parent / catalog, (config_dir / catalog).read_text())
                )
    # Validate all applications before publishing any configuration.
    for output, payload in pending:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "# Generated; regenerate with prepare_identity_provider_configs.py.\n"
            + payload
        )
    return [output for output, _ in pending]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=(*PROFILES, "all"), default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/fred-idp-tests"))
    parser.add_argument("--examples-dir", type=Path, default=DEFAULT_EXAMPLES_DIR)
    for name in ("tenant", "ui_client", "api_client", *ENTRA_CLIENTS.values()):
        parser.add_argument("--entra-" + name.replace("_", "-"))
    args = parser.parse_args()
    profiles = DEFAULT_PROFILES if args.profile == "all" else (args.profile,)
    entra = None
    if "entra" in profiles:
        names = ("tenant", "ui_client", "api_client", *ENTRA_CLIENTS.values())
        entra = {name: getattr(args, "entra_" + name) for name in names}
        if any(not value for value in entra.values()):
            parser.error("Entra requires all six --entra-* identifiers; see --help")
        try:
            for value in entra.values():
                UUID(value)
        except ValueError:
            parser.error("Entra tenant and client IDs must be UUIDs")
    for profile in profiles:
        for output in prepare(profile, args.output_dir, entra, args.examples_dir):
            print(f"OK {output}")


if __name__ == "__main__":
    main()
