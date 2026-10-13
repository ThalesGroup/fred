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
Wire contract of the agent creation assistant.

The control plane receives `AgentDraftRequest` from the agent form,
narrows its capabilities to the ones the team may use, and forwards it to the
template's pod as `AgentDraftPodRequest`. The pod reads the admin settings
(`CreationAssistantRuntimeSettings`) from the control plane itself.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The admin's reasoning choice for the assistant's call; "off" strips reasoning.
CreationAssistantReasoningEffort = Literal["off", "low", "medium", "high"]
MAX_AGENT_DRAFT_DESCRIPTION_CHARS = 4000
MAX_CREATION_ASSISTANT_PROMPT_CHARS = 20_000
# Hard caps on drafted values, below the agent form's 255 / 255 / 500 so a
# draft always fits; the meta-prompt asks for much shorter values.
MAX_DRAFT_NAME_CHARS = 60
MAX_DRAFT_ROLE_CHARS = 120
MAX_DRAFT_DESCRIPTION_CHARS = 300
# Generous: a template rarely offers more than a few dozen capabilities.
MAX_DRAFT_CAPABILITIES = 500


class AgentDraftCapabilityCandidate(BaseModel):
    """One capability the creation assistant may recommend, in the user's language."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class AgentDraftRequest(BaseModel):
    """What the user wants their agent to do, plus the capabilities on offer."""

    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(
        min_length=1,
        max_length=MAX_AGENT_DRAFT_DESCRIPTION_CHARS,
        description="The user's own words: role, mission, audience, constraints.",
    )
    language: str = Field(
        default="en",
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$",
        description="UI language (BCP 47, e.g. 'fr', 'en'); the prompt is written in it.",
    )
    agent_name: str | None = Field(default=None, max_length=200)
    agent_role: str | None = Field(default=None, max_length=500)
    capabilities: list[AgentDraftCapabilityCandidate] = Field(
        default_factory=list, max_length=MAX_DRAFT_CAPABILITIES
    )


class AgentDraftPodRequest(AgentDraftRequest):
    """The pod-side body: the control plane adds the canonical team id.

    It carries no admin setting: a pod is reachable from browsers, so it reads
    them from the control plane with the caller's token instead."""

    team_id: str = Field(min_length=1)


class CreationAssistantRuntimeSettings(BaseModel):
    """The admin settings a pod applies to a draft; None uses the pod default."""

    creation_assistant_prompt: str | None = Field(
        default=None, max_length=MAX_CREATION_ASSISTANT_PROMPT_CHARS
    )
    model_profile_id: str | None = Field(
        default=None,
        max_length=200,
        description="Chat profile; one unknown to the pod uses the pod default.",
    )
    reasoning_effort: CreationAssistantReasoningEffort = Field(
        default="off",
        description=(
            "Reasoning of the assistant's own call. The pod clamps it to the "
            "profile: any non-'off' value means on for an on/off profile, the "
            "nearest declared level otherwise."
        ),
    )


class AgentDraftResult(BaseModel):
    """A drafted agent: short identity fields, system prompt, capabilities."""

    name: str | None = Field(default=None, max_length=MAX_DRAFT_NAME_CHARS)
    role: str | None = Field(default=None, max_length=MAX_DRAFT_ROLE_CHARS)
    description: str | None = Field(
        default=None,
        max_length=MAX_DRAFT_DESCRIPTION_CHARS,
        description="One sentence; None when the model gave none.",
    )
    system_prompt: str
    capability_ids: list[str] = Field(
        default_factory=list,
        description="Recommended capabilities, always a subset of the request's.",
    )
