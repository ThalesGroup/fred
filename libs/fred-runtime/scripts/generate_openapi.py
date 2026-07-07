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

#!/usr/bin/env python3
"""
Generate the frontend-facing fred-runtime OpenAPI specification offline.

Why this exists:
- `fred-runtime` is a reusable library, not a standalone backend with its own
  `main.py` and checked-in config directory
- Phase 2 frontend codegen still needs a stable `openapi.json` artifact sourced
  from the runtime execution contracts

How to use it:
- run `make generate-openapi` from `libs/fred-runtime`
- the script builds a minimal offline pod app and writes `openapi.json` at the
  library root

Example:
- `cd libs/fred-runtime && make generate-openapi`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fred_runtime.app import AgentPodConfig, create_agent_app


def build_openapi_app() -> FastAPI:
    """
    Build a minimal offline pod app used only for OpenAPI export.

    Why this exists:
    - the runtime contracts live on the reusable pod routes created by
      `create_agent_app(...)`
    - schema export should not depend on a real agent registry, Keycloak, or
      external services being available

    How to use it:
    - call once during schema generation, then use `app.openapi()`

    Example:
    - `app = build_openapi_app()`
    """

    config = AgentPodConfig.model_validate(
        {
            "app": {
                "name": "Fred Runtime",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
            },
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "fred-runtime-openapi-m2m",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "fred-runtime-openapi-user",
                },
                "authorized_origins": [],
            },
            "ai": {
                "knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1",
            },
            "storage": {
                "postgres": {
                    "sqlite_path": "~/.fred/fred-runtime/openapi.sqlite3",
                }
            },
            "platform": {
                "control_plane_url": "http://localhost:8222/control-plane/v1",
            },
        }
    )
    return create_agent_app(registry={}, config=config)


def generate_openapi(output_file: Path) -> Path:
    """
    Write the runtime OpenAPI JSON artifact to disk.

    Why this exists:
    - frontend RTK Query codegen expects a schema file path, not an in-memory
      FastAPI app object

    How to use it:
    - pass the desired output path, typically `<repo>/libs/fred-runtime/openapi.json`

    Example:
    - `generate_openapi(Path("openapi.json"))`
    """

    app = build_openapi_app()
    output_file.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_file


def main() -> int:
    """
    Run the offline fred-runtime OpenAPI export.

    Why this exists:
    - `make generate-openapi` needs a small CLI entrypoint with a predictable
      exit code for local development and CI

    How to use it:
    - execute the script directly or via the Make target in `libs/fred-runtime`

    Example:
    - `python scripts/generate_openapi.py`
    """

    project_root = Path(__file__).resolve().parents[1]
    output_file = project_root / "openapi.json"

    try:
        generated = generate_openapi(output_file)
        print(f"✅ OpenAPI specification generated for fred-runtime: {generated}")
        return 0
    except Exception as exc:  # pragma: no cover - surfaced through CLI output
        print(f"❌ Error generating OpenAPI specification: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
