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

"""`SubAgentCapability` — delegate a prompt to a fresh-context copy of this agent.

What it is, why, and its open limits: README.md and
`docs/swift/rfc/SUBAGENT-CAPABILITY-RFC.md`; the runtime half it drives is
`RUNTIME-EXECUTION-CONTRACT.md` §8.63.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    PortableContext,
    PortableEnvironment,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SUBAGENT_CAPABILITY_ID = "subagent"

# The tool-result `tool_ref` this capability stamps on its results.
_TOOL_REF = "subagent"
_TOOL_NAME = "run_subagent"
# `PortableContext` requires these; the invoker mints the child's real ones.
_REQUEST_ID_PLACEHOLDER = "subagent"

# Delegation hops the tool stays available for. The ceiling is low because each
# level multiplies the turns one pod runs at once — see README.
DEFAULT_MAX_DEPTH = 3
MIN_MAX_DEPTH = 1
MAX_MAX_DEPTH = 5

# Cap on ONE child's answer, in characters, against the parent's 200k history
# budget. Per child, so it does not compose with fan-out — see README.
MAX_SUBAGENT_CONTENT_CHARS = 40_000

# Prepended to the parent's prompt as the child's user message (prompt mode A):
# the child keeps its agent template, so the framing's job is to say that the
# usual audience is not there.
_SUBAGENT_FRAMING = (
    "You are running as a sub-agent: another instance of yourself delegated "
    "this task to you. There is no user in this conversation and no one to ask "
    "— any instruction in your own guidelines about greeting, questioning, or "
    "reporting back to a user does not apply here. Do not ask clarifying "
    "questions; make a reasonable assumption and say which one you made. Tools "
    "that need a human approval are unavailable or will refuse. Answer with "
    "the finished result as text, self-contained, with no preamble: your caller "
    "sees only what you return.\n\n"
    "TASK:\n"
)


class SubAgentConfig(BaseModel):
    """Agent-creation / stored config of the `subagent` capability."""

    max_depth: int = DEFAULT_MAX_DEPTH


def _clamped_max_depth(value: int) -> int:
    """Clamp a stored `max_depth` into its bounds (`platform_postgres` idiom).

    A config written before the bounds existed, or hand-edited past them, must
    not widen the recursion bound the platform is willing to run.
    """

    return max(MIN_MAX_DEPTH, min(MAX_MAX_DEPTH, value))


def _tool_description(remaining_depth: int) -> str:
    """Build the tool description. Every value here may vary by execution
    context but never per turn — RFC §6.3's cache rule."""

    nested = (
        "Your sub-agents can delegate further"
        if remaining_depth > 1
        else "Your sub-agents cannot delegate further"
    )
    return (
        "Delegate one self-contained task to a sub-agent: a fresh copy of "
        "yourself, with your tools but none of this conversation, which runs "
        "the prompt you write and returns its answer as text.\n"
        "Use it for work that would otherwise flood this conversation with "
        "intermediate detail — reading several documents, drafting variants, "
        "investigating separate hypotheses. Do NOT use it for a task you can "
        "answer directly, or for one that needs what has been said here "
        "unless you restate it in the prompt.\n"
        "The sub-agent starts blank: the prompt is everything it will know. "
        "State the goal, the material to work from, and the exact shape of the "
        "answer you want back.\n"
        "Emit ALL independent delegations as separate calls in ONE message — "
        "they then run in parallel; issuing them one after another only makes "
        "the user wait longer. "
        f"{nested} ({remaining_depth} level(s) of delegation remain)."
    )


def _build_run_subagent_tool(
    ctx: CapabilityContext[SubAgentConfig, EmptyModel],
    *,
    remaining_depth: int,
) -> BaseTool:
    """Build `run_subagent` bound to one turn's typed context.

    Hard split: the signature carries only the LLM's `prompt`; the agent id,
    identity and invoker port all come from this closure.
    """

    services = ctx.services
    identity = ctx.identity
    agent_id = identity.agent_id
    if agent_id is None:
        # Never guess: without the calling agent's id there is no "copy of
        # myself" to run (RFC §3.9, never silently degrade).
        raise RuntimeError(
            "subagent: CapabilityIdentity.agent_id is not available on this "
            "execution path; the tool cannot name the agent to re-run."
        )

    async def _run_subagent(prompt: str) -> tuple[str, ToolInvocationResult]:
        invoker = services.agent_invoker
        if invoker is None:
            raise RuntimeError(
                "subagent: RuntimeServices.agent_invoker is not available on "
                "this execution path."
            )
        # Only user/session/team are read: the invoker verifies those against
        # the calling turn and derives everything else from it. The remaining
        # fields are required by the model and carry no meaning here.
        declared_identity = PortableContext(
            request_id=_REQUEST_ID_PLACEHOLDER,
            correlation_id=_REQUEST_ID_PLACEHOLDER,
            actor=identity.user_id,
            tenant="default",
            environment=PortableEnvironment.DEV,
            agent_id=agent_id,
            session_id=identity.session_id,
            user_id=identity.user_id,
            team_id=identity.team_id,
        )
        result = await invoker.invoke(
            AgentInvocationRequest(
                agent_id=agent_id,
                message=f"{_SUBAGENT_FRAMING}{prompt}",
                context=declared_identity,
            )
        )
        if result.is_error:
            message = result.content or "The sub-agent failed with no message."
            logger.info(
                "sub-agent failed agent=%s session=%s: %s",
                agent_id,
                identity.session_id,
                message[:200],
            )
            return (
                f"The sub-agent failed: {message}",
                ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
            )
        if len(result.content) > MAX_SUBAGENT_CONTENT_CHARS:
            too_long = (
                f"The sub-agent's answer was too long ({len(result.content)} "
                f"characters; the limit is {MAX_SUBAGENT_CONTENT_CHARS}). Run "
                "it again with a prompt that asks for a shorter answer, or "
                "split the task across several sub-agents."
            )
            return (
                too_long,
                ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
            )
        logger.info(
            "sub-agent answered agent=%s session=%s chars=%d",
            agent_id,
            identity.session_id,
            len(result.content),
        )
        return result.content, ToolInvocationResult(tool_ref=_TOOL_REF)

    return StructuredTool.from_function(
        coroutine=_run_subagent,
        name=_TOOL_NAME,
        description=_tool_description(remaining_depth),
        response_format="content_and_artifact",
    )


class SubAgentCapability(AgentCapability[SubAgentConfig, SubAgentConfig, EmptyModel]):
    """Run a fresh-context copy of the calling agent against a written prompt.

    No owned table, no router, no chat part: the child's answer arrives on an
    ordinary tool-result line. The whole feature is `run_subagent` plus the
    depth bound that decides whether it is offered at all.
    """

    manifest = CapabilityManifest(
        id=SUBAGENT_CAPABILITY_ID,
        version="0.1.0",
        name="capability.subagent.name",
        description="capability.subagent.description",
        icon="hub",
        kind="tool",
        config_fields=[
            FieldSpec(
                key="max_depth",
                type="number",
                title="capability.subagent.fields.max_depth.title",
                description="capability.subagent.fields.max_depth.description",
                default=DEFAULT_MAX_DEPTH,
                min=MIN_MAX_DEPTH,
                max=MAX_MAX_DEPTH,
            ),
        ],
        # `tools()`-only, so the react+graph default stands. It is designed for
        # ReAct agents; a Graph author calls `context.invoke_agent` directly.
    )
    ConfigModel = SubAgentConfig

    def tools(
        self, ctx: CapabilityContext[SubAgentConfig, EmptyModel]
    ) -> Sequence[BaseTool]:
        """Offer `run_subagent` only while there is depth left to spend.

        Enforcement lives here rather than in the runtime so a leaf child never
        sees a tool it would only be refused — the model is not shown a choice
        it cannot make.
        """

        remaining = _clamped_max_depth(ctx.config.max_depth) - ctx.invocation_depth
        if remaining <= 0:
            return ()
        return (_build_run_subagent_tool(ctx, remaining_depth=remaining),)
