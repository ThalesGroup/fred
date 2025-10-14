# app/agents/leader/leader.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import logging
from collections import deque
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Literal, Sequence

from fred_core import get_model, get_structured_chain
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.constants import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

from app.agents.leader.structures.decision import ExecuteDecision, PlanDecision
from app.agents.leader.structures.plan import Plan
from app.agents.leader.structures.state import State
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# -----------------------------
# Spec-only tuning (class-level)
# -----------------------------
# Dev note:
# - This is a *schema* for the UI, not the live values. Live (overridden) values are
#   provided at runtime via AgentSettings.tuning and applied by AgentFlow.__init__.
LEADER_TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="Leader System Prompt",
            description=(
                "Sets Fred’s leadership persona and guardrails: plan minimally, route deterministically, "
                "avoid loops, summarize without inventing facts."
            ),
            required=True,
            default=(
                "You are Fred, a pragmatic team leader. Plan the SHORTEST path to the answer, route to the most "
                "appropriate expert, supervise execution, validate succinctly, and deliver a clear final answer.\n"
                "- Prefer 1-step plans when sufficient.\n"
                "- Be deterministic and avoid re-planning loops.\n"
                "- Never invent facts beyond what experts produced.\n"
                "- When you must choose, prioritize correctness and brevity."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="routing.prompts.choose_expert",
            type="prompt",
            title="Choose-Expert Prompt",
            description=(
                "LLM tie-breaker when multiple experts are plausible. "
                "MUST return exactly one expert name from {options}."
            ),
            required=True,
            default=(
                "Objective: {objective}\n"
                "Step {step_number}: {step}\n"
                "Choose the best expert from: {options}.\n"
                "Answer with only the expert name."
            ),
            ui=UIHints(group="Routing", multiline=True, markdown=False),
        ),
        FieldSpec(
            key="routing.top_k",
            type="integer",
            title="Routing Top-K",
            description="How many top candidates to present to the tie-breaker prompt.",
            required=False,
            default=2,
            ui=UIHints(group="Routing"),
        ),
    ],
)


# ---------------
# UI “thoughts”
# ---------------
def mk_thought(
    *, label: str, node: str, task: str, content: str, extras: dict | None = None
) -> AIMessage:
    """Emit a zero-token assistant-side 'thought' that the UI renders in a dedicated lane."""
    md = {"thought": content, "extras": {"label": label, "node": node, "task": task}}
    if extras:
        md["extras"].update(extras)
    return AIMessage(content="", response_metadata=md)


def _ensure_metadata_dict(msg: BaseMessage) -> dict:
    md = getattr(msg, "response_metadata", None) or {}
    if not isinstance(md, dict):
        md = {}
    msg.response_metadata = md
    return md


def _normalize_choice(raw: str, options: list[str]) -> str | None:
    """Make the LLM tie-breaker robust to trivial capitalization/spacing issues."""
    if not raw:
        return None
    raw = raw.strip()
    if raw in options:
        return raw
    lower_map = {o.lower(): o for o in options}
    if raw.lower() in lower_map:
        return lower_map[raw.lower()]
    match = get_close_matches(raw, options, n=1, cutoff=0.6)
    return match[0] if match else None


# -------------------------
# Deterministic pre-router
# -------------------------
@dataclass(frozen=True)
class ExpertProfile:
    """
    Hard priors for routing—cheap, stable, explainable.
    Leader uses this first; LLM only breaks ties among top-K (configurable).
    """

    name: str
    categories: tuple[str, ...]
    keywords: tuple[
        str, ...
    ]  # substring hints from description or explicit agent hints
    live_ok: bool  # False for theoretical-only agents
    cost_hint: int  # 1=cheap..3=expensive (tie-break)
    latency_hint: int  # 1=fast..3=slow (tie-break)


# ========
# Leader
# ========
@expose_runtime_source("agent.Appollo")
class Appollo(AgentFlow):
    """
    This is the legacy fred leader. Why legacy? because we are introducing a new version soon
    that will be much more effective. COnsider this class as a useful example
    Fred = plan → supervise → execute → validate → respond, with expert routing.

    Design mirrors AgentFlow best practices:
    - tuning (spec) is class-level → UI contract
    - per-instance wiring happens in async_init() → binds model, builds `self._graph`, sets chains
    - NO automatic prompt composition: each node explicitly chooses the tuned text it needs
    """

    tuning = LEADER_TUNING  # spec only; live values come from AgentSettings.tuning

    # --- lifecycle / bootstrap ------------------------------------------------
    async def async_init(self):
        """
        Bind model, set up registries & chains, and build the LangGraph.
        This is per-instance because nodes call bound methods and can depend on runtime state.
        """
        # Deterministic-ish model for routing/validation
        self.model = get_model(self.agent_settings.model)
        try:
            self.model = self.model.bind(temperature=0, top_p=1)
        except Exception:
            logger.warning(
                "Leader: provider does not support temperature/top_p bind; using defaults."
            )

        # Routing / supervision settings
        self.max_steps = 5
        self.experts: dict[str, AgentFlow] = {}
        self.compiled_expert_graphs: dict[str, CompiledStateGraph] = {}
        self.expert_index: dict[str, ExpertProfile] = {}
        self.max_replans: int = min(self.max_steps or 6, 3)
        self._replans_done: int = 0
        self._decision_history = deque(maxlen=6)
        self._last_progress_hash: str | None = None

        # Graph + typed, structured chains (all consume {"messages":[...]} uniformly)
        self._graph = self._build_graph()
        if self.agent_settings.model is None:
            raise ValueError("Leader requires agent_settings.model to build chains.")
        self.plan_chain = get_structured_chain(Plan, self.agent_settings.model)
        self.exec_decision_chain = get_structured_chain(
            ExecuteDecision, self.agent_settings.model
        )
        self.plan_decision_chain = get_structured_chain(
            PlanDecision, self.agent_settings.model
        )

    # --- expert registry ------------------------------------------------------
    def reset_experts(self) -> None:
        logger.info("Leader: resetting experts (was: %s)", list(self.experts.keys()))
        self.experts.clear()
        self.compiled_expert_graphs.clear()
        self.expert_index.clear()

    def add_expert(
        self, name: str, instance: AgentFlow, compiled_graph: CompiledStateGraph
    ) -> None:
        """
        Register an expert, its compiled graph, and its deterministic routing profile.
        """
        self.experts[name] = instance
        self.compiled_expert_graphs[name] = compiled_graph

        # Prefer explicit routing hints; else derive shallow keywords from description
        keywords = tuple(
            (getattr(instance, "routing_keywords", []) or [])
            or (instance.get_description() or "").lower().split()[:8]
        )
        profile = ExpertProfile(
            name=name,
            categories=tuple(instance.get_tags() or ()),
            keywords=keywords,
            live_ok=bool(getattr(instance, "live_ok", True)),
            cost_hint=int(getattr(instance, "cost_hint", 2)),
            latency_hint=int(getattr(instance, "latency_hint", 2)),
        )
        self.expert_index[name] = profile

    # --- graph definition -----------------------------------------------------
    def _build_graph(self) -> StateGraph:
        """
        Keep graph construction separate for readability.
        Compiled once via AgentFlow.get_compiled_graph().
        """
        builder = StateGraph(State)
        builder.add_node("planning", self.plan)
        builder.add_node("supervise", self.supervise)
        builder.add_node("execute", self.execute)
        builder.add_node("validate", self.validate)
        builder.add_node("respond", self.respond)

        builder.add_edge(START, "planning")
        builder.add_edge("planning", "supervise")
        builder.add_conditional_edges("supervise", self.should_validate)
        builder.add_edge("execute", "supervise")
        builder.add_conditional_edges("validate", self.should_replan)
        builder.add_edge("respond", END)

        logger.info("Leader: graph created.")
        return builder

    # --- routing helpers ------------------------------------------------------
    def _hash_progress(
        self, progress: Sequence[tuple[str, Sequence[BaseMessage]]]
    ) -> str:
        """If this fingerprint doesn't change across loops, we're stalling → exit to validation."""
        parts = []
        for task, msgs in progress or []:
            tail = (msgs[-1].content if msgs else "") or ""
            if not isinstance(tail, str):
                tail = str(tail)
            task_str = task if isinstance(task, str) else str(task)
            parts.append(task_str + "|" + tail[:100])
        return "|#|".join(parts)

    def _rank_experts(self, objective: str, step: str, require_live: bool) -> list[str]:
        """
        Deterministic filter/score: categories > keywords then tie-break by cost/latency hints.
        This is the cheap, stable shortlist before asking the LLM to break ties.
        """
        text = f"{objective}\n{step}".lower()
        scored = []
        for name, p in self.expert_index.items():
            if require_live and not p.live_ok:
                continue
            kw = sum(1 for k in p.keywords if k in text)
            cat = sum(1 for c in p.categories if c in text)
            total = cat * 3 + kw * 2
            if total <= 0:
                continue
            scored.append((total, -p.cost_hint, -p.latency_hint, name))
        scored.sort(reverse=True)
        return [n for _, _, _, n in scored]

    async def _choose_expert(self, state: State, step: str, step_number: int) -> str:
        """
        Tie-breaker between plausible experts:
        - shortlist deterministically via _rank_experts
        - ask the LLM using the *tuned* choose_expert prompt (explicit, auditable)
        """
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")

        objective_msg = state.get("objective") or state["messages"][0]
        objective = getattr(objective_msg, "content", str(objective_msg))
        require_live = any(
            x in objective.lower() for x in ("live", "today", "now", "current")
        )
        ranked = self._rank_experts(objective, step, require_live) or list(
            self.experts.keys()
        )
        if len(ranked) == 1:
            return ranked[0]
        top_k = self.get_tuned_int("routing.top_k", default=2)
        top = ranked[:top_k]
        # Use tuned prompt + safe {token} rendering (unknown tokens remain literal)
        tpl = self.get_tuned_text("routing.prompts.choose_expert") or ""
        prompt_text = self.render(
            tpl,
            objective=objective,
            step_number=step_number,
            step=step,
            options=", ".join(top),
        )

        raw = await self.exec_decision_chain.ainvoke(
            {"messages": [HumanMessage(content=prompt_text)]}
        )
        choice = getattr(raw, "expert", "") or ""
        return _normalize_choice(choice, top) or top[0]

    # --- routing conditions ---------------------------------------------------
    async def should_validate(self, state: State) -> Literal["execute", "validate"]:
        progress = state.get("progress") or []
        if (self.max_steps or 0) and len(progress) >= (self.max_steps or 0):
            logger.warning(
                "Leader: reached max_steps=%s, forcing validate.", self.max_steps
            )
            return "validate"

        curr = self._hash_progress(progress)
        if self._last_progress_hash == curr and progress:
            logger.warning("Leader: detected stall in progress, moving to validate.")
            return "validate"
        self._last_progress_hash = curr

        if len(progress) == len(state["plan"].steps):
            return "validate"
        return "execute"

    async def should_replan(self, state: State) -> Literal["respond", "planning"]:
        plan_decision = state.get("plan_decision")
        if (
            plan_decision is not None
            and getattr(plan_decision, "action", None) == "planning"
        ):
            return "planning"
        return "respond"

    # --- nodes ----------------------------------------------------------------
    async def respond(self, state: State):
        if self.model is None:
            self.model = get_model(self.agent_settings.model)

        # Compress step outputs into a single final answer; add no new facts.
        step_conclusions_str = ""
        for _, step_responses in state.get("progress") or []:
            step_conclusions_str += f"{step_responses[-1].content}\n"

        progress_msg = mk_thought(
            label="respond", node="respond", task="finalize", content="Summarizing…"
        )

        prompt = (
            "Use ONLY the data produced by the executed agents (no new assumptions).\n"
            f"You executed this plan:\n{state['plan']}\n"
            f"Step conclusions:\n{step_conclusions_str}\n"
            f"Final answer to the objective: {state['objective']}"
        )

        messages = [HumanMessage(content=prompt)]
        messages = self.with_chat_context_text(messages)

        response = await self.model.ainvoke(messages)
        response = AIMessage(
            content=response.content,
            response_metadata={
                "extras": {"node": "respond", "task": "deliver final answer"}
            },
        )
        return {
            "messages": [progress_msg, response],
            "traces": ["Responded to the user."],
        }

    async def plan(self, state: State):
        """
        Plan minimally:
        - Initial objective → shortest plan (prefer 1 step).
        - If partial progress exists → propose at most one additional step.
        Prompts are explicit and local to this node; no hidden profile/system merges.
        """
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")

        state.setdefault("messages", [])
        new_objective = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if new_objective is None:
            raise ValueError("No human message found for objective.")

        # First encounter of this objective → reset plan/progress
        if "initial_objective" not in state:
            state["progress"] = []
            state["plan"] = Plan(steps=[])
            state["initial_objective"] = new_objective

        if (
            state["initial_objective"] is None
            or state["initial_objective"].content != new_objective.content
        ):
            logger.info(
                "Leader: new initial objective detected. Resetting plan and progress."
            )
            state["progress"] = []
            state["plan"] = Plan(steps=[])
            state["initial_objective"] = new_objective
            self._replans_done = 0
            self._last_progress_hash = None

        progress = state.get("progress") or []

        # Re-plan (add *at most one* necessary step)
        if progress:
            objective = state["messages"][-1]
            current_plan = state["plan"]
            step_conclusions = [sr[-1] for _, sr in progress]

            base_prompt = (
                f"Objective: {objective.content}\n"
                f"Original plan:\n{current_plan}\n"
                "The previous steps were not sufficient. Propose AT MOST ONE additional step, "
                "only if strictly necessary to reach the objective. No explanations."
            )

            if self.experts:
                experts_list = "\n".join(
                    [str(expert) for expert in self.experts.values()]
                )
                prompt = f"{base_prompt}\nExperts:\n{experts_list}\n"
            else:
                prompt = base_prompt

            messages = step_conclusions + [HumanMessage(content=prompt)]
            re_plan_result = await self.plan_chain.ainvoke({"messages": messages})
            re_plan: Plan = (
                re_plan_result
                if isinstance(re_plan_result, Plan)
                else Plan.model_validate(re_plan_result)
            )

            thought = mk_thought(
                label="replan", node="replan", task="planning", content=str(re_plan)
            )
            return {
                "messages": [thought],
                "plan": Plan(steps=state["plan"].steps + re_plan.steps),
                "traces": ["Plan adjusted with minimal additional step."],
                "objective": objective,
            }

        # Initial plan (prefer shortest)
        else:
            objective = state["messages"][-1]
            base_prompt = (
                "Produce the SHORTEST possible plan that still achieves the objective. "
                "Prefer a single step if it fully answers. No explanations. "
                "Each step must be executable by exactly one expert."
            )

            if self.experts:
                experts_list = "\n".join(
                    [str(expert) for expert in self.experts.values()]
                )
                plan_instructions = (
                    f"Experts available:\n{experts_list}\n\n{base_prompt}"
                )
            else:
                plan_instructions = base_prompt

            # Explicit system: use the tuned leader system prompt for the planning node
            sys_tpl = self.get_tuned_text("prompts.system") or ""
            sys_text = self.render(sys_tpl)
            messages = self.with_system(
                sys_text, state["messages"] + [SystemMessage(content=plan_instructions)]
            )

            new_plan_result = await self.plan_chain.ainvoke({"messages": messages})
            new_plan: Plan = (
                new_plan_result
                if isinstance(new_plan_result, Plan)
                else Plan.model_validate(new_plan_result)
            )

            thought = mk_thought(
                label="plan", node="plan", task="planning", content=str(new_plan)
            )
            return {
                "messages": [thought],
                "plan": new_plan,
                "traces": ["Initial minimal plan set."],
                "progress": [],
                "objective": objective,
            }

    async def supervise(self, state: State):
        return {
            "messages": [
                mk_thought(
                    label="supervise",
                    node="supervise",
                    task="orchestration",
                    content="Supervising…",
                )
            ]
        }

    async def execute(self, state: State):
        """
        Pick expert → run expert graph on a structured job message.
        Note: we do *not* inject expert system prompts here; each expert’s own node decides
        how to use its tuned prompts (mirrors the “no magic” rule).
        """
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")
        progress = state.get("progress") or []
        task = state["plan"].steps[len(progress)]
        task_number = len(progress) + 1

        if not self.experts:
            raise ValueError("No experts available to execute the task.")

        picking = mk_thought(
            label="expert_select",
            node="execute",
            task="routing",
            content=f"Selecting expert for step {task_number}: {task}",
        )
        selected_expert = await self._choose_expert(state, task, task_number)
        decided = mk_thought(
            label="expert_selected",
            node="execute",
            task="routing",
            content=f"Selected expert: {selected_expert}",
            extras={"expert": selected_expert, "step": task_number, "task": str(task)},
        )
        logger.info(
            "Leader: selected expert=%s for step=%s", selected_expert, task_number
        )

        if selected_expert not in self.experts:
            fail = mk_thought(
                label="expert_missing",
                node="execute",
                task="routing",
                content=f"Expert {selected_expert} missing. Replanning…",
            )
            plan_update = await self.plan(state)
            plan_update["messages"] = [fail] + (plan_update.get("messages") or [])
            return plan_update

        compiled = self.compiled_expert_graphs.get(selected_expert)
        if not compiled:
            fail = mk_thought(
                label="expert_graph_missing",
                node="execute",
                task="routing",
                content=f"Compiled graph not found for expert {selected_expert}. Replanning…",
            )
            plan_update = await self.plan(state)
            plan_update["messages"] = [fail] + (plan_update.get("messages") or [])
            return plan_update

        # Job for the expert (context includes the plan). Keep this as a SystemMessage so
        # the expert can prepend its own system prompt separately without ambiguity.
        task_job = f"For the following plan:\n\n{state['plan']}\n\nYou are tasked with executing step {task_number}, {task}."
        step_conclusions = [sr[-1] for _, sr in progress]
        expert_messages = step_conclusions + [SystemMessage(content=task_job)]

        expert_instance = self.experts[selected_expert]
        response = await compiled.ainvoke({"messages": expert_messages})

        expert_description = expert_instance.get_description() or ""
        additional_messages: list[BaseMessage] = [picking, decided]
        for message in response.get("messages", []):
            new_message: BaseMessage = message
            md = _ensure_metadata_dict(new_message)
            md["extras"] = {
                **(md.get("extras") or {}),
                "node": "execute",
                "task": str(task),
                "task_number": task_number,
                "agentic_flow": selected_expert,
                "expert_description": expert_description,
            }
            md.setdefault("thought", f"Execution output from {selected_expert}")
            new_message.response_metadata = md
            additional_messages.append(new_message)

        return {
            "messages": additional_messages,
            "traces": [
                f"Step {task_number} ({task}) assigned to {selected_expert} and executed"
            ],
            "progress": (state.get("progress") or [])
            + [(task, response.get("messages", []))],
        }

    async def validate(self, state: State):
        """
        Gate between “respond” and “replan one more step”.
        Deterministic budget guards protect against loops; the LLM only picks the branch.
        """
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")
        progress = state.get("progress") or []

        # Budget guard: steps or replans exceeded → respond now.
        if ((self.max_steps or 0) and len(progress) >= (self.max_steps or 0)) or (
            self._replans_done >= self.max_replans
        ):
            note = mk_thought(
                label="validate_forced",
                node="validate",
                task="gate",
                content=f"Budget reached (steps={len(progress)}/{self.max_steps}, replans={self._replans_done}/{self.max_replans}). Forcing final response.",
            )
            return {
                "messages": [note],
                "plan_decision": PlanDecision(action="respond"),
                "traces": ["Forced respond due to budget limits"],
            }

        objective = state["messages"][0].content
        current_plan = state["plan"]
        prompt = (
            f"Objective: {objective}\nPlan: {current_plan}\n"
            "Based only on the executed step conclusions above, is the objective met?\n"
            "Answer 'respond' if yes or uncertain. Answer 'planning' ONLY if exactly one minimal additional step is clearly needed."
        )

        progress_msg = mk_thought(
            label="validate",
            node="validate",
            task="gate",
            content="Validating whether to respond or replan…",
        )
        step_conclusions = [sr[-1] for _, sr in progress]
        messages = step_conclusions + [HumanMessage(content=prompt)]

        plan_decision_result = await self.plan_decision_chain.ainvoke(
            {"messages": messages}
        )
        plan_decision: PlanDecision = (
            plan_decision_result
            if isinstance(plan_decision_result, PlanDecision)
            else PlanDecision.model_validate(plan_decision_result)
        )

        if plan_decision.action == "planning":
            self._replans_done += 1

        decided_msg = mk_thought(
            label="validate_decision",
            node="validate",
            task="gate",
            content=f"Decision: {plan_decision.action}",
        )
        return {
            "messages": [progress_msg, decided_msg],
            "plan_decision": plan_decision,
            "traces": [f"Evaluation done, status is {plan_decision}."],
        }
