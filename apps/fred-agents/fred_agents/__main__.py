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
Entrypoint for `python -m fred_agents`.

Why this module exists:
- keeps HTTP bind settings out of the Makefile so configuration.yaml is the
  single source of truth for host, port, and log level
- `make run` only needs to set ENV_FILE; CONFIG_FILE comes from the .env file

How to use it:
- `make run` (via Makefile) — sets ENV_FILE then delegates here
- `ENV_FILE=./config/.env uv run python -m fred_agents` — direct invocation

Example:
- `python -m fred_agents`
"""

import argparse
import asyncio

import uvicorn
from fred_runtime.app import load_agent_pod_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("api", "worker"), default="api")
    args = parser.parse_args()
    config = load_agent_pod_config()
    if args.mode == "worker":
        from fred_runtime.app.preparation_worker import run_preparation_worker

        asyncio.run(run_preparation_worker(config))
        return
    uvicorn.run(
        "fred_agents.main:app",
        host=config.app.host,
        port=config.app.port,
        log_level=config.app.log_level,
        limit_concurrency=config.app.limit_concurrency,
        reload=False,
    )


if __name__ == "__main__":
    main()
