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
Bridge from legacy `RuntimeContext` to the v2 `BoundRuntimeContext`.

Why this module exists:
- most of the backend request lifecycle still produces the legacy
  `RuntimeContext`
- v2 runtimes should receive the narrower `BoundRuntimeContext`
- keeping this conversion here makes the legacy dependency explicit and easy to
  remove later

How to use it:
- call `build_bound_runtime_context(...)` when one legacy request context must
  be rebound to a v2 runtime

Example:
- `binding = build_bound_runtime_context(user=user, runtime_context=ctx, agent_id="basic.react.v2")`
"""

from __future__ import annotations

import os

from fred_core import KeycloakUser

from agentic_backend.core.agents.runtime_context import RuntimeContext

from ..contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)


def build_bound_runtime_context(
    *,
    user: KeycloakUser,
    runtime_context: RuntimeContext,
    agent_id: str,
    agent_name: str | None = None,
    team_id: str | None = None,
) -> BoundRuntimeContext:
    """
    Convert one legacy `RuntimeContext` into the v2 runtime binding object.

    Why this function exists:
    - the request/session stack still provides `RuntimeContext`
    - v2 runtimes and tools should consume the narrower `BoundRuntimeContext`
    - one shared bridge avoids repeating the legacy-to-v2 mapping in factories
      and controllers

    How to use it:
    - call once when creating or rebinding one v2 session agent

    Example:
    - `binding = build_bound_runtime_context(user=user, runtime_context=ctx, agent_id="internal.react_profile.custodian")`
    """

    tenant = runtime_context.user_id or user.uid or "fred"
    return BoundRuntimeContext(
        runtime_context=runtime_context.model_copy(deep=True),
        portable_context=PortableContext(
            request_id=f"req:{runtime_context.session_id or agent_id}",
            correlation_id=f"corr:{runtime_context.session_id or agent_id}",
            actor=f"user:{user.uid}",
            tenant=tenant,
            environment=_portable_environment_from_env(),
            trace_id=None,
            client_app="fred-ui",
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=runtime_context.session_id,
            user_id=user.uid or runtime_context.user_id,
            user_name=user.username,
            team_id=team_id,
            baggage={},
        ),
    )


def _portable_environment_from_env() -> PortableEnvironment:
    """
    Read the portable runtime environment label from process env.

    Why this function exists:
    - legacy request context does not carry this portable value
    - the v2 binding should still expose a stable environment label to tools and
      downstream services

    How to use it:
    - use only from `build_bound_runtime_context(...)`

    Example:
    - `environment = _portable_environment_from_env()`
    """

    raw = os.getenv("FRED_ENVIRONMENT", "dev").strip().lower()
    if raw == PortableEnvironment.PROD.value:
        return PortableEnvironment.PROD
    if raw == PortableEnvironment.STAGING.value:
        return PortableEnvironment.STAGING
    return PortableEnvironment.DEV
