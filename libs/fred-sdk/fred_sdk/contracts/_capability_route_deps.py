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
FastAPI dependencies for capability routers, kept out of `runtime.py` so fred-sdk
imports no fastapi until a capability router asks for one. Public paths:
`fred_sdk.contracts.runtime.capability_team_authorizer` and
`fred_sdk.contracts.runtime.capability_platform_model`.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from .runtime import (
    CAPABILITY_PLATFORM_MODEL_STATE,
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelPort,
    CapabilityTeamAuthorizer,
)


async def capability_team_authorizer(request: Request) -> CapabilityTeamAuthorizer:
    """FastAPI dependency for capability routers: the caller's team authorizer.

    Fails closed (503) on a pod that did not bind one.
    """
    authorizer = getattr(request.state, CAPABILITY_TEAM_AUTHORIZER_STATE, None)
    if not isinstance(authorizer, CapabilityTeamAuthorizer):
        raise HTTPException(
            status_code=503, detail="Team authorization is not available."
        )
    return authorizer


async def capability_platform_model(request: Request) -> CapabilityModelPort:
    """FastAPI dependency for capability routers: a model port bound to no team,
    for platform-wide work a capability manager starts. Without a team, no
    usable-models restriction applies. Fails closed (503) on a pod without one.
    """
    port = getattr(request.state, CAPABILITY_PLATFORM_MODEL_STATE, None)
    if not isinstance(port, CapabilityModelPort):
        raise HTTPException(
            status_code=503, detail="Platform model access is not available."
        )
    return port
