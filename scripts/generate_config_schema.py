"""Generate a JSON schema from a Pydantic BaseModel config class.

Usage:
    python generate_config_schema.py <module.ClassName> <output.json>

Example:
    python generate_config_schema.py control_plane_backend.config.models.Configuration \
        apps/control-plane-backend/config/schema/configuration.schema.json
"""

import importlib
import json
import sys


def _set_no_additional_properties(node: object) -> None:
    """Recursively add additionalProperties: false to every object schema node."""
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            node.setdefault("additionalProperties", False)
        for value in node.values():
            _set_no_additional_properties(value)
    elif isinstance(node, list):
        for item in node:
            _set_no_additional_properties(item)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <module.ClassName> <output.json>", file=sys.stderr)
        sys.exit(1)

    qualified_name = sys.argv[1]
    output_path = sys.argv[2]

    module_path, class_name = qualified_name.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    schema = cls.model_json_schema()
    _set_no_additional_properties(schema)

    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")

    print(f"Schema written to {output_path}")


if __name__ == "__main__":
    main()
