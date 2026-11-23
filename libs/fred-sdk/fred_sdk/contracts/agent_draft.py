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

"""Creation assistant request/result and private Weaver admission, without an instance."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .weaver import InferenceAdmission, ResolverFact, RuntimeSpace

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

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class AgentDraftRequest(BaseModel):
    """What the user wants their agent to do, plus the capabilities on offer."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

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
    """Requested destination and template, verified by private Control Plane admission."""

    space_id: UUID
    template_id: UUID


class AgentDraftAdmission(ResolverFact):
    """Server-only facts for one draft; no conversation, instance or tool authority."""

    subject_id: str
    run_id: str
    space: RuntimeSpace
    template_id: UUID
    runtime_id: str
    template_key: str
    prompt_key: str
    capability_ids: tuple[str, ...]
    creation_prompt: str | None
    inference: InferenceAdmission


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
