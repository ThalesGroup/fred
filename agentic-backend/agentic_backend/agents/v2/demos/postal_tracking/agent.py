"""
Graph v2 example for a real workflow (postal tracking).

Use this file as reference when you need:
- intent routing + deterministic steps
- tool calls across multiple systems
- HITL decision gate before sensitive action
- rich final output (text + map)
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agentic_backend.core.agents.agent_spec import FieldSpec, MCPServerRef, UIHints
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    GraphAgentDefinition,
    GraphConditionalDefinition,
    GraphDefinition,
    GraphEdgeDefinition,
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeDefinition,
    GraphNodeResult,
    GraphNodeShape,
    GraphRouteDefinition,
    HumanChoiceOption,
    HumanInputRequest,
)
from agentic_backend.core.chatbot.chat_schema import GeoPart

RequestMode = Literal[
    "unknown", "unsupported", "capabilities_info", "followup_info", "action_flow"
]
ActionKind = Literal["none", "reroute", "reschedule"]


class TrackingGraphDemoInput(BaseModel):
    message: str


class TrackingGraphDemoState(BaseModel):
    latest_user_text: str
    request_mode: RequestMode = "unknown"
    routing_mode_source: str | None = None
    routing_reason: str | None = None
    intent_topic: str = "other"
    intent_confidence: float = 0.0
    intent_explicit_action: bool = False
    intent_action_kind: ActionKind = "none"
    intent_requires_parcel_context: bool = True
    intent_needs_map: bool = False
    intent_need_iot_snapshot: bool = False
    intent_need_iot_events: bool = False
    intent_need_pickup_points: bool = False
    tracking_id: str | None = None
    tracking_candidates: list[dict[str, Any]] = Field(default_factory=list)
    selected_parcel_summary: dict[str, Any] = Field(default_factory=dict)
    business_seed: dict[str, Any] = Field(default_factory=dict)
    iot_seed: dict[str, Any] = Field(default_factory=dict)
    business_track: dict[str, Any] = Field(default_factory=dict)
    iot_snapshot: dict[str, Any] = Field(default_factory=dict)
    iot_events: list[dict[str, Any]] = Field(default_factory=list)
    pickup_points: list[dict[str, Any]] = Field(default_factory=list)
    map_overlay: dict[str, Any] = Field(default_factory=dict)
    show_map: bool = False
    chosen_action: str | None = None
    chosen_pickup_point_id: str | None = None
    chosen_pickup_point_name: str | None = None
    chosen_reschedule_date: str | None = None
    chosen_reschedule_time_window: str | None = None
    reroute_result: dict[str, Any] = Field(default_factory=dict)
    reschedule_result: dict[str, Any] = Field(default_factory=dict)
    notification_result: dict[str, Any] = Field(default_factory=dict)
    final_text: str | None = None


class Definition(GraphAgentDefinition):
    """
    Example of a production-like graph agent.

    Quick edit guide:
    - graph structure: `build_graph()`
    - business logic: node handler methods
    - UI / human decisions: `HumanInputRequest` payloads
    - tool contracts: `tool_requirements` and runtime calls in nodes
    """

    agent_id: str = "tracking.graph.demo.v2"
    role: str = "Postal tracking workflow demo"
    description: str = (
        "Demonstrates a graph-style parcel workflow with intent routing, "
        "business MCP tools, IoT tracking tools, human approval, and map output."
    )
    tags: tuple[str, ...] = ("postal", "graph", "iot", "map", "hitl", "demo")
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="mcp-postal-business-demo"),
        MCPServerRef(id="mcp-iot-tracking-demo"),
    )
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="i18n.default_language",
            type="select",
            title="Default language",
            description="Language used when the runtime context does not provide one.",
            required=False,
            default="fr",
            enum=["fr", "en"],
            ui=UIHints(group="I18n"),
        ),
    )

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="TrackingGraphDemoState",
            entry_node="route_request",
            nodes=(
                GraphNodeDefinition(
                    node_id="route_request",
                    title="Route request",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="respond_capabilities",
                    title="Respond capabilities",
                ),
                GraphNodeDefinition(
                    node_id="resolve_parcel_context",
                    title="Resolve parcel context",
                ),
                GraphNodeDefinition(
                    node_id="ensure_iot_context",
                    title="Ensure IoT context",
                ),
                GraphNodeDefinition(
                    node_id="collect_context",
                    title="Collect context",
                ),
                GraphNodeDefinition(
                    node_id="respond_followup",
                    title="Respond follow-up",
                ),
                GraphNodeDefinition(
                    node_id="choose_resolution",
                    title="Choose resolution",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="apply_reroute",
                    title="Apply reroute",
                ),
                GraphNodeDefinition(
                    node_id="apply_reschedule",
                    title="Apply reschedule",
                ),
                GraphNodeDefinition(
                    node_id="cancel_flow",
                    title="Cancel flow",
                ),
                GraphNodeDefinition(
                    node_id="finalize",
                    title="Finalize response",
                    shape=GraphNodeShape.ROUND,
                ),
            ),
            edges=(
                GraphEdgeDefinition(source="respond_capabilities", target="finalize"),
                GraphEdgeDefinition(
                    source="resolve_parcel_context", target="ensure_iot_context"
                ),
                GraphEdgeDefinition(
                    source="ensure_iot_context", target="collect_context"
                ),
                GraphEdgeDefinition(source="respond_followup", target="finalize"),
                GraphEdgeDefinition(source="apply_reroute", target="finalize"),
                GraphEdgeDefinition(source="apply_reschedule", target="finalize"),
                GraphEdgeDefinition(source="cancel_flow", target="finalize"),
            ),
            conditionals=(
                GraphConditionalDefinition(
                    source="route_request",
                    routes=(
                        GraphRouteDefinition(
                            route_key="capabilities",
                            target="respond_capabilities",
                            label="capabilities",
                        ),
                        GraphRouteDefinition(
                            route_key="parcel_context",
                            target="resolve_parcel_context",
                            label="parcel context",
                        ),
                        GraphRouteDefinition(
                            route_key="unsupported",
                            target="finalize",
                            label="unsupported",
                        ),
                    ),
                ),
                GraphConditionalDefinition(
                    source="collect_context",
                    routes=(
                        GraphRouteDefinition(
                            route_key="followup",
                            target="respond_followup",
                            label="follow-up",
                        ),
                        GraphRouteDefinition(
                            route_key="action",
                            target="choose_resolution",
                            label="action",
                        ),
                    ),
                ),
                GraphConditionalDefinition(
                    source="choose_resolution",
                    routes=(
                        GraphRouteDefinition(
                            route_key="reroute",
                            target="apply_reroute",
                            label="reroute",
                        ),
                        GraphRouteDefinition(
                            route_key="reschedule",
                            target="apply_reschedule",
                            label="reschedule",
                        ),
                        GraphRouteDefinition(
                            route_key="cancel",
                            target="cancel_flow",
                            label="cancel",
                        ),
                    ),
                ),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return TrackingGraphDemoInput

    def state_model(self) -> type[BaseModel]:
        return TrackingGraphDemoState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        del binding
        model = TrackingGraphDemoInput.model_validate(input_model)
        return TrackingGraphDemoState(latest_user_text=model.message)

    def build_turn_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
        previous_state: BaseModel | None = None,
    ) -> BaseModel:
        del binding
        model = TrackingGraphDemoInput.model_validate(input_model)
        state = TrackingGraphDemoState(latest_user_text=model.message)
        if previous_state is None:
            return state

        prior = TrackingGraphDemoState.model_validate(previous_state)
        # Parcel support feels much better when the conversation remembers which
        # shipment the user already selected. The runtime stores the last
        # completed state; the agent decides that this piece of state is worth
        # carrying into the next turn.
        explicit_tracking_id = self._extract_tracking_id(model.message)
        if explicit_tracking_id is None and prior.tracking_id:
            state.tracking_id = prior.tracking_id
            state.selected_parcel_summary = dict(prior.selected_parcel_summary)
            state.business_seed = dict(prior.business_seed)
            state.iot_seed = dict(prior.iot_seed)
            state.tracking_candidates = [
                dict(item) for item in prior.tracking_candidates
            ]
        return state

    def node_handlers(self) -> dict[str, object]:
        return {
            "route_request": self.route_request,
            "respond_capabilities": self.respond_capabilities,
            "resolve_parcel_context": self.resolve_parcel_context,
            "ensure_iot_context": self.ensure_iot_context,
            "collect_context": self.collect_context,
            "respond_followup": self.respond_followup,
            "choose_resolution": self.choose_resolution,
            "apply_reroute": self.apply_reroute,
            "apply_reschedule": self.apply_reschedule,
            "cancel_flow": self.cancel_flow,
            "finalize": self.finalize,
        }

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = TrackingGraphDemoState.model_validate(state)
        ui_parts = ()
        if graph_state.show_map or graph_state.chosen_action in {
            "reroute",
            "reschedule",
        }:
            geojson = self._build_geojson(graph_state)
            if geojson is not None:
                ui_parts = (
                    GeoPart(geojson=geojson, popup_property="name", fit_bounds=True),
                )
        return GraphExecutionOutput(
            content=graph_state.final_text or "",
            ui_parts=ui_parts,
        )

    async def route_request(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Understand what kind of parcel help the user is asking for."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        latest_user = graph_state.latest_user_text.strip()
        explicit_tracking_id = self._extract_tracking_id(latest_user)
        decision = await self._route_intent_with_llm(
            context=context,
            latest_user=latest_user,
            has_tracking_context=bool(graph_state.tracking_id),
            has_explicit_tracking_id=bool(explicit_tracking_id),
        )

        route = str(decision.get("route") or "unsupported").strip().lower()
        if route == "capabilities":
            request_mode: RequestMode = "capabilities_info"
            route_key = "capabilities"
        elif route == "action_flow":
            request_mode = "action_flow"
            route_key = "parcel_context"
        elif route == "followup_info":
            request_mode = "followup_info"
            route_key = "parcel_context"
        else:
            request_mode = "unsupported"
            route_key = "unsupported"

        if request_mode == "unsupported":
            return GraphNodeResult(
                state_update={
                    "request_mode": "unsupported",
                    "routing_mode_source": str(
                        decision.get("_source") or "unsupported"
                    ),
                    "routing_reason": str(
                        decision.get("reason")
                        or "No parcel operations intent detected."
                    ),
                    "final_text": (
                        "Cette démo attend une question sur ton colis, par exemple son "
                        "statut, un retard, une congestion, une carte, ou une demande "
                        "de reroutage ou de reprogrammation de livraison."
                    ),
                },
                route_key=route_key,
            )

        context.emit_status("routing", f"Resolved route '{request_mode}'.")
        context.emit_status(
            "parcel_context",
            "Preparing parcel context and identifying the relevant shipment.",
        )
        return GraphNodeResult(
            state_update={
                "request_mode": request_mode,
                "routing_mode_source": str(decision.get("_source") or "unknown"),
                "routing_reason": str(decision.get("reason") or ""),
                "intent_topic": str(decision.get("topic") or "other"),
                "intent_confidence": self._coerce_float(
                    decision.get("confidence"), default=0.0
                ),
                "intent_explicit_action": self._coerce_bool(
                    decision.get("explicit_action"),
                    default=(request_mode == "action_flow"),
                ),
                "intent_action_kind": self._coerce_action_kind(
                    decision.get("action_kind"),
                    default=("reroute" if request_mode == "action_flow" else "none"),
                ),
                "intent_requires_parcel_context": self._coerce_bool(
                    decision.get("requires_parcel_context"),
                    default=(request_mode != "capabilities_info"),
                ),
                "intent_needs_map": self._coerce_bool(
                    decision.get("needs_map"), default=False
                ),
                "intent_need_iot_snapshot": self._coerce_bool(
                    decision.get("need_iot_snapshot"),
                    default=(request_mode == "action_flow"),
                ),
                "intent_need_iot_events": self._coerce_bool(
                    decision.get("need_iot_events"),
                    default=(request_mode == "action_flow"),
                ),
                "intent_need_pickup_points": self._coerce_bool(
                    decision.get("need_pickup_points"),
                    default=(
                        self._coerce_action_kind(
                            decision.get("action_kind"),
                            default="none",
                        )
                        == "reroute"
                    ),
                ),
                "tracking_id": explicit_tracking_id or graph_state.tracking_id,
            },
            route_key=route_key,
        )

    async def respond_capabilities(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Explain the service role of the agent before any parcel is selected."""
        tool_names: list[str] = []
        tool_provider = context.services.tool_provider
        if tool_provider is not None:
            tool_names = sorted(tool.name for tool in tool_provider.get_tools())

        if tool_names:
            text = (
                "Je peux aider sur le suivi colis, la lecture du contexte IoT, "
                "l'affichage d'une carte, le reroutage vers un point relais, et la "
                "reprogrammation de livraison avec validation humaine.\n\n"
                "Outils runtime disponibles :\n"
                + "\n".join(f"- `{name}`" for name in tool_names)
            )
        else:
            text = (
                "Je peux aider sur le suivi colis, la lecture du contexte IoT, "
                "l'affichage d'une carte, le reroutage vers un point relais, et la "
                "reprogrammation de livraison avec validation humaine."
            )
        return GraphNodeResult(state_update={"final_text": text, "show_map": False})

    async def resolve_parcel_context(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Identify which parcel the user means from identity, history, or choice."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id
        selected_summary: dict[str, Any] = dict(graph_state.selected_parcel_summary)
        business_seed: dict[str, Any] = graph_state.business_seed

        context.emit_status("parcel_context", "Resolving parcel context for caller.")

        if not tracking_id:
            parcels_response = await context.invoke_runtime_tool(
                "list_my_active_parcels",
                {"include_terminal": False, "limit": 5},
            )
            tracking_candidates = self._parcel_candidates_from_response(
                parcels_response
            )
        else:
            tracking_candidates = graph_state.tracking_candidates

        if not tracking_id and len(tracking_candidates) == 1:
            selected_summary = tracking_candidates[0]
            tracking_id = str(selected_summary.get("tracking_id") or "").strip() or None

        if not tracking_id and len(tracking_candidates) > 1:
            decision = await context.request_human_input(
                HumanInputRequest(
                    stage="tracking_parcel_selection",
                    title="Choisir le colis à analyser",
                    question=(
                        "J'ai trouvé plusieurs colis actifs pour ton identité. "
                        "Lequel veux-tu analyser ?"
                    ),
                    choices=tuple(
                        HumanChoiceOption(
                            id=f"track:{candidate['tracking_id']}",
                            label=(
                                f"{candidate['tracking_id']} - "
                                f"{candidate.get('status', 'UNKNOWN')}"
                            )[:90],
                            description=self._parcel_choice_description(candidate),
                            default=index == 0,
                        )
                        for index, candidate in enumerate(tracking_candidates[:5])
                    ),
                    metadata={"candidate_count": len(tracking_candidates)},
                )
            )
            choice_id = str(
                self._as_dict(decision).get("choice_id")
                or self._as_dict(decision).get("answer")
                or ""
            ).strip()
            if choice_id.startswith("track:"):
                selected_tracking_id = choice_id.split(":", 1)[1].strip()
                tracking_id = selected_tracking_id or None
                for candidate in tracking_candidates:
                    if candidate.get("tracking_id") == tracking_id:
                        selected_summary = candidate
                        break

        if not tracking_id:
            context.emit_status(
                "demo_seed",
                "No active parcel was found for the caller; seeding a demo parcel.",
            )
            business_seed = await self._invoke_first_available(
                context,
                (
                    "seed_demo_parcel_exception_for_current_user",
                    "seed_demo_parcel_exception",
                ),
                {},
            )
            tracking_id = str(business_seed.get("tracking_id") or "").strip() or None

        if not tracking_id:
            raise RuntimeError("No tracking_id available after parcel resolution.")

        if not selected_summary:
            selected_summary = {
                "tracking_id": tracking_id,
                "status": business_seed.get("status") or "UNKNOWN",
            }

        return GraphNodeResult(
            state_update={
                "tracking_id": tracking_id,
                "tracking_candidates": tracking_candidates,
                "selected_parcel_summary": selected_summary,
                "business_seed": business_seed,
            }
        )

    async def ensure_iot_context(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Ensure the operational tracking backend knows about the selected parcel."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id
        if not tracking_id:
            raise RuntimeError("ensure_iot_context requires a tracking_id.")

        needs_iot_context = bool(
            graph_state.intent_need_iot_snapshot
            or graph_state.intent_need_iot_events
            or graph_state.intent_needs_map
            or graph_state.request_mode == "action_flow"
        )
        if not needs_iot_context:
            return GraphNodeResult()

        context.emit_status(
            "iot_context",
            f"Ensuring IoT scenario exists for {tracking_id}.",
        )
        iot_seed = self._as_dict(
            await context.invoke_runtime_tool(
                "seed_demo_tracking_incident",
                {"tracking_id": tracking_id},
            )
        )
        return GraphNodeResult(state_update={"iot_seed": iot_seed})

    async def collect_context(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Gather the business and operational facts needed for a useful answer."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id
        if not tracking_id:
            raise RuntimeError("collect_context requires a tracking_id.")

        context.emit_status("context", f"Collecting runtime context for {tracking_id}.")

        business_track = self._as_dict(
            await context.invoke_runtime_tool(
                "track_package", {"tracking_id": tracking_id}
            )
        )

        iot_snapshot: dict[str, Any] = {}
        if (
            graph_state.intent_need_iot_snapshot
            or graph_state.intent_need_iot_events
            or graph_state.intent_needs_map
            or graph_state.request_mode == "action_flow"
        ):
            iot_snapshot = self._as_dict(
                await context.invoke_runtime_tool(
                    "get_live_tracking_snapshot", {"tracking_id": tracking_id}
                )
            )

        iot_events: list[dict[str, Any]] = []
        if (
            graph_state.intent_need_iot_events
            or graph_state.request_mode == "action_flow"
        ):
            events_response = self._as_dict(
                await context.invoke_runtime_tool(
                    "list_tracking_events",
                    {"tracking_id": tracking_id, "limit": 5, "since_seq": 0},
                )
            )
            iot_events = self._events_from_response(events_response)

        delivery_address = self._as_dict(
            self._safe_get(business_track, "delivery", "address")
        )
        city = str(delivery_address.get("city") or "Paris")
        postal_code = str(delivery_address.get("postal_code") or "75015")

        pickup_points: list[dict[str, Any]] = []
        if (
            graph_state.intent_need_pickup_points
            or graph_state.request_mode == "action_flow"
        ):
            pickup_response = await context.invoke_runtime_tool(
                "get_pickup_points_nearby",
                {"city": city, "postal_code": postal_code, "limit": 3},
            )
            pickup_points = self._pickup_points_from_response(pickup_response)

        map_overlay = self._map_overlay_from_snapshot(iot_snapshot)
        if graph_state.intent_needs_map or graph_state.request_mode == "action_flow":
            route_response = self._as_dict(
                await context.invoke_runtime_tool(
                    "get_route_geometry", {"tracking_id": tracking_id}
                )
            )
            map_overlay = self._merge_map_overlay(
                map_overlay,
                self._map_overlay_from_route_response(route_response),
            )

        route_key = (
            "action" if graph_state.request_mode == "action_flow" else "followup"
        )
        return GraphNodeResult(
            state_update={
                "business_track": business_track,
                "iot_seed": graph_state.iot_seed,
                "iot_snapshot": iot_snapshot,
                "iot_events": iot_events,
                "pickup_points": pickup_points,
                "map_overlay": map_overlay,
                "show_map": bool(
                    graph_state.intent_needs_map
                    or graph_state.request_mode == "action_flow"
                ),
            },
            route_key=route_key,
        )

    async def respond_followup(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Answer the current parcel question without executing a customer action."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        payload = self._followup_payload(graph_state)
        content = await self._summarize_with_model(
            context=context,
            latest_user=graph_state.latest_user_text,
            payload=payload,
            system_instruction=(
                "You are a parcel operations copilot. Answer in the user's "
                "language using only the provided JSON data. Be concise. Use "
                "short bullets when helpful. Mention the tracking_id explicitly. "
                "If a value is missing, write 'n/a'."
            ),
        )
        if not content:
            content = self._followup_fallback_text(graph_state)
        return GraphNodeResult(state_update={"final_text": content})

    async def choose_resolution(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Ask for a human decision before changing the delivery plan."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id or "UNKNOWN"
        pickup_points = graph_state.pickup_points[:3]

        diagnosis = await self._summarize_with_model(
            context=context,
            latest_user=graph_state.latest_user_text,
            payload=self._followup_payload(graph_state),
            system_instruction=(
                "You are a parcel operations copilot. Produce a short diagnosis "
                "before any customer action. Mention delay, congestion, and the "
                "most relevant next action option. Use the user's language."
            ),
        )
        if not diagnosis:
            diagnosis = self._diagnosis_fallback_text(graph_state)
        context.emit_assistant_delta(diagnosis)

        if graph_state.intent_action_kind == "reschedule":
            schedule_choices = self._reschedule_choice_options()
            decision = await context.request_human_input(
                HumanInputRequest(
                    stage="tracking_reschedule",
                    title="Choisir un créneau de reprogrammation",
                    question=(
                        f"Quel nouveau créneau veux-tu proposer pour le colis "
                        f"`{tracking_id}` ?"
                    ),
                    choices=tuple(schedule_choices),
                    metadata={"tracking_id": tracking_id},
                )
            )
            choice_id = str(
                self._as_dict(decision).get("choice_id")
                or self._as_dict(decision).get("answer")
                or "cancel"
            ).strip()
            if choice_id.startswith("reschedule:"):
                _, requested_date, time_window = choice_id.split(":", 2)
                return GraphNodeResult(
                    state_update={
                        "chosen_action": "reschedule",
                        "chosen_reschedule_date": requested_date,
                        "chosen_reschedule_time_window": time_window,
                    },
                    route_key="reschedule",
                )
            return GraphNodeResult(
                state_update={"chosen_action": "cancel"},
                route_key="cancel",
            )

        choices: list[HumanChoiceOption] = []
        for index, point in enumerate(pickup_points):
            pickup_point_id = str(point.get("pickup_point_id") or "").strip()
            if not pickup_point_id:
                continue
            name = str(point.get("name") or pickup_point_id)
            choices.append(
                HumanChoiceOption(
                    id=f"reroute:{pickup_point_id}",
                    label=f"{pickup_point_id} - {name}"[:80],
                    description=str(point.get("opening_hours") or "") or None,
                    default=index == 0,
                )
            )
        choices.append(
            HumanChoiceOption(
                id="cancel",
                label="Ne rien faire",
                description="Conserver seulement le diagnostic.",
            )
        )

        if len(choices) == 1:
            return GraphNodeResult(
                state_update={
                    "chosen_action": "cancel",
                    "final_text": (
                        f"Aucun point relais pertinent n'a été trouvé pour `{tracking_id}`. "
                        "Je conserve seulement le diagnostic."
                    ),
                },
                route_key="cancel",
            )

        decision = await context.request_human_input(
            HumanInputRequest(
                stage="tracking_resolution",
                title="Choisir une action de résolution",
                question=(
                    f"Le colis `{tracking_id}` est en difficulté. Veux-tu le rerouter "
                    "vers un point relais proposé ?"
                ),
                choices=tuple(choices),
                metadata={"tracking_id": tracking_id},
            )
        )
        choice_id = str(
            self._as_dict(decision).get("choice_id")
            or self._as_dict(decision).get("answer")
            or "cancel"
        ).strip()

        if choice_id.startswith("reroute:"):
            pickup_point_id = choice_id.split(":", 1)[1].strip()
            pickup_point_name = pickup_point_id
            for point in pickup_points:
                if str(point.get("pickup_point_id") or "").strip() == pickup_point_id:
                    pickup_point_name = str(point.get("name") or pickup_point_id)
                    break
            return GraphNodeResult(
                state_update={
                    "chosen_action": "reroute",
                    "chosen_pickup_point_id": pickup_point_id,
                    "chosen_pickup_point_name": pickup_point_name,
                    "show_map": True,
                },
                route_key="reroute",
            )

        return GraphNodeResult(
            state_update={"chosen_action": "cancel"},
            route_key="cancel",
        )

    async def apply_reroute(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Execute a reroute only after the user has explicitly chosen it."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id
        pickup_point_id = graph_state.chosen_pickup_point_id
        if not tracking_id or not pickup_point_id:
            raise RuntimeError(
                "apply_reroute requires tracking_id and pickup_point_id."
            )

        reroute_result = self._as_dict(
            await context.invoke_runtime_tool(
                "reroute_package_to_pickup_point",
                {
                    "tracking_id": tracking_id,
                    "pickup_point_id": pickup_point_id,
                    "reason": "customer_choice_via_hitl",
                },
            )
        )
        notification_result = self._as_dict(
            await context.invoke_runtime_tool(
                "notify_customer",
                {
                    "tracking_id": tracking_id,
                    "channel": "sms",
                    "message": (
                        f"Votre colis {tracking_id} a été rerouté vers "
                        f"{graph_state.chosen_pickup_point_name or pickup_point_id}."
                    ),
                },
            )
        )
        return GraphNodeResult(
            state_update={
                "reroute_result": reroute_result,
                "notification_result": notification_result,
            }
        )

    async def apply_reschedule(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Execute a delivery reschedule chosen through HITL."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id
        requested_date = graph_state.chosen_reschedule_date
        time_window = graph_state.chosen_reschedule_time_window
        if not tracking_id or not requested_date or not time_window:
            raise RuntimeError(
                "apply_reschedule requires tracking_id, requested_date, and time_window."
            )

        reschedule_result = self._as_dict(
            await context.invoke_runtime_tool(
                "reschedule_delivery",
                {
                    "tracking_id": tracking_id,
                    "requested_date": requested_date,
                    "time_window": time_window,
                },
            )
        )
        notification_result = self._as_dict(
            await context.invoke_runtime_tool(
                "notify_customer",
                {
                    "tracking_id": tracking_id,
                    "channel": "sms",
                    "message": (
                        f"Votre colis {tracking_id} a été reprogrammé pour le "
                        f"{requested_date} ({time_window})."
                    ),
                },
            )
        )
        return GraphNodeResult(
            state_update={
                "reschedule_result": reschedule_result,
                "notification_result": notification_result,
            }
        )

    async def cancel_flow(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Stop after diagnosis when the user does not want an action."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        tracking_id = graph_state.tracking_id or "UNKNOWN"
        if graph_state.final_text:
            return GraphNodeResult()
        return GraphNodeResult(
            state_update={
                "final_text": (
                    f"Aucune action exécutée pour `{tracking_id}`. "
                    "Le diagnostic et la carte restent disponibles."
                )
            }
        )

    async def finalize(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        """Produce the concise business outcome shown back to the user."""
        graph_state = TrackingGraphDemoState.model_validate(state)
        if graph_state.final_text:
            return GraphNodeResult()

        tracking_id = graph_state.tracking_id or "UNKNOWN"
        if graph_state.chosen_action == "reroute":
            reroute = graph_state.reroute_result
            notification = graph_state.notification_result
            delivery = self._as_dict(reroute.get("delivery"))
            point_id = (
                str(delivery.get("pickup_point_id") or "")
                or graph_state.chosen_pickup_point_id
                or "n/a"
            )
            point_name = (
                str(delivery.get("pickup_point_name") or "")
                or graph_state.chosen_pickup_point_name
                or point_id
            )
            notification_id = str(notification.get("notification_id") or "n/a")
            return GraphNodeResult(
                state_update={
                    "final_text": (
                        f"Reroutage exécuté pour `{tracking_id}` vers `{point_id}` "
                        f"({point_name}). Notification `{notification_id}` envoyée."
                    )
                }
            )

        if graph_state.chosen_action == "reschedule":
            reschedule = graph_state.reschedule_result
            notification = graph_state.notification_result
            delivery = self._as_dict(reschedule.get("delivery"))
            requested_date = (
                str(delivery.get("scheduled_date") or "")
                or graph_state.chosen_reschedule_date
                or "n/a"
            )
            time_window = (
                str(delivery.get("time_window") or "")
                or graph_state.chosen_reschedule_time_window
                or "n/a"
            )
            notification_id = str(notification.get("notification_id") or "n/a")
            return GraphNodeResult(
                state_update={
                    "final_text": (
                        f"Reprogrammation exécutée pour `{tracking_id}` le "
                        f"`{requested_date}` sur le créneau `{time_window}`. "
                        f"Notification `{notification_id}` envoyée."
                    )
                }
            )

        return GraphNodeResult(
            state_update={
                "final_text": (
                    f"Le workflow colis pour `{tracking_id}` n'a pas produit de résultat final."
                )
            }
        )

    async def _route_intent_with_llm(
        self,
        *,
        context: GraphNodeContext,
        latest_user: str,
        has_tracking_context: bool,
        has_explicit_tracking_id: bool,
    ) -> dict[str, Any]:
        if context.model is None or not latest_user.strip():
            return self._fallback_intent_router(
                latest_user=latest_user,
                has_tracking_context=has_tracking_context,
                has_explicit_tracking_id=has_explicit_tracking_id,
            )

        prompt = self._intent_router_prompt(
            latest_user=latest_user,
            has_tracking_context=has_tracking_context,
            has_explicit_tracking_id=has_explicit_tracking_id,
        )
        try:
            response = await context.model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(response, "content", ""))
            parsed = self._parse_json_object_from_text(text) or {}
            if not parsed:
                raise ValueError("empty/invalid JSON router output")

            route_raw = str(parsed.get("route") or "").strip().lower()
            if route_raw in {"capabilities_info", "capabilities"}:
                route = "capabilities"
            elif route_raw in {"followup", "info", "followup_info"}:
                route = "followup_info"
            elif route_raw in {"action", "action_flow"}:
                route = "action_flow"
            else:
                route = "unsupported"

            decision = {
                "route": route,
                "topic": str(parsed.get("topic") or "other").strip().lower() or "other",
                "explicit_action": self._coerce_bool(
                    parsed.get("explicit_action"),
                    default=(route == "action_flow"),
                ),
                "action_kind": self._coerce_action_kind(
                    parsed.get("action_kind"),
                    default=("reroute" if route == "action_flow" else "none"),
                ),
                "requires_parcel_context": self._coerce_bool(
                    parsed.get("requires_parcel_context"),
                    default=(route != "capabilities"),
                ),
                "needs_map": self._coerce_bool(parsed.get("needs_map"), default=False),
                "need_iot_snapshot": self._coerce_bool(
                    parsed.get("need_iot_snapshot"), default=False
                ),
                "need_iot_events": self._coerce_bool(
                    parsed.get("need_iot_events"), default=False
                ),
                "need_pickup_points": self._coerce_bool(
                    parsed.get("need_pickup_points"), default=False
                ),
                "confidence": max(
                    0.0,
                    min(1.0, self._coerce_float(parsed.get("confidence"), default=0.0)),
                ),
                "reason": str(parsed.get("reason") or "").strip(),
                "_source": "llm_router",
            }
            if decision["needs_map"]:
                decision["need_iot_snapshot"] = True
            return decision
        except Exception:
            return self._fallback_intent_router(
                latest_user=latest_user,
                has_tracking_context=has_tracking_context,
                has_explicit_tracking_id=has_explicit_tracking_id,
            )

    def _intent_router_prompt(
        self,
        *,
        latest_user: str,
        has_tracking_context: bool,
        has_explicit_tracking_id: bool,
    ) -> str:
        return (
            "You are an intent router for a parcel-operations graph.\n"
            "Return JSON only, no markdown, no prose around it.\n"
            "Schema:\n"
            "{\n"
            '  "route": "capabilities|followup_info|action_flow|unsupported",\n'
            '  "topic": "capabilities|tracking_status|location|iot_state|events|pickup_options|other",\n'
            '  "explicit_action": false,\n'
            '  "action_kind": "none|reroute|reschedule",\n'
            '  "requires_parcel_context": true,\n'
            '  "needs_map": false,\n'
            '  "need_iot_snapshot": false,\n'
            '  "need_iot_events": false,\n'
            '  "need_pickup_points": false,\n'
            '  "confidence": 0.0,\n'
            '  "reason": "short explanation"\n'
            "}\n"
            "Rules:\n"
            "- capabilities if the user asks what you can do.\n"
            "- followup_info for tracking, delay, congestion, explanation, location, map.\n"
            "- action_flow only when the user clearly asks you to execute an action such as rerouting or rescheduling.\n"
            "- action_kind='reroute' for pickup-point / relay / locker rerouting requests.\n"
            "- action_kind='reschedule' for delivery rescheduling / reprogramming requests.\n"
            "- unsupported if the message is unrelated to parcel operations.\n"
            "- needs_map only when the user explicitly asks for a map, route, position, or visualisation.\n"
            "- need_pickup_points only if pickup points are needed to answer or execute the request.\n"
            "- If the request mentions congestion, route delay, telemetry, or hub state, set need_iot_snapshot=true.\n"
            "- If the request asks why, what happened, or asks for alerts/events, set need_iot_events=true.\n"
            f"has_tracking_context={'yes' if has_tracking_context else 'no'}\n"
            f"has_explicit_tracking_id={'yes' if has_explicit_tracking_id else 'no'}\n"
            f"message={latest_user}"
        )

    def _fallback_intent_router(
        self,
        *,
        latest_user: str,
        has_tracking_context: bool,
        has_explicit_tracking_id: bool,
    ) -> dict[str, Any]:
        normalized = self._normalize_intent_text(latest_user)
        if self._looks_like_capabilities_question(latest_user):
            return {
                "route": "capabilities",
                "topic": "capabilities",
                "explicit_action": False,
                "requires_parcel_context": False,
                "needs_map": False,
                "need_iot_snapshot": False,
                "need_iot_events": False,
                "need_pickup_points": False,
                "confidence": 0.55,
                "reason": "fallback: capabilities question",
                "_source": "fallback",
            }

        explicit_action = self._looks_like_action_request(latest_user)
        action_kind = self._detect_action_kind(latest_user)
        parcel_related = bool(
            has_explicit_tracking_id
        ) or self._looks_like_parcel_request(latest_user)
        wants_map = self._looks_like_map_request(latest_user)
        mentions_pickup = any(
            keyword in normalized
            for keyword in (
                "relais",
                "point relais",
                "point de retrait",
                "pickup",
                "locker",
                "consigne",
            )
        )
        mentions_events = any(
            keyword in normalized
            for keyword in ("event", "evenement", "alerte", "alert", "historique")
        )
        mentions_iot = any(
            keyword in normalized
            for keyword in (
                "iot",
                "congestion",
                "hub",
                "retard",
                "delay",
                "capteur",
                "telemetrie",
                "telemetry",
            )
        )

        if explicit_action:
            route = "action_flow"
        elif parcel_related:
            route = "followup_info"
        else:
            route = "unsupported"

        return {
            "route": route,
            "topic": (
                "pickup_options"
                if action_kind == "reroute" or mentions_pickup
                else "tracking_status"
                if action_kind == "reschedule"
                else "events"
                if mentions_events
                else "location"
                if wants_map
                else "iot_state"
                if mentions_iot
                else "tracking_status"
            ),
            "explicit_action": explicit_action,
            "action_kind": action_kind,
            "requires_parcel_context": route != "capabilities",
            "needs_map": wants_map,
            "need_iot_snapshot": wants_map or mentions_iot or route == "action_flow",
            "need_iot_events": mentions_events or route == "action_flow",
            "need_pickup_points": mentions_pickup or action_kind == "reroute",
            "confidence": 0.4,
            "reason": "fallback heuristic routing",
            "_source": "fallback",
        }

    async def _summarize_with_model(
        self,
        *,
        context: GraphNodeContext,
        latest_user: str,
        payload: dict[str, Any],
        system_instruction: str,
    ) -> str | None:
        if context.model is None:
            return None
        prompt = (
            f"{system_instruction}\n\n"
            f"User request:\n{latest_user}\n\n"
            "Data JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}"
        )
        try:
            response = await context.model.ainvoke([HumanMessage(content=prompt)])
            content = self._message_content_to_text(getattr(response, "content", ""))
            return content.strip() or None
        except Exception:
            return None

    def _followup_payload(self, state: TrackingGraphDemoState) -> dict[str, Any]:
        eta = self._as_dict(state.business_track.get("eta"))
        hub_status = self._as_dict(state.iot_snapshot.get("hub_status"))
        vehicle_position = self._as_dict(state.iot_snapshot.get("vehicle_position"))
        active_alerts = state.iot_snapshot.get("active_alerts")
        if not isinstance(active_alerts, list):
            active_alerts = []
        return {
            "tracking_id": state.tracking_id,
            "selected_parcel_summary": state.selected_parcel_summary,
            "business_status": state.business_track.get("status"),
            "delivery": self._as_dict(state.business_track.get("delivery")),
            "eta": eta,
            "delay_minutes": eta.get("delay_minutes"),
            "iot_phase": state.iot_snapshot.get("phase"),
            "hub_status": hub_status,
            "vehicle_position": vehicle_position,
            "active_alerts": active_alerts,
            "latest_events": state.iot_events[-5:],
            "pickup_points": state.pickup_points[:3],
        }

    def _followup_fallback_text(self, state: TrackingGraphDemoState) -> str:
        tracking_id = state.tracking_id or "UNKNOWN"
        eta = self._as_dict(state.business_track.get("eta"))
        delay_minutes = eta.get("delay_minutes")
        hub_status = self._as_dict(state.iot_snapshot.get("hub_status"))
        congestion = hub_status.get("congestion_level") or "n/a"
        phase = state.iot_snapshot.get("phase") or "n/a"
        actions = state.business_track.get("actions_available") or []
        if not isinstance(actions, list):
            actions = []
        lines = [
            f"Diagnostic colis pour `{tracking_id}` :",
            f"- Statut métier : `{state.business_track.get('status', 'n/a')}`",
            f"- Phase IoT : `{phase}`",
            f"- Congestion hub : `{congestion}`",
            f"- Retard estimé : `{delay_minutes if delay_minutes is not None else 'n/a'}` minutes",
        ]
        if actions:
            lines.append(
                "- Actions disponibles : "
                + ", ".join(f"`{action}`" for action in actions)
            )
        if state.intent_needs_map:
            lines.append("- Une carte est affichée pour visualiser le contexte.")
        return "\n".join(lines)

    def _diagnosis_fallback_text(self, state: TrackingGraphDemoState) -> str:
        tracking_id = state.tracking_id or "UNKNOWN"
        hub_status = self._as_dict(state.iot_snapshot.get("hub_status"))
        congestion = hub_status.get("congestion_level") or "n/a"
        queue_depth = hub_status.get("queue_depth") or "n/a"
        if state.intent_action_kind == "reschedule":
            return (
                f"Diagnostic colis pour `{tracking_id}` : congestion `{congestion}` au hub "
                f"(file `{queue_depth}`). Une reprogrammation de livraison est pertinente "
                "avant d'engager une autre action."
            )
        point_hint = "n/a"
        if state.pickup_points:
            point_hint = str(
                state.pickup_points[0].get("name")
                or state.pickup_points[0].get("pickup_point_id")
                or "n/a"
            )
        return (
            f"Diagnostic colis pour `{tracking_id}` : congestion `{congestion}` au hub "
            f"(file `{queue_depth}`), avec `{point_hint}` comme meilleure option de reroutage."
        )

    @staticmethod
    def _message_content_to_text(content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "\n".join(part.strip() for part in chunks if part.strip()).strip()
        return str(content).strip()

    @staticmethod
    def _parse_json_object_from_text(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        candidate = stripped[start : end + 1]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _extract_tracking_id(text: str) -> str | None:
        match = re.search(r"\b(PKG-[A-Z0-9-]+)\b", text.upper())
        return match.group(1) if match else None

    @staticmethod
    def _normalize_intent_text(text: str) -> str:
        raw = (text or "").strip().lower()
        if not raw:
            return ""
        raw = "".join(
            ch
            for ch in unicodedata.normalize("NFKD", raw)
            if not unicodedata.combining(ch)
        )
        raw = re.sub(r"[^a-z0-9]+", " ", raw)
        return " ".join(raw.split())

    @classmethod
    def _looks_like_capabilities_question(cls, text: str) -> bool:
        normalized = cls._normalize_intent_text(text)
        if not normalized:
            return False
        patterns = (
            "quels outils",
            "que peux tu faire",
            "que peux tu faire pour moi",
            "tes capacites",
            "capabilities",
            "what can you do",
            "what tools",
        )
        return any(pattern in normalized for pattern in patterns)

    @classmethod
    def _looks_like_action_request(cls, text: str) -> bool:
        normalized = cls._normalize_intent_text(text)
        if not normalized:
            return False
        action_keywords = (
            "reroute",
            "reroutage",
            "rerouter",
            "redirect",
            "rediriger",
            "relay",
            "relais",
            "pickup point",
            "point relais",
            "point de retrait",
            "locker",
            "consigne",
            "reschedule",
            "reprogrammer",
            "reprogramme",
            "reprogrammation",
            "replanif",
            "replanifier",
            "replanification",
            "annule",
            "cancel",
            "notifie",
            "notify",
            "execute",
            "executer",
            "solution",
            "resoudre",
        )
        return any(keyword in normalized for keyword in action_keywords)

    @classmethod
    def _detect_action_kind(cls, text: str) -> ActionKind:
        normalized = cls._normalize_intent_text(text)
        if not normalized:
            return "none"
        reschedule_keywords = (
            "reschedule",
            "reprogrammer",
            "reprogramme",
            "reprogrammation",
            "replanif",
            "replanifier",
            "replanification",
            "nouveau creneau",
            "nouvelle date",
            "changer la date",
        )
        if any(keyword in normalized for keyword in reschedule_keywords):
            return "reschedule"
        reroute_keywords = (
            "reroute",
            "reroutage",
            "rerouter",
            "redirect",
            "rediriger",
            "relay",
            "relais",
            "pickup point",
            "point relais",
            "point de retrait",
            "locker",
            "consigne",
        )
        if any(keyword in normalized for keyword in reroute_keywords):
            return "reroute"
        return "none"

    @classmethod
    def _looks_like_map_request(cls, text: str) -> bool:
        normalized = cls._normalize_intent_text(text)
        if not normalized:
            return False
        map_keywords = (
            "carte",
            "map",
            "visualise",
            "visualiser",
            "montre",
            "montre moi",
            "ou est",
            "ou se trouve",
            "where is",
            "position",
            "trajet",
            "route",
        )
        return any(keyword in normalized for keyword in map_keywords)

    @classmethod
    def _looks_like_parcel_request(cls, text: str) -> bool:
        normalized = cls._normalize_intent_text(text)
        if not normalized:
            return False
        parcel_keywords = (
            "colis",
            "parcel",
            "tracking",
            "suivi",
            "livraison",
            "delivery",
            "retard",
            "delayed",
            "delay",
            "incident",
            "hub",
            "congestion",
            "point relais",
            "pickup",
            "locker",
            "relais",
        )
        return any(keyword in normalized for keyword in parcel_keywords)

    @staticmethod
    def _coerce_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1", "on"}:
                return True
            if normalized in {"false", "no", "0", "off"}:
                return False
        return default

    @staticmethod
    def _coerce_float(value: object, default: float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _coerce_action_kind(value: object, default: ActionKind) -> ActionKind:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "none":
                return "none"
            if normalized == "reroute":
                return "reroute"
            if normalized == "reschedule":
                return "reschedule"
        return default

    @staticmethod
    def _as_dict(value: object) -> dict[str, Any]:
        if isinstance(value, dict):
            return {str(k): v for k, v in value.items()}
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json")
            if isinstance(dumped, dict):
                return {str(k): v for k, v in dumped.items()}
        return {}

    @classmethod
    async def _invoke_first_available(
        cls,
        context: GraphNodeContext,
        tool_names: tuple[str, ...],
        arguments: dict[str, object],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for tool_name in tool_names:
            try:
                result = await context.invoke_runtime_tool(tool_name, arguments)
                return cls._as_dict(result)
            except RuntimeError as exc:
                last_error = exc
                continue
        raise RuntimeError(
            f"None of the required runtime tools are available: {', '.join(tool_names)}"
        ) from last_error

    @staticmethod
    def _safe_get(value: object, *path: str) -> object:
        current = value
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @classmethod
    def _parcel_candidates_from_response(cls, value: object) -> list[dict[str, Any]]:
        payload = cls._as_dict(value)
        raw_parcels = payload.get("parcels")
        if not isinstance(raw_parcels, list):
            return []
        return [
            cls._as_dict(parcel) for parcel in raw_parcels if isinstance(parcel, dict)
        ]

    @staticmethod
    def _parcel_choice_description(candidate: dict[str, Any]) -> str | None:
        location = Definition._as_dict(candidate.get("current_location"))
        parts: list[str] = []
        if candidate.get("status"):
            parts.append(f"statut={candidate['status']}")
        if candidate.get("delay_minutes") is not None:
            parts.append(f"retard={candidate['delay_minutes']} min")
        if location.get("label"):
            parts.append(f"position={location['label']}")
        return ", ".join(parts) if parts else None

    @classmethod
    def _events_from_response(cls, value: object) -> list[dict[str, Any]]:
        payload = cls._as_dict(value)
        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            return []
        return [cls._as_dict(event) for event in raw_events if isinstance(event, dict)]

    @classmethod
    def _pickup_points_from_response(cls, value: object) -> list[dict[str, Any]]:
        payload = cls._as_dict(value)
        raw_points = payload.get("pickup_points")
        if not isinstance(raw_points, list):
            return []
        return [cls._as_dict(point) for point in raw_points if isinstance(point, dict)]

    @classmethod
    def _map_overlay_from_snapshot(cls, snapshot: dict[str, Any]) -> dict[str, Any]:
        overlay = cls._as_dict(snapshot.get("map_overlay"))
        return {
            "route_polyline": overlay.get("route_polyline")
            if isinstance(overlay.get("route_polyline"), list)
            else [],
            "markers": overlay.get("markers")
            if isinstance(overlay.get("markers"), list)
            else [],
        }

    @classmethod
    def _map_overlay_from_route_response(
        cls, response: dict[str, Any]
    ) -> dict[str, Any]:
        route_geometry = cls._as_dict(response.get("route_geometry"))
        polyline = route_geometry.get("polyline")
        markers = response.get("markers")
        return {
            "route_polyline": polyline if isinstance(polyline, list) else [],
            "markers": markers if isinstance(markers, list) else [],
        }

    @staticmethod
    def _merge_map_overlay(
        primary: dict[str, Any], secondary: dict[str, Any]
    ) -> dict[str, Any]:
        route_polyline = secondary.get("route_polyline") or primary.get(
            "route_polyline"
        )
        markers = secondary.get("markers") or primary.get("markers")
        return {
            "route_polyline": route_polyline
            if isinstance(route_polyline, list)
            else [],
            "markers": markers if isinstance(markers, list) else [],
        }

    @staticmethod
    def _reschedule_choice_options() -> list[HumanChoiceOption]:
        today = datetime.now(UTC).date()
        options = [
            (today + timedelta(days=1), "morning", "Demain matin"),
            (today + timedelta(days=1), "afternoon", "Demain après-midi"),
            (today + timedelta(days=2), "evening", "Après-demain soirée"),
        ]
        choices: list[HumanChoiceOption] = []
        for index, (requested_date, time_window, label) in enumerate(options):
            choices.append(
                HumanChoiceOption(
                    id=f"reschedule:{requested_date.isoformat()}:{time_window}",
                    label=label,
                    description=f"{requested_date.isoformat()} / {time_window}",
                    default=index == 0,
                )
            )
        choices.append(
            HumanChoiceOption(
                id="cancel",
                label="Ne rien faire",
                description="Conserver seulement le diagnostic.",
            )
        )
        return choices

    @classmethod
    def _build_geojson(cls, state: TrackingGraphDemoState) -> dict[str, Any] | None:
        features: list[dict[str, Any]] = []

        route_polyline = state.map_overlay.get("route_polyline")
        if isinstance(route_polyline, list):
            coordinates: list[list[float]] = []
            for point in route_polyline:
                point_dict = cls._as_dict(point)
                lat = cls._coerce_optional_float(point_dict.get("lat"))
                lon = cls._coerce_optional_float(point_dict.get("lon"))
                if lat is None or lon is None:
                    continue
                coordinates.append([lon, lat])
            if len(coordinates) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coordinates,
                        },
                        "properties": {
                            "name": "Parcel route",
                            "kind": "route",
                        },
                    }
                )

        raw_markers = state.map_overlay.get("markers")
        if isinstance(raw_markers, list):
            for marker in raw_markers:
                marker_dict = cls._as_dict(marker)
                lat = cls._coerce_optional_float(marker_dict.get("lat"))
                lon = cls._coerce_optional_float(marker_dict.get("lon"))
                if lat is None or lon is None:
                    continue
                marker_id = str(marker_dict.get("id") or "")
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "properties": {
                            "name": str(
                                marker_dict.get("label") or marker_id or "Marker"
                            ),
                            "kind": str(marker_dict.get("kind") or "marker"),
                            "marker_id": marker_id or None,
                        },
                    }
                )

        for point in state.pickup_points[:5]:
            lat = cls._coerce_optional_float(point.get("lat"))
            lon = cls._coerce_optional_float(point.get("lon"))
            if lat is None or lon is None:
                continue
            pickup_point_id = str(point.get("pickup_point_id") or "")
            selected = (
                pickup_point_id and pickup_point_id == state.chosen_pickup_point_id
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "name": str(
                            point.get("name") or pickup_point_id or "Pickup point"
                        ),
                        "pickup_point_id": pickup_point_id or None,
                        "kind": "pickup_point",
                        "selected": bool(selected),
                    },
                }
            )

        if not features:
            return None
        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def _coerce_optional_float(value: object) -> float | None:
        if isinstance(value, (float, int)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None
