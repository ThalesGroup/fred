# /// script
# dependencies = [
#   "jsonschema>=4.0,<5",
#   "pyyaml>=6.0",
# ]
# ///
"""Validate backend configuration YAML files against their JSON schemas.

Usage:
    python check_config_files.py <schema.json> <config_dir>

All files matching *configuration*.yaml in <config_dir> are validated against
the same schema, including configuration_worker.yaml.
Validation is strict: extra keys not present in the schema are rejected.

Exit code: 0 if all files pass, 1 if any file fails or is missing.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_yaml(path: Path) -> object:
    with open(path) as f:
        return yaml.safe_load(f)


def _validate(instance: object, schema: dict) -> list[str]:
    """Return a list of human-readable error strings, empty if valid."""
    from jsonschema import Draft7Validator

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [
        f"  [{'.'.join(str(p) for p in e.absolute_path) or '<root>'}] {e.message}"
        for e in errors
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate config YAML files against JSON schemas")
    parser.add_argument("schema", help="Path to the JSON schema file")
    parser.add_argument("config_dir", help="Directory containing configuration*.yaml files")
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    schema = _load_json(Path(args.schema))

    yaml_files = sorted(config_dir.glob("*configuration*.yaml"))
    if not yaml_files:
        print(f"WARNING: No configuration*.yaml files found in {config_dir}")
        sys.exit(0)

    all_passed = True
    for yaml_file in yaml_files:
        instance = _load_yaml(yaml_file)
        errors = _validate(instance, schema)

        if errors:
            print(f"FAIL  {yaml_file.relative_to(config_dir.parent)}")
            for err in errors:
                print(err)
            all_passed = False
        else:
            print(f"OK    {yaml_file.relative_to(config_dir.parent)}")

    if not all_passed:
        print("\nValidation failed. Fix the errors above or update the schema with 'make generate-config-schema'.")
        sys.exit(1)

    print("\nAll configuration files are valid.")


if __name__ == "__main__":
    main()
