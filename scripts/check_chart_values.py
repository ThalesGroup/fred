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


def _deep_merge(base: object, overlay: object) -> object:
    """Merge `overlay` over `base` the way Helm merges successive -f files.

    Helm's rule: maps merge key-by-key, everything else (scalars, lists) is replaced
    wholesale by the later file. Overlays like values-gcp.yaml and values-local.yaml are
    *partial* — they carry only the keys they change — so validating one on its own reports
    every required property that lives in the base as missing. What ships is the merge, so
    that is what has to satisfy the schema.

    An explicit null in the overlay DELETES the key rather than setting it to None — that
    is Helm's documented behaviour, and without it this merge validates a document Helm
    would never render (an overlay clearing an inherited `duckdb_path` would be checked
    with the key still present).
    """
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = _deep_merge(merged[key], value) if key in merged else value
        return merged
    return overlay


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
    parser.add_argument(
        "--merge-over",
        metavar="BASE_VALUES",
        help=(
            "Treat `values` as a partial Helm overlay and validate it merged over BASE_VALUES, "
            "as `helm -f BASE_VALUES -f values` would render it."
        ),
    )
    args = parser.parse_args()

    schema = _load_json(Path(args.schema))
    values = _strip_helm_anchors(_load_yaml(Path(args.values)))

    label = args.values
    if args.merge_over:
        base = _strip_helm_anchors(_load_yaml(Path(args.merge_over)))
        values = _deep_merge(base, values)
        label = f"{args.values} (merged over {args.merge_over})"

    errors = _validate(values, schema)

    if errors:
        print(f"FAIL  {label}")
        for err in errors:
            print(err)
        print("\nValues validation failed. Fix the errors above or update the schema.")
        sys.exit(1)

    print(f"OK    {label}")
    print("\nValues file is valid.")


if __name__ == "__main__":
    main()
