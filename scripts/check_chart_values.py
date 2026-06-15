# /// script
# dependencies = [
#   "jsonschema>=4.0,<5",
#   "pyyaml>=6.0",
# ]
# ///
"""Validate deploy/charts/fred/values.yaml against values.schema.json.

Helm resolves YAML anchors and strips x-* keys before schema validation.
This script replicates that behaviour so the check is faithful to what
`helm lint` would see.

Usage:
    python check_chart_values.py <schema.json> <values.yaml>

Exit code: 0 if valid, 1 if invalid.
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


def _strip_helm_anchors(values: object) -> object:
    """Remove top-level x-* keys that are YAML anchors, not real values."""
    if isinstance(values, dict):
        return {k: v for k, v in values.items() if not str(k).startswith("x-")}
    return values


def _validate(instance: object, schema: dict) -> list[str]:
    from jsonschema import Draft7Validator

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [
        f"  [{'.'.join(str(p) for p in e.absolute_path) or '<root>'}] {e.message}"
        for e in errors
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Helm values.yaml against values.schema.json")
    parser.add_argument("schema", help="Path to values.schema.json")
    parser.add_argument("values", help="Path to values.yaml")
    args = parser.parse_args()

    schema = _load_json(Path(args.schema))
    raw = _load_yaml(Path(args.values))
    values = _strip_helm_anchors(raw)

    errors = _validate(values, schema)

    if errors:
        print(f"FAIL  {args.values}")
        for err in errors:
            print(err)
        print("\nValues validation failed. Fix the errors above or update the schema.")
        sys.exit(1)

    print(f"OK    {args.values}")
    print("\nValues file is valid.")


if __name__ == "__main__":
    main()
