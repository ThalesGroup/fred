from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, timedelta
from typing import Annotated, Any, Dict, List, Optional, Sequence, Type, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerRef
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.interrupts.hitl_i18n import hitl_language_for_agent
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


class LaPosteState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    tracking_id: str
    business_seed: Dict[str, Any]
    iot_seed: Dict[str, Any]
    business_track: Dict[str, Any]
    iot_snapshot: Dict[str, Any]
    iot_events: List[Dict[str, Any]]
    pickup_points: List[Dict[str, Any]]
    chosen_action: str  # reroute | reschedule | cancel
    chosen_pickup_point_id: str
    chosen_pickup_point_name: str
    chosen_reschedule_date: str
    chosen_reschedule_window: str
    reroute_result: Dict[str, Any]
    reschedule_result: Dict[str, Any]
    notification_result: Dict[str, Any]
    final_text: str


@expose_runtime_source("agent.LaPosteDemoAgent")
class LaPosteDemoAgent(AgentFlow):
    """
    Controlled business demo agent for La Poste:
    - deterministic orchestration over two MCP servers (business + IoT)
    - explicit HITL choice card for relay selection vs home reschedule
    - tool calls remain visible in the trace (AI tool_call + ToolMessage)
    """

    tuning = AgentTuning(
        role="La Poste Operations Copilot",
        description=(
            "Agent métier démonstratif pour incidents colis (retard, reroutage, "
            "replanification) avec orchestration MCP et HITL."
        ),
        tags=["laposte", "postal", "iot", "hitl", "demo"],
        mcp_servers=[
            MCPServerRef(id="mcp-postal-business-demo"),
            MCPServerRef(id="mcp-iot-tracking-demo"),
        ],
        fields=[],
    )

    default_chat_options = AgentChatOptions(
        search_policy_selection=False,
        libraries_selection=False,
        search_rag_scoping=False,
        deep_search_delegate=False,
        attach_files=False,
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)
        self.mcp: Optional[MCPRuntime] = None

    def get_state_schema(self) -> Type:
        return LaPosteState

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()
        self._graph = self._build_graph()

    async def aclose(self):
        if self.mcp:
            await self.mcp.aclose()

    # -----------------------------
    # Graph definition
    # -----------------------------
    def _build_graph(self) -> StateGraph:
        g = StateGraph(LaPosteState)
        g.add_node("prepare_incident", self.prepare_incident)
        g.add_node("diagnose_incident", self.diagnose_incident)
        g.add_node("choose_resolution", self.choose_resolution_hitl)
        g.add_node("apply_reroute", self.apply_reroute)
        g.add_node("apply_reschedule", self.apply_reschedule)
        g.add_node("cancel_flow", self.cancel_flow)
        g.add_node("finalize", self.finalize_response)

        g.set_entry_point("prepare_incident")
        g.add_edge("prepare_incident", "diagnose_incident")
        g.add_edge("diagnose_incident", "choose_resolution")
        g.add_conditional_edges(
            "choose_resolution",
            self._route_after_choice,
            {
                "reroute": "apply_reroute",
                "reschedule": "apply_reschedule",
                "cancel": "cancel_flow",
            },
        )
        g.add_edge("apply_reroute", "finalize")
        g.add_edge("apply_reschedule", "finalize")
        g.add_edge("cancel_flow", "finalize")
        g.add_edge("finalize", END)
        return g

    # -----------------------------
    # Helpers
    # -----------------------------
    def _tool_map(self) -> Dict[str, BaseTool]:
        if not self.mcp:
            return {}
        tool_map: Dict[str, BaseTool] = {}
        for tool in self.mcp.get_tools():
            if tool.name in tool_map:
                logger.warning(
                    "[LaPosteDemoAgent] Duplicate tool name '%s' detected; last one wins",
                    tool.name,
                )
            tool_map[tool.name] = tool
        return tool_map

    @staticmethod
    def _latest_human_text(messages: Sequence[BaseMessage]) -> str:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                try:
                    return json.dumps(content, ensure_ascii=False)
                except Exception:
                    return str(content)
        return ""

    @staticmethod
    def _json_str(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    @staticmethod
    def _normalize_tool_output(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return raw
        if hasattr(raw, "model_dump"):
            try:
                return raw.model_dump()
            except Exception:
                return str(raw)
        return raw

    async def _call_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        *,
        tool_map: Optional[Dict[str, BaseTool]] = None,
    ) -> tuple[Any, List[BaseMessage]]:
        tools = tool_map or self._tool_map()
        tool = tools.get(tool_name)
        if not tool:
            raise RuntimeError(f"Tool '{tool_name}' not found for LaPosteDemoAgent")

        call_id = f"call_{uuid.uuid4().hex[:20]}"
        tool_call_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": call_id,
                    "name": tool_name,
                    "args": args,
                    "type": "tool_call",
                }
            ],
        )
        try:
            raw = await tool.ainvoke(args)
            payload = self._normalize_tool_output(raw)
            ok = not (isinstance(payload, dict) and payload.get("ok") is False)
            tool_result_msg = ToolMessage(
                content=self._json_str(payload),
                tool_call_id=call_id,
                name=tool_name,
                status="success" if ok else "error",
            )
            return payload, [tool_call_msg, tool_result_msg]
        except Exception as exc:
            logger.exception(
                "[LaPosteDemoAgent] Tool call failed tool=%s args=%s", tool_name, args
            )
            err_payload = {"ok": False, "error": str(exc)}
            tool_result_msg = ToolMessage(
                content=self._json_str(err_payload),
                tool_call_id=call_id,
                name=tool_name,
                status="error",
            )
            return err_payload, [tool_call_msg, tool_result_msg]

    @staticmethod
    def _extract_tracking_id(text: str) -> Optional[str]:
        if not text:
            return None
        m = re.search(r"\b(PKG-[A-Z0-9-]+)\b", text.upper())
        return m.group(1) if m else None

    @staticmethod
    def _tomorrow_str() -> str:
        return (date.today() + timedelta(days=1)).isoformat()

    @staticmethod
    def _safe_get(d: Any, *path: str, default: Any = None) -> Any:
        cur = d
        for key in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(key)
            if cur is None:
                return default
        return cur

    @staticmethod
    def _parse_choice(
        decision: Dict[str, Any], pickup_points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        choice_id = str(
            decision.get("choice_id") or decision.get("answer") or ""
        ).strip()
        free_text = str(decision.get("text") or decision.get("notes") or "").strip()
        combined = f"{choice_id} {free_text}".strip()
        combined_upper = combined.upper()

        if choice_id.startswith("reroute:"):
            pp_id = choice_id.split(":", 1)[1].strip()
            return {"action": "reroute", "pickup_point_id": pp_id}

        if choice_id.startswith("reschedule:"):
            window = choice_id.split(":", 1)[1].strip().lower() or "afternoon"
            return {"action": "reschedule", "time_window": window}

        if choice_id == "cancel":
            return {"action": "cancel"}

        # free-text fallback
        pp_match = re.search(r"\bPP-[A-Z]{3}-\d{3}\b", combined_upper)
        if pp_match:
            return {"action": "reroute", "pickup_point_id": pp_match.group(0)}

        if any(
            word in combined_upper
            for word in ["REPLAN", "DOMICILE", "AFTERNOON", "APRES", "APRÈS"]
        ):
            window = "afternoon"
            if "MORNING" in combined_upper or "MATIN" in combined_upper:
                window = "morning"
            elif "EVENING" in combined_upper or "SOIR" in combined_upper:
                window = "evening"
            return {"action": "reschedule", "time_window": window}

        if any(word in combined_upper for word in ["ANNUL", "CANCEL", "STOP"]):
            return {"action": "cancel"}

        # default to recommended first pickup point
        if pickup_points:
            return {
                "action": "reroute",
                "pickup_point_id": str(pickup_points[0].get("pickup_point_id")),
            }
        return {"action": "cancel"}

    def _route_after_choice(self, state: LaPosteState) -> str:
        action = state.get("chosen_action") or "cancel"
        if action == "reroute":
            return "reroute"
        if action == "reschedule":
            return "reschedule"
        return "cancel"

    # -----------------------------
    # Nodes
    # -----------------------------
    async def prepare_incident(self, state: LaPosteState) -> Dict[str, Any]:
        tool_map = self._tool_map()
        msgs: List[BaseMessage] = []
        latest_user = self._latest_human_text(state.get("messages", []))
        tracking_id = self._extract_tracking_id(latest_user)

        business_seed: Dict[str, Any] = {}
        iot_seed: Dict[str, Any] = {}

        if not tracking_id:
            business_seed_raw, m = await self._call_tool(
                "seed_demo_parcel_exception", {}, tool_map=tool_map
            )
            msgs.extend(m)
            if (
                not isinstance(business_seed_raw, dict)
                or business_seed_raw.get("ok") is False
            ):
                raise RuntimeError(
                    f"seed_demo_parcel_exception failed: {business_seed_raw}"
                )
            business_seed = business_seed_raw
            tracking_id = str(business_seed.get("tracking_id") or "")

        if not tracking_id:
            raise RuntimeError("No tracking_id available after seeding/parsing")

        iot_seed_raw, m = await self._call_tool(
            "seed_demo_tracking_incident",
            {"tracking_id": tracking_id},
            tool_map=tool_map,
        )
        msgs.extend(m)
        if isinstance(iot_seed_raw, dict):
            iot_seed = iot_seed_raw

        return {
            "messages": msgs,
            "tracking_id": tracking_id,
            "business_seed": business_seed,
            "iot_seed": iot_seed,
        }

    async def diagnose_incident(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id")
        if not tracking_id:
            raise RuntimeError("Missing tracking_id in diagnose_incident")

        tool_map = self._tool_map()
        msgs: List[BaseMessage] = []

        business_track, m = await self._call_tool(
            "track_package", {"tracking_id": tracking_id}, tool_map=tool_map
        )
        msgs.extend(m)
        iot_snapshot, m = await self._call_tool(
            "get_live_tracking_snapshot",
            {"tracking_id": tracking_id},
            tool_map=tool_map,
        )
        msgs.extend(m)
        iot_events_raw, m = await self._call_tool(
            "list_tracking_events",
            {"tracking_id": tracking_id, "since_seq": 0, "limit": 5},
            tool_map=tool_map,
        )
        msgs.extend(m)

        track_dict = business_track if isinstance(business_track, dict) else {}
        delivery_addr = (
            self._safe_get(track_dict, "delivery", "address", default={}) or {}
        )
        city = delivery_addr.get("city") or "Paris"
        postal_code = delivery_addr.get("postal_code") or "75015"

        pickup_resp, m = await self._call_tool(
            "get_pickup_points_nearby",
            {"city": city, "postal_code": postal_code, "limit": 3},
            tool_map=tool_map,
        )
        msgs.extend(m)

        pickup_points = []
        if isinstance(pickup_resp, dict):
            raw_points = pickup_resp.get("pickup_points") or []
            if isinstance(raw_points, list):
                pickup_points = [p for p in raw_points if isinstance(p, dict)]

        # Enrich locker telemetry when possible (demo UX value)
        for point in pickup_points:
            if point.get("type") != "locker":
                continue
            pp_id = point.get("pickup_point_id")
            if not isinstance(pp_id, str):
                continue
            locker_resp, m = await self._call_tool(
                "get_locker_occupancy", {"pickup_point_id": pp_id}, tool_map=tool_map
            )
            msgs.extend(m)
            if isinstance(locker_resp, dict) and locker_resp.get("ok"):
                point["locker_telemetry"] = locker_resp.get("telemetry")

        iot_events = []
        if isinstance(iot_events_raw, dict) and isinstance(
            iot_events_raw.get("events"), list
        ):
            iot_events = [e for e in iot_events_raw["events"] if isinstance(e, dict)]

        # Brief structured summary before the HITL card
        delay_min = self._safe_get(track_dict, "eta", "delay_minutes", default=None)
        hub_congestion = self._safe_get(
            iot_snapshot, "hub_status", "congestion_level", default=None
        )
        phase = self._safe_get(iot_snapshot, "phase", default=None)
        summary_text = (
            "Diagnostic établi. Je vais maintenant te proposer une carte de décision "
            "(choix relais ou replanification) pour lancer l'action.\n\n"
            f"- `tracking_id`: `{tracking_id}`\n"
            f"- Statut métier: `{track_dict.get('status', 'UNKNOWN')}`\n"
            f"- Retard estimé: `{delay_min if delay_min is not None else 'n/a'} min`\n"
            f"- IoT hub congestion: `{hub_congestion or 'n/a'}`\n"
            f"- Phase IoT: `{phase or 'n/a'}`"
        )

        return {
            "messages": [*msgs, AIMessage(content=summary_text)],
            "business_track": track_dict,
            "iot_snapshot": iot_snapshot if isinstance(iot_snapshot, dict) else {},
            "iot_events": iot_events,
            "pickup_points": pickup_points,
        }

    async def choose_resolution_hitl(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        pickup_points = state.get("pickup_points") or []
        business_track = state.get("business_track") or {}
        iot_snapshot = state.get("iot_snapshot") or {}
        is_fr = hitl_language_for_agent(self) == "fr"

        recommended_id = None
        if pickup_points:
            recommended_id = str(pickup_points[0].get("pickup_point_id"))

        choices: List[Dict[str, Any]] = []
        for idx, point in enumerate(pickup_points[:3]):
            pp_id = str(point.get("pickup_point_id"))
            name = str(point.get("name") or pp_id)
            opening = str(point.get("opening_hours") or "")
            avail = point.get("available_slots")
            desc = []
            if point.get("type"):
                desc.append(f"type={point.get('type')}")
            if avail is not None:
                desc.append(f"places={avail}")
            if opening:
                desc.append(f"horaires={opening}")
            label = f"{pp_id} - {name}"
            choice: Dict[str, Any] = {
                "id": f"reroute:{pp_id}",
                "label": label[:80],
                "description": (
                    ", ".join(desc)[:200]
                    if desc
                    else (
                        "Rerouter vers ce point relais."
                        if is_fr
                        else "Reroute to this pickup point."
                    )
                ),
            }
            if idx == 0:
                choice["default"] = True
            choices.append(choice)

        choices.extend(
            [
                {
                    "id": "reschedule:afternoon",
                    "label": (
                        "Replanifier domicile (demain après-midi)"
                        if is_fr
                        else "Reschedule home delivery (tomorrow afternoon)"
                    ),
                    "description": (
                        "Conserver la livraison à domicile et proposer un nouveau créneau."
                        if is_fr
                        else "Keep home delivery and propose a new time window."
                    ),
                },
                {
                    "id": "cancel",
                    "label": "Ne rien faire" if is_fr else "Do nothing",
                    "description": (
                        "Aucune action métier, garder uniquement le diagnostic."
                        if is_fr
                        else "No business action, keep the diagnosis only."
                    ),
                },
            ]
        )

        if is_fr:
            title = "Choisir une action de résolution"
            question = (
                f"Le colis `{tracking_id}` est en retard. Quelle action veux-tu que j'exécute ? "
                "Choisis un point relais ou une replanification à domicile."
            )
        else:
            title = "Choose a resolution action"
            question = (
                f"Parcel `{tracking_id}` is delayed. Which action should I execute? "
                "Choose a pickup point or a home delivery reschedule."
            )

        decision = interrupt(
            {
                "stage": "la_poste_resolution_choice",
                "title": title,
                "question": question,
                "choices": choices,
                "free_text": True,
                "metadata": {
                    "tracking_id": tracking_id,
                    "recommended_pickup_point_id": recommended_id,
                    "business_status": business_track.get("status"),
                    "delay_minutes": self._safe_get(
                        business_track, "eta", "delay_minutes", default=None
                    ),
                    "iot_phase": iot_snapshot.get("phase"),
                    "pickup_points": pickup_points,
                },
            }
        )

        parsed = self._parse_choice(
            decision if isinstance(decision, dict) else {},
            pickup_points=pickup_points,
        )
        action = parsed.get("action", "cancel")

        update: Dict[str, Any] = {"chosen_action": action}
        if action == "reroute":
            pp_id = str(parsed.get("pickup_point_id") or "")
            update["chosen_pickup_point_id"] = pp_id
            for point in pickup_points:
                if str(point.get("pickup_point_id")) == pp_id:
                    update["chosen_pickup_point_name"] = str(point.get("name") or pp_id)
                    break
        elif action == "reschedule":
            update["chosen_reschedule_date"] = self._tomorrow_str()
            window = str(parsed.get("time_window") or "afternoon").lower()
            if window not in {"morning", "afternoon", "evening"}:
                window = "afternoon"
            update["chosen_reschedule_window"] = window

        return update

    async def apply_reroute(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id")
        pickup_point_id = state.get("chosen_pickup_point_id")
        if not tracking_id or not pickup_point_id:
            raise RuntimeError(
                "Missing tracking_id or pickup_point_id in apply_reroute"
            )

        tool_map = self._tool_map()
        msgs: List[BaseMessage] = []

        reroute_result, m = await self._call_tool(
            "reroute_package_to_pickup_point",
            {
                "tracking_id": tracking_id,
                "pickup_point_id": pickup_point_id,
                "reason": "customer_choice_via_hitl",
            },
            tool_map=tool_map,
        )
        msgs.extend(m)

        point_name = state.get("chosen_pickup_point_name") or pickup_point_id
        notify_message = (
            f"Votre colis {tracking_id} a ete reroute vers {point_name} ({pickup_point_id}). "
            "Vous recevrez une notification lorsqu'il sera disponible au retrait."
        )
        notify_result, m = await self._call_tool(
            "notify_customer",
            {
                "tracking_id": tracking_id,
                "channel": "sms",
                "message": notify_message,
            },
            tool_map=tool_map,
        )
        msgs.extend(m)

        return {
            "messages": msgs,
            "reroute_result": reroute_result
            if isinstance(reroute_result, dict)
            else {},
            "notification_result": notify_result
            if isinstance(notify_result, dict)
            else {},
        }

    async def apply_reschedule(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id")
        requested_date = state.get("chosen_reschedule_date") or self._tomorrow_str()
        time_window = state.get("chosen_reschedule_window") or "afternoon"
        if not tracking_id:
            raise RuntimeError("Missing tracking_id in apply_reschedule")

        tool_map = self._tool_map()
        msgs: List[BaseMessage] = []

        reschedule_result, m = await self._call_tool(
            "reschedule_delivery",
            {
                "tracking_id": tracking_id,
                "requested_date": requested_date,
                "time_window": time_window,
            },
            tool_map=tool_map,
        )
        msgs.extend(m)

        notify_message = f"Votre colis {tracking_id} a ete replanifie pour le {requested_date} ({time_window})."
        notify_result, m = await self._call_tool(
            "notify_customer",
            {
                "tracking_id": tracking_id,
                "channel": "sms",
                "message": notify_message,
            },
            tool_map=tool_map,
        )
        msgs.extend(m)

        return {
            "messages": msgs,
            "reschedule_result": reschedule_result
            if isinstance(reschedule_result, dict)
            else {},
            "notification_result": notify_result
            if isinstance(notify_result, dict)
            else {},
        }

    async def cancel_flow(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"Aucune action métier n'a été exécutée pour `{tracking_id}`. "
                        "Je garde le diagnostic disponible si tu veux choisir une action ensuite."
                    )
                )
            ]
        }

    async def finalize_response(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        action = state.get("chosen_action") or "cancel"
        business_track = state.get("business_track") or {}
        iot_snapshot = state.get("iot_snapshot") or {}
        pickup_points = state.get("pickup_points") or []

        if action == "reroute":
            reroute = state.get("reroute_result") or {}
            delivery = reroute.get("delivery") or {}
            eta = reroute.get("eta") or {}
            point_id = (
                delivery.get("pickup_point_id")
                or state.get("chosen_pickup_point_id")
                or "n/a"
            )
            point_name = (
                delivery.get("pickup_point_name")
                or state.get("chosen_pickup_point_name")
                or point_id
            )
            notif = state.get("notification_result") or {}
            text = (
                "Action réalisée via agent métier (HITL de choix)\n\n"
                f"- Colis: `{tracking_id}`\n"
                f"- Action: reroutage vers point relais `{point_id}` ({point_name})\n"
                f"- Nouveau statut: `{reroute.get('status', 'n/a')}`\n"
                f"- Retard estimé (minutes): `{eta.get('delay_minutes', 'n/a')}`\n"
                f"- Notification client: `{notif.get('notification_id', 'non envoyée')}` (SMS)\n\n"
                "Différence avec un agent ReAct générique:\n"
                "- ici, le choix métier est capturé via une carte HITL structurée (pas une réponse texte libre)\n"
                "- l'action exécutée correspond directement au choix UI\n\n"
                f"`tracking_id`: `{tracking_id}`"
            )
            return {"messages": [AIMessage(content=text)], "final_text": text}

        if action == "reschedule":
            res = state.get("reschedule_result") or {}
            delivery = res.get("delivery") or {}
            notif = state.get("notification_result") or {}
            text = (
                "Action réalisée via agent métier (HITL de choix)\n\n"
                f"- Colis: `{tracking_id}`\n"
                "- Action: replanification de livraison à domicile\n"
                f"- Date: `{delivery.get('scheduled_date', state.get('chosen_reschedule_date', 'n/a'))}`\n"
                f"- Créneau: `{delivery.get('time_window', state.get('chosen_reschedule_window', 'n/a'))}`\n"
                f"- Nouveau statut: `{res.get('status', 'n/a')}`\n"
                f"- Notification client: `{notif.get('notification_id', 'non envoyée')}` (SMS)\n\n"
                f"`tracking_id`: `{tracking_id}`"
            )
            return {"messages": [AIMessage(content=text)], "final_text": text}

        # cancel / fallback
        top_points = []
        for point in pickup_points[:3]:
            pp_id = point.get("pickup_point_id")
            if pp_id:
                top_points.append(str(pp_id))
        text = (
            "Diagnostic disponible, aucune action exécutée.\n\n"
            f"- Colis: `{tracking_id}`\n"
            f"- Statut métier: `{business_track.get('status', 'n/a')}`\n"
            f"- Phase IoT: `{iot_snapshot.get('phase', 'n/a')}`\n"
            f"- Options relais observées: {', '.join(top_points) if top_points else 'n/a'}\n\n"
            f"`tracking_id`: `{tracking_id}`"
        )
        return {"messages": [AIMessage(content=text)], "final_text": text}
