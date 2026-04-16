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
- keeps host/port out of the Makefile so configuration.yaml is the single
  source of truth for those values
- `make run` only needs to set ENV_FILE; CONFIG_FILE comes from the .env file

How to use it:
- `make run` (via Makefile) — sets ENV_FILE then delegates here
- `ENV_FILE=./config/.env uv run python -m fred_agents` — direct invocation

Example:
- `python -m fred_agents`
"""

import uvicorn
from fred_runtime.app import load_agent_pod_config


def main() -> None:
    config = load_agent_pod_config()
    uvicorn.run(
        "fred_agents.main:app",
        host="127.0.0.1",
        port=config.app.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
