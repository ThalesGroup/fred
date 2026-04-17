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
ASGI entrypoint for the standalone Fred agents pod.

Why this module exists:
- downstream pod apps need a tiny `main.py` that loads config, builds the
  registry, and exposes an `app` object for Uvicorn

How to use it:
- run `uvicorn fred_agents.main:app`
- or import `create_app()` in tests

Example:
- `app = create_app()`
"""

from fastapi import FastAPI
from fred_runtime.app import AgentPodConfig, create_agent_app, load_agent_pod_config

from fred_agents.registry import REGISTRY


def create_app(config: AgentPodConfig | None = None) -> FastAPI:
    """
    Build the standalone Fred agents FastAPI application.

    Why this function exists:
    - keeps the pod aligned with the standard Fred startup contract while still
      allowing tests to inject or reuse configuration

    How to use it:
    - call without arguments for normal startup
    - pass an explicit config in tests only when you need a custom override

    Example:
    - `app = create_app()`
    """

    resolved_config = config if config is not None else load_agent_pod_config()
    return create_agent_app(
        registry=REGISTRY,
        config=resolved_config,
    )


app = create_app()
