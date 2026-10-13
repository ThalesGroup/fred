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
Relay a creation assistant request ("draft my agent") to the template's pod.

The control plane only narrows the offered capabilities to the ones the team
may use on that template; the pod owns the model call and reads the admin
settings back from `creation_assistant_runtime_settings`. Acceptance:
openspec/changes/add-agent-creation-assistant/.
"""

from __future__ import annotations

import logging

import httpx
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_sdk.contracts.agent_draft import (
    AgentDraftPodRequest,
    AgentDraftRequest,
    AgentDraftResult,
    CreationAssistantRuntimeSettings,
)
from pydantic import ValidationError

from control_plane_backend.capabilities.authz import (
    filter_entries_by_usable,
    usable_capability_ids,
)
from control_plane_backend.platform_prompt.service import (
    resolve_creation_assistant_settings,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.service import (
    EnrollmentError,
    _resolve_enrollable_template,
)

logger = logging.getLogger(__name__)

# A little above the pod's own 50 s model deadline, below common 60 s ingress
# read timeouts. The pool wait stays short: the client is shared with other calls.
_POD_TIMEOUT = httpx.Timeout(55.0, connect=5.0, pool=5.0)


async def draft_agent(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    template_id: str,
    request: AgentDraftRequest,
    deps: ProductServiceDependencies,
    authorization: str | None,
) -> AgentDraftResult:
    """Forward to the template's pod, offering only capabilities the team may use."""
    source, template = await _resolve_enrollable_template(
        user=user, team_id=team_id, template_id=template_id, deps=deps
    )
    usable = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
    allowed = {
        entry.id
        for entry in filter_entries_by_usable(template.available_capabilities, usable)
    }
    # The client names and describes them in the user's language; the ids are
    # what must be trusted, so anything else is dropped here.
    candidates = [c for c in request.capabilities if c.id in allowed]
    body = AgentDraftPodRequest(
        **request.model_dump(exclude={"capabilities"}),
        capabilities=candidates,
        team_id=str(team_id),
    )
    url = f"{source.base_url.rstrip('/')}/agents/creation-assistant/draft"
    headers = {"Authorization": authorization} if authorization else None
    try:
        response = await deps.get_runtime_http_client().post(
            url,
            json=body.model_dump(mode="json"),
            headers=headers,
            timeout=_POD_TIMEOUT,
        )
    except httpx.PoolTimeout as exc:
        raise EnrollmentError(
            "The control plane is busy and could not reach the agent runtime. "
            "Please try again.",
            http_status=503,
        ) from exc
    except httpx.TimeoutException as exc:
        raise EnrollmentError(
            "The agent runtime took too long to draft the agent. Please try again.",
            http_status=504,
        ) from exc
    except httpx.RequestError as exc:
        raise EnrollmentError(
            f"Agent runtime service at {source.base_url} is not reachable to "
            "draft the agent.",
            http_status=503,
        ) from exc
    if response.status_code in (403, 422, 503, 504):
        raise EnrollmentError(_pod_detail(response), http_status=response.status_code)
    if response.status_code == 404:
        # A pod built before this operation existed, or a wrong base_url.
        logger.info(
            "[control-plane][creation-assistant] runtime %s answered 404",
            source.runtime_id,
        )
        raise EnrollmentError(
            "This agent's runtime does not support creation assistant yet.",
            http_status=501,
        )
    if response.status_code >= 400:
        logger.info(
            "[control-plane][creation-assistant] runtime %s answered %s",
            source.runtime_id,
            response.status_code,
        )
        # A pod 401 is a platform credential problem, not the browser session's,
        # so it must not reach the client as a 401.
        raise EnrollmentError(
            "The agent runtime refused the request's credentials."
            if response.status_code == 401
            else "The agent runtime could not draft the agent. Please try again.",
            http_status=502,
        )
    try:
        result = AgentDraftResult.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise EnrollmentError(
            "The agent runtime returned a malformed draft.", http_status=502
        ) from exc
    # Defence in depth: never recommend something the team could not enable.
    offered = {c.id for c in candidates}
    return result.model_copy(
        update={"capability_ids": [i for i in result.capability_ids if i in offered]}
    )


async def creation_assistant_runtime_settings(
    deps: ProductServiceDependencies,
) -> CreationAssistantRuntimeSettings:
    """The saved admin settings as the pod applies them; None fields use the
    pod defaults. The caller's team access is checked by the route."""
    stored = await resolve_creation_assistant_settings(deps)
    if stored is None:
        return CreationAssistantRuntimeSettings()
    return CreationAssistantRuntimeSettings(
        creation_assistant_prompt=stored.text,
        model_profile_id=stored.model_profile_id,
        reasoning_effort=stored.reasoning_effort,
    )


def _pod_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, list):  # FastAPI validation errors
        detail = "; ".join(
            str(item.get("msg", item)) if isinstance(item, dict) else str(item)
            for item in detail
        )
    return str(detail or response.text or response.reason_phrase)
