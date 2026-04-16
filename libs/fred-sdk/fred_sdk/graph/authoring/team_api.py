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
TeamAgent authoring primitives for multi-agent coordination.

Why this module exists:
- building multi-agent teams in fred v2 currently requires writing explicit
  graph nodes, edges, and state schemas for every team composition
- this module provides a higher-level abstraction: declare team members with
  their roles and instructions, and let the framework generate the workflow
- the API mirrors the simplicity of team frameworks such as agno: describe
  who is on the team and what they do, then run

Who this module is for:
- agent authors who want to compose specialized agents into a coordinated team
- this is part of the public authoring surface and is designed to be
  pip-installable as a standalone SDK in a future extraction step

SDK extraction note:
- this module depends only on the graph authoring layer (`api.py`) and the
  graph runtime context; it does NOT import runtime internals or Fred platform
  specifics beyond what any graph agent already uses
- when the authoring surface is extracted to a standalone package, this module
  moves with it unchanged

Modes:
- ``sequential`` (default): members run in declaration order; each member is an
  inline LLM call using its ``instructions``; no coordinator LLM is involved,
  making this the cheapest and most deterministic option
- ``dynamic``: a coordinator LLM runs after each member and decides who works
  next, allowing adaptive delegation and early stopping; members are inline LLM
  calls
- ``route``: a coordinator LLM picks exactly one registered agent and delegates
  the full request to it via ``context.invoke_agent``; every ``AgentSpec`` must
  declare an ``agent_ref`` pointing to a registered fred agent; the selected
  agent runs as a real independent agent (with its own tools, prompts, memory)
  rather than as an inline LLM call

Member kinds:

``AgentSpec(name, role, instructions)``
    Inline LLM call.  Used in ``sequential`` and ``dynamic`` modes.  The member
    receives the task plus prior context and produces text output.

``AgentSpec(name, role, agent_ref="v2.my.agent")``
    Real agent invocation.  Required in ``route`` mode; also usable in
    ``sequential`` and ``dynamic`` to delegate a step to a registered agent
    rather than an ad-hoc LLM call.

Example (sequential pipeline with inline members)::

    class CandidateScreeningTeam(TeamAgent):
        agent_id = "sample.candidate_screening_team"
        role = "Screen job candidates through a multi-stage pipeline"
        description = "Parse, match, evaluate, and score each candidate"
        tags = ("team", "screening", "hr")

        members = (
            AgentSpec(
                name="Resume Parser",
                role="Extract structured data from the resume",
                instructions="Parse the resume and output JSON with name, skills, years of experience...",
            ),
            AgentSpec(
                name="Skills Matcher",
                role="Match candidate skills to the job requirements",
                instructions="Compare the parsed skills against requirements and score the match 0-100...",
            ),
        )

Example (route to a registered agent)::

    class SupportRouter(TeamAgent):
        agent_id = "support.router"
        role = "Route support requests to the right specialist agent"
        description = "Reads the request and delegates to the best registered agent"
        tags = ("router", "support")
        mode = "route"
        coordinator_instructions = (
            "You are a support dispatcher.  Read the request and choose the single "
            "most appropriate specialist.  Never try to handle it yourself."
        )

        members = (
            AgentSpec(
                name="Billing Agent",
                role="Handles billing, invoices, and payment questions",
                agent_ref="v2.production.billing_agent",
            ),
            AgentSpec(
                name="Technical Agent",
                role="Handles technical issues, bugs, and configuration",
                agent_ref="v2.production.technical_agent",
            ),
        )

Example (dynamic coordinator with inline members)::

    class ResearchTeam(TeamAgent):
        agent_id = "sample.research_team"
        role = "Research a topic using a flexible team"
        description = "Coordinator routes to the right specialist based on what is still missing"
        tags = ("team", "research")
        mode = "dynamic"
        coordinator_instructions = "Assemble a complete research report. Use the researcher for facts, the writer to synthesize."

        members = (
            AgentSpec(name="Researcher", role="Gather facts and sources", instructions="..."),
            AgentSpec(name="Writer", role="Synthesize into a readable report", instructions="..."),
        )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from ..runtime import GraphNodeContext, GraphNodeResult
from .api import (
    GraphAgent,
    GraphStepHandler,
    GraphWorkflow,
    StepResult,
    finalize_step,
    model_text_step,
    structured_model_step,
    typed_node,
)

__all__ = [
    "AgentSpec",
    "TeamAgent",
    "TeamInput",
    "TeamMemberResult",
    "TeamState",
]


# ---------------------------------------------------------------------------
# Public author-facing types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """
    Declarative description of one team member.

    Why this model exists:
    - authors should describe each specialist in one place without writing
      explicit graph nodes, state updates, or LangGraph wiring
    - this is the fred v2 equivalent of agno's ``Agent(name=, role=, instructions=)``

    How to use it:

    Inline LLM member (used in ``sequential`` and ``dynamic`` modes):

    - set ``name`` to a short human-readable identifier
    - set ``role`` to one sentence describing what this member specialises in
    - set ``instructions`` to the full system prompt the member LLM will receive

    Real agent member (required in ``route`` mode, also usable in other modes):

    - set ``agent_ref`` to the ``agent_id`` of a registered fred agent
    - ``instructions`` is ignored when ``agent_ref`` is set; the registered
      agent runs with its own configured prompts and tools

    Example (inline LLM member)::

        AgentSpec(
            name="Technical Writer",
            role="Synthesise all research into a polished blog post",
            instructions="You are a senior technical writer. Use all provided research...",
        )

    Example (registered agent member)::

        AgentSpec(
            name="SQL Analyst",
            role="Answers questions by querying databases",
            agent_ref="v2.production.sql_analyst",
        )
    """

    name: str
    """Short human-readable identifier, e.g. ``"Technical Researcher"``."""

    role: str
    """One-sentence capability description shown to the coordinator and peers."""

    instructions: str = ""
    """
    Full system prompt this member receives when it runs as an inline LLM call.
    Ignored when ``agent_ref`` is set.
    """

    agent_ref: str | None = None
    """
    Registered fred agent id to invoke instead of an inline LLM call.

    When set, the member step calls ``context.invoke_agent(agent_ref, message)``
    so the full registered agent (with its tools, prompts, and memory) handles
    the request.  Required for all members in ``route`` mode.
    """


class TeamMemberResult(BaseModel):
    """
    One member's contribution captured in the shared team state.

    Why this model exists:
    - each member appends its output here so that subsequent members can read
      the work already done without needing to parse raw message history

    How to use it:
    - read ``results`` from ``TeamState`` to inspect prior member outputs
    - this model is populated automatically by the team framework
    """

    agent_name: str
    """The ``AgentSpec.name`` of the member that produced this result."""

    output: str
    """The full text output produced by this member."""


class TeamInput(BaseModel):
    """
    Input model for all TeamAgent subclasses.

    Why this model exists:
    - all team agents share the same single-message input contract
    - authors should not need to redefine this for routine team compositions

    How to use it:
    - this is set automatically on ``TeamAgent`` subclasses; do not declare it
      manually unless you need to extend the input schema
    """

    message: str
    """The task or question sent to the team."""


class TeamState(BaseModel):
    """
    Shared workflow state for all TeamAgent subclasses.

    Why this model exists:
    - all members read and write the same state so that later members can see
      what earlier members produced

    How to use it:
    - ``user_message`` holds the original task unchanged throughout the workflow
    - ``results`` accumulates one entry per member that has already run
    - ``final_text`` is updated by each member and read by ``build_output``

    Authors should not need to interact with this model directly; it is
    populated automatically by the team framework.
    """

    user_message: str
    """The original user task, copied from ``TeamInput.message``."""

    results: list[TeamMemberResult] = Field(default_factory=list)
    """Accumulated outputs from members that have already run."""

    final_text: str = ""
    """Most recent member output; used by ``GraphAgent.build_output``."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _node_id(name: str) -> str:
    """Return a deterministic LangGraph-safe node id for a member name."""
    return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def _format_prior_results(results: list[TeamMemberResult]) -> str:
    """Format accumulated member results into a readable context block."""
    if not results:
        return ""
    parts = [f"### {r.agent_name}\n{r.output}" for r in results]
    return "\n\n".join(parts)


def _make_member_step(spec: AgentSpec) -> GraphStepHandler:
    """
    Build a typed graph node that runs one AgentSpec as an LLM call.

    Why this helper exists:
    - each member node follows the same pattern: read prior context, call the
      model with the member's instructions, append the result to state
    - extracting this into a factory keeps the workflow builders concise

    How to use it:
    - called automatically by ``_build_sequential_workflow`` and
      ``_build_dynamic_workflow``; not intended for direct use
    """
    node_name = _node_id(spec.name)
    operation = f"team_member_{node_name}"

    @typed_node(TeamState)
    async def _step(state: TeamState, context: GraphNodeContext) -> StepResult:
        context.emit_status(spec.name, detail=spec.role)

        prior_context = _format_prior_results(state.results)
        user_prompt = f"Task: {state.user_message}"
        if prior_context:
            user_prompt = (
                f"{user_prompt}\n\n"
                f"Work already completed by your teammates:\n\n{prior_context}"
            )

        output = await model_text_step(
            context,
            operation=operation,
            system_prompt=f"Your role: {spec.role}\n\n{spec.instructions}",
            user_prompt=user_prompt,
            fallback_text=f"[{spec.name} produced no output]",
        )

        new_result = TeamMemberResult(agent_name=spec.name, output=output)
        updated_results = list(state.results) + [new_result]

        return StepResult(
            state_update={
                "results": updated_results,
                # Keep final_text pointing at the most recent member output so
                # that GraphAgent.build_output always has something to return.
                "final_text": output,
            }
        )

    # Give the inner function a stable name for tracing and debugging.
    _step.__name__ = f"member_{node_name}_step"
    _step.__qualname__ = f"member_{node_name}_step"
    return _step


def _make_finalize_step() -> GraphStepHandler:
    """
    Build a terminal node that preserves the final text already in state.

    Why this helper exists:
    - both workflow modes need a terminal node that the graph can route to
    - ``finalize_step`` from ``api.py`` handles the "already set" case cleanly
    """

    @typed_node(TeamState)
    async def _finalize(state: TeamState, context: GraphNodeContext) -> GraphNodeResult:
        return finalize_step(
            final_text=state.final_text,
            fallback_text="The team completed the task.",
        )

    return _finalize


def _make_agent_invoke_step(spec: AgentSpec) -> GraphStepHandler:
    """
    Build a typed graph node that delegates to a registered fred agent.

    Why this helper exists:
    - ``route`` mode members are real registered agents, not inline LLM calls
    - the invocation goes through ``context.invoke_agent`` so the target agent
      runs with its own tools, prompts, memory, and streaming events
    - extracting this keeps ``_build_route_workflow`` readable

    How to use it:
    - called automatically by ``_build_route_workflow``; not intended for direct use
    - ``spec.agent_ref`` must be set before calling this helper
    """
    assert spec.agent_ref is not None, (
        f"AgentSpec '{spec.name}' must have agent_ref set"
    )
    agent_ref = spec.agent_ref
    node_name = _node_id(spec.name)

    @typed_node(TeamState)
    async def _step(state: TeamState, context: GraphNodeContext) -> StepResult:
        context.emit_status(spec.name, detail=spec.role)
        result = await context.invoke_agent(
            agent_id=agent_ref,
            message=state.user_message,
        )
        output = (
            result.content
            if not result.is_error
            else f"[{spec.name} returned an error: {result.content}]"
        )
        new_result = TeamMemberResult(agent_name=spec.name, output=output)
        return StepResult(
            state_update={
                "results": list(state.results) + [new_result],
                "final_text": output,
            }
        )

    _step.__name__ = f"agent_{node_name}_step"
    _step.__qualname__ = f"agent_{node_name}_step"
    return _step


def _make_route_coordinator_step(
    members: tuple[AgentSpec, ...], coordinator_instructions: str
) -> GraphStepHandler:
    """
    Build the coordinator node for ``route`` mode.

    Why this differs from the dynamic coordinator:
    - ``route`` mode picks exactly one member and never loops back
    - the coordinator prompt is simpler: pick the single best agent and stop

    How to use it:
    - called automatically by ``_build_route_workflow``
    """
    member_list_text = "\n".join(f"- {spec.name}: {spec.role}" for spec in members)
    member_names = [spec.name for spec in members]

    system_prompt = (
        f"{coordinator_instructions}\n\n"
        f"You are a request router.  Available specialists:\n"
        f"{member_list_text}\n\n"
        f"Read the request and choose the single most appropriate specialist.\n"
        f'Output valid JSON: {{"next_member": "<exact name from the list above>", "reasoning": "<one sentence>"}}'
    )

    @typed_node(TeamState)
    async def _coordinator(state: TeamState, context: GraphNodeContext) -> StepResult:
        fallback = _CoordinatorDecision(
            next_member=member_names[0],
            reasoning="fallback: first member",
        )
        decision = await structured_model_step(
            context,
            operation="team_route_coordinator",
            output_model=_CoordinatorDecision,
            system_prompt=system_prompt,
            user_prompt=f"Request: {state.user_message}\n\nWhich specialist should handle this?",
            fallback_output=fallback,
        )
        route = decision.next_member
        if route not in member_names:
            route = member_names[0]
        return StepResult(route_key=_node_id(route))

    return _coordinator


def _build_route_workflow(
    members: tuple[AgentSpec, ...],
    coordinator_instructions: str,
) -> GraphWorkflow:
    """
    Build a routing workflow: coordinator picks one agent, invokes it, done.

    Graph topology:
        coordinator → agent_X → finalize
                    → agent_Y → finalize
                    → …

    Why this mode exists:
    - some teams are pure dispatchers: they read the request and delegate to the
      single most appropriate registered agent
    - the selected agent runs as a real independent agent (tools, prompts, memory)
      rather than as an inline LLM call
    - this requires ``agent_ref`` on every ``AgentSpec``

    How to use it:
    - called automatically when ``TeamAgent.mode == "route"``
    """
    if not members:
        raise ValueError("TeamAgent requires at least one AgentSpec member.")
    for spec in members:
        if spec.agent_ref is None:
            raise ValueError(
                f"AgentSpec '{spec.name}' must declare an agent_ref in route mode. "
                f"Set agent_ref to the registered agent id, e.g. agent_ref='v2.my.agent'."
            )

    nodes: dict[str, GraphStepHandler] = {}
    edges: dict[str, str] = {}
    route_map: dict[str, str] = {}

    nodes["coordinator"] = _make_route_coordinator_step(
        members, coordinator_instructions
    )

    for spec in members:
        node_id = _node_id(spec.name)
        nodes[node_id] = _make_agent_invoke_step(spec)
        edges[node_id] = "finalize"
        route_map[node_id] = node_id

    nodes["finalize"] = _make_finalize_step()

    return GraphWorkflow(
        entry="coordinator",
        nodes=nodes,
        edges=edges,
        routes={"coordinator": route_map},
    )


def _build_sequential_workflow(members: tuple[AgentSpec, ...]) -> GraphWorkflow:
    """
    Build a sequential pipeline: member_0 → member_1 → … → member_n → finalize.

    Why this helper exists:
    - many team compositions are simple ordered pipelines where each specialist
      hands off to the next; no coordinator LLM is needed
    - this produces the cheapest possible workflow: N+1 LLM calls, deterministic
      ordering, no routing overhead

    How to use it:
    - called automatically when ``TeamAgent.mode == "sequential"``
    """
    if not members:
        raise ValueError("TeamAgent requires at least one AgentSpec member.")

    node_ids = [_node_id(spec.name) for spec in members]
    nodes: dict[str, GraphStepHandler] = {}
    edges: dict[str, str] = {}

    for spec, node_id in zip(members, node_ids):
        nodes[node_id] = _make_member_step(spec)

    # Chain member nodes in declaration order.
    for i in range(len(node_ids) - 1):
        edges[node_ids[i]] = node_ids[i + 1]

    # Terminal finalize node after the last member.
    nodes["finalize"] = _make_finalize_step()
    edges[node_ids[-1]] = "finalize"

    return GraphWorkflow(
        entry=node_ids[0],
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Dynamic coordinator (used when mode == "dynamic")
# ---------------------------------------------------------------------------


class _CoordinatorDecision(BaseModel):
    """Internal structured output for the coordinator routing decision."""

    next_member: str
    """Name of the next AgentSpec to run, or the literal string ``"done"``."""

    reasoning: str
    """Brief explanation of why this member was chosen (for tracing)."""


def _make_coordinator_step(
    members: tuple[AgentSpec, ...],
    coordinator_instructions: str,
) -> GraphStepHandler:
    """
    Build the coordinator node that decides which member runs next.

    Why this helper exists:
    - the coordinator is an LLM that reads the task, sees what has been done,
      and picks the next specialist or declares the task finished
    - extracting this keeps ``_build_dynamic_workflow`` readable

    How to use it:
    - called automatically when ``TeamAgent.mode == "dynamic"``
    """
    member_names = [spec.name for spec in members]
    member_list_text = "\n".join(f"- {spec.name}: {spec.role}" for spec in members)

    system_prompt = (
        f"{coordinator_instructions}\n\n"
        f"You coordinate a team of specialists. Available members:\n"
        f"{member_list_text}\n\n"
        f"After each member completes their work, decide who should work next.\n"
        f"When the task is fully complete, set next_member to the exact string "
        f'"done".\n'
        f"Always output valid JSON matching the schema: "
        f'{{"next_member": "<name or done>", "reasoning": "<brief reason>"}}.'
    )

    @typed_node(TeamState)
    async def _coordinator(state: TeamState, context: GraphNodeContext) -> StepResult:
        prior_context = _format_prior_results(state.results)
        user_prompt = (
            f"Task: {state.user_message}\n\n"
            + (
                f"Work completed so far:\n{prior_context}"
                if prior_context
                else "No work has been done yet."
            )
            + "\n\nWho should work next, or is the task done?"
        )

        # Fallback: follow declaration order, then stop.
        n_done = len(state.results)
        fallback_next = member_names[n_done] if n_done < len(member_names) else "done"
        fallback = _CoordinatorDecision(
            next_member=fallback_next,
            reasoning="fallback: sequential order",
        )

        decision = await structured_model_step(
            context,
            operation="team_coordinator",
            output_model=_CoordinatorDecision,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_output=fallback,
        )

        # Guard: only accept known member names or "done".
        route = decision.next_member
        if route not in member_names and route != "done":
            route = fallback_next

        return StepResult(route_key=_node_id(route) if route != "done" else "done")

    return _coordinator


def _build_dynamic_workflow(
    members: tuple[AgentSpec, ...],
    coordinator_instructions: str,
) -> GraphWorkflow:
    """
    Build a coordinator-driven workflow:
    coordinator → member_X → coordinator → … → finalize.

    Why this helper exists:
    - some tasks need adaptive routing: the coordinator LLM decides which
      specialist runs next after seeing what has already been done
    - this allows out-of-order execution, early stopping, and member re-use

    How to use it:
    - called automatically when ``TeamAgent.mode == "dynamic"``
    """
    if not members:
        raise ValueError("TeamAgent requires at least one AgentSpec member.")

    nodes: dict[str, GraphStepHandler] = {}
    edges: dict[str, str] = {}
    routes: dict[str, dict[str, str]] = {}

    # Coordinator node routes to any member or to finalize.
    nodes["coordinator"] = _make_coordinator_step(members, coordinator_instructions)
    routes["coordinator"] = {
        _node_id(spec.name): _node_id(spec.name) for spec in members
    }
    routes["coordinator"]["done"] = "finalize"

    # Each member node returns to the coordinator unconditionally.
    for spec in members:
        node_id = _node_id(spec.name)
        nodes[node_id] = _make_member_step(spec)
        edges[node_id] = "coordinator"

    # Terminal finalize node.
    nodes["finalize"] = _make_finalize_step()

    return GraphWorkflow(
        entry="coordinator",
        nodes=nodes,
        edges=edges,
        routes=routes,
    )


# ---------------------------------------------------------------------------
# Public base class
# ---------------------------------------------------------------------------


class TeamAgent(GraphAgent):
    """
    Authoring base class for multi-agent teams.

    Why this class exists:
    - coordinating a group of specialised agents requires graph nodes, state
      schemas, and routing wiring that repeats across every team composition
    - ``TeamAgent`` removes that ceremony: declare members, pick a mode, run

    How to use it:
    - subclass ``TeamAgent`` and set ``agent_id``, ``role``, ``description``,
      ``tags``, and ``members``
    - optionally set ``mode`` (default ``"sequential"``) and
      ``coordinator_instructions`` (required when ``mode == "dynamic"``)
    - the framework generates ``input_schema``, ``state_schema``, ``workflow``,
      and ``input_to_state`` automatically from the member declarations
    - do NOT declare these class variables manually on a ``TeamAgent`` subclass

    Modes:

    ``sequential`` (default)
        Members run in declaration order. Every member receives the original
        task plus all prior member outputs. No coordinator LLM call is made
        between members, making this the cheapest and most predictable option.
        Ideal for ordered pipelines such as parse → evaluate → score.

    ``dynamic``
        A coordinator LLM runs after each member and decides who works next
        (or declares the task done). Set ``coordinator_instructions`` to guide
        the coordinator's strategy. Ideal when the order depends on the task.

    SDK extraction note:
        This class belongs to the public authoring surface. It does not import
        Fred platform internals and is safe to move to a standalone SDK package.

    Example (sequential pipeline)::

        class CandidateScreeningTeam(TeamAgent):
            agent_id = "sample.candidate_screening_team"
            role = "Screen candidates through a four-stage pipeline"
            description = "Parse, match, evaluate, then score each candidate"
            tags = ("team", "hr", "screening")

            members = (
                AgentSpec(
                    name="Resume Parser",
                    role="Extract structured data from the resume",
                    instructions="Parse the resume and return JSON...",
                ),
                AgentSpec(
                    name="Scorer",
                    role="Produce a final recommendation",
                    instructions="Use the previous analysis to score the candidate...",
                ),
            )

    Example (dynamic coordinator)::

        class TechBlogTeam(TeamAgent):
            agent_id = "sample.techblog_team"
            role = "Write technical blog posts"
            description = "Research, generate examples, then write the post"
            tags = ("team", "writing")
            mode = "dynamic"
            coordinator_instructions = "Produce a complete, publication-ready blog post."

            members = (
                AgentSpec(name="Researcher", role="Find facts and examples", instructions="..."),
                AgentSpec(name="Writer", role="Write the final article", instructions="..."),
            )
    """

    members: ClassVar[tuple[AgentSpec, ...]] = ()
    """Team members in declaration order. Required on every concrete subclass."""

    coordinator_instructions: ClassVar[str] = ""
    """
    High-level goal given to the coordinator LLM in ``dynamic`` mode.

    Ignored in ``sequential`` mode. Describe the overall objective and any
    sequencing hints you want the coordinator to follow.
    """

    mode: ClassVar[Literal["sequential", "dynamic", "route"]] = "sequential"
    """
    Workflow mode. ``"sequential"`` runs members in order; ``"dynamic"``
    uses a coordinator LLM to decide the next member after each step;
    ``"route"`` picks exactly one registered agent via ``context.invoke_agent``.
    """

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        """
        Auto-generate the graph workflow from the declared members.

        Why this hook exists:
        - Pydantic calls this after the subclass is fully constructed, giving
          us a clean place to derive ``input_schema``, ``state_schema``,
          ``input_to_state``, and ``workflow`` from ``members`` and ``mode``
        - authors should never need to call or override this method
        """
        super().__pydantic_init_subclass__(**kwargs)

        # Skip the abstract base itself (members is empty).
        if not cls.members:
            return

        # Use setattr to assign ClassVar attributes on the subclass; direct
        # attribute assignment on cls triggers a type-checker false positive
        # because __pydantic_init_subclass__ receives cls typed as an instance.
        setattr(cls, "input_schema", TeamInput)
        setattr(cls, "state_schema", TeamState)
        setattr(cls, "input_to_state", {"message": "user_message"})

        if cls.mode == "sequential":
            setattr(cls, "workflow", _build_sequential_workflow(cls.members))
        elif cls.mode == "dynamic":
            setattr(
                cls,
                "workflow",
                _build_dynamic_workflow(cls.members, cls.coordinator_instructions),
            )
        elif cls.mode == "route":
            setattr(
                cls,
                "workflow",
                _build_route_workflow(cls.members, cls.coordinator_instructions),
            )
        else:
            raise ValueError(
                f"TeamAgent.mode must be 'sequential', 'dynamic', or 'route', got {cls.mode!r}."
            )
