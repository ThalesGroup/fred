from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, timedelta
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    TypedDict,
    cast,
)

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerRef
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import GeoPart, MessagePart, TextPart
from agentic_backend.core.interrupts.hitl_i18n import hitl_language_for_agent
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


class LaPosteState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    request_mode: str  # action_flow | followup_info
    routing_mode_source: str  # heuristic | llm | default
    latest_user_text: str
    tracking_changed_hint: bool
    tracking_id: str
    business_seed: Dict[str, Any]
    iot_seed: Dict[str, Any]
    business_track: Dict[str, Any]
    iot_snapshot: Dict[str, Any]
    iot_events: List[Dict[str, Any]]
    pickup_points: List[Dict[str, Any]]
    read_only_plan: List[Dict[str, Any]]
    read_only_results: Dict[str, Any]
    chosen_action: str  # reroute | reschedule | cancel
    chosen_pickup_point_id: str
    chosen_pickup_point_name: str
    chosen_reschedule_date: str
    chosen_reschedule_window: str
    reroute_result: Dict[str, Any]
    reschedule_result: Dict[str, Any]
    notification_result: Dict[str, Any]
    final_text: str


@expose_runtime_source("agent.ParcelOpsAgent")
class ParcelOpsAgent(AgentFlow):
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
        self.model = None

    def get_state_schema(self) -> Type:
        return LaPosteState

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)
        self.model = get_default_chat_model()
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
        g.add_node("route_request", self.route_request)
        g.add_node("prepare_incident", self.prepare_incident)
        g.add_node("diagnose_incident", self.diagnose_incident)
        g.add_node("respond_followup", self.respond_followup)
        g.add_node("choose_resolution", self.choose_resolution_hitl)
        g.add_node("apply_reroute", self.apply_reroute)
        g.add_node("apply_reschedule", self.apply_reschedule)
        g.add_node("cancel_flow", self.cancel_flow)
        g.add_node("finalize", self.finalize_response)

        g.set_entry_point("route_request")
        g.add_edge("route_request", "prepare_incident")
        g.add_edge("prepare_incident", "diagnose_incident")
        g.add_conditional_edges(
            "diagnose_incident",
            self._route_after_diagnosis,
            {
                "resolution": "choose_resolution",
                "followup": "respond_followup",
            },
        )
        g.add_edge("respond_followup", END)
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

    def _route_after_diagnosis(self, state: LaPosteState) -> str:
        if (state.get("request_mode") or "").strip().lower() == "followup_info":
            return "followup"
        return "resolution"

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "\n".join([c.strip() for c in chunks if c and c.strip()]).strip()
        return str(content).strip()

    @staticmethod
    def _looks_like_action_request(text: str) -> bool:
        t = (text or "").lower()
        if not t:
            return False
        action_keywords = (
            "reroute",
            "re-route",
            "relay",
            "relais",
            "pickup point",
            "point relais",
            "locker",
            "reschedule",
            "replanif",
            "replanifier",
            "replanification",
            "annule",
            "cancel",
            "notifie",
            "notify",
            "execute",
            "exécute",
        )
        return any(k in t for k in action_keywords)

    @staticmethod
    def _looks_like_info_followup(text: str) -> bool:
        t = (text or "").lower()
        if not t:
            return False
        info_keywords = (
            "rappelle",
            "rappel",
            "résume",
            "resume",
            "summary",
            "summarize",
            "etat",
            "état",
            "status",
            "iot",
            "phase",
            "congestion",
            "position",
            "vehicle",
            "véhicule",
            "where is",
            "où",
            "tracking_id",
            "numéro de suivi",
            "suivi",
        )
        return any(k in t for k in info_keywords)

    @staticmethod
    def _looks_like_identification_request(text: str) -> bool:
        t = (text or "").lower().strip()
        if not t:
            return False
        patterns = (
            "quel est mon colis",
            "quel colis",
            "donne-moi le tracking",
            "donne moi le tracking",
            "tracking id",
            "numéro de suivi",
            "numero de suivi",
            "which parcel",
            "what is my parcel",
            "what's my parcel",
        )
        return any(p in t for p in patterns)

    @staticmethod
    def _parse_json_object_from_text(text: str) -> Optional[Dict[str, Any]]:
        raw = (text or "").strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            logger.warning(
                "[LaPosteDemoAgent] Text does not look like pure JSON, attempting to extract JSON object from text"
            )

        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    @staticmethod
    def _read_only_tool_whitelist() -> tuple[str, ...]:
        return (
            "get_live_tracking_snapshot",
            "list_tracking_events",
            "get_pickup_points_nearby",
            "get_route_geometry",
            "get_hub_status",
            "get_vehicle_position",
            "estimate_compensation",
        )

    @staticmethod
    def _read_only_tool_plan_schema_hint() -> str:
        return (
            '{"calls":[{"tool":"get_live_tracking_snapshot","args":{}},'
            '{"tool":"list_tracking_events","args":{"limit":5}},'
            '{"tool":"get_pickup_points_nearby","args":{"limit":3}}]}'
        )

    async def _llm_plan_read_only_calls(
        self,
        *,
        state: LaPosteState,
        tracking_id: str,
        city: str,
        postal_code: str,
    ) -> Optional[List[Dict[str, Any]]]:
        if not self.model:
            return None

        latest_user = state.get("latest_user_text") or self._latest_human_text(
            state.get("messages", [])
        )
        request_mode = state.get("request_mode") or "action_flow"
        allowed = ", ".join(self._read_only_tool_whitelist())
        prompt = (
            "You are planning read-only MCP calls for a parcel operations agent.\n"
            "Return JSON ONLY.\n"
            "The agent already called `track_package` and has delivery city/postal code.\n"
            "Never include mutating tools. Never include `track_package`.\n"
            "Choose 2 to 5 calls max, prioritize tools useful for diagnosis, map display, and follow-up recap.\n"
            "Allowed tools: "
            f"{allowed}\n"
            "For `list_tracking_events`, optional args: `limit` (1..10), `since_seq` (>=0).\n"
            "For `get_pickup_points_nearby`, optional arg: `limit` (1..5). City/postal_code are auto-filled.\n"
            "For `get_hub_status` / `get_vehicle_position`, ids can be omitted if not known yet (executor may infer after snapshot).\n"
            "Schema (exact top-level key): "
            f"{self._read_only_tool_plan_schema_hint()}\n"
            f"Request mode: {request_mode}\n"
            f"User message: {latest_user}\n"
            f"tracking_id: {tracking_id}\n"
            f"delivery_city: {city}\n"
            f"delivery_postal_code: {postal_code}\n"
        )
        try:
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(resp, "content", ""))
            parsed = self._parse_json_object_from_text(text) or {}
            calls = parsed.get("calls")
            if not isinstance(calls, list):
                return None
            clean_calls: List[Dict[str, Any]] = []
            for call in calls[:6]:
                if not isinstance(call, dict):
                    continue
                tool = str(call.get("tool") or "").strip()
                if not tool:
                    continue
                args = call.get("args")
                if not isinstance(args, dict):
                    args = {}
                clean_calls.append({"tool": tool, "args": args})
            return clean_calls or None
        except Exception as exc:
            logger.warning(
                "[LaPosteDemoAgent] LLM read-only planner failed (%s: %s); using deterministic diagnosis sequence",
                exc.__class__.__name__,
                exc,
            )
            return None

    def _resolve_read_only_plan_call_args(
        self,
        *,
        tool_name: str,
        proposed_args: Dict[str, Any],
        tracking_id: str,
        city: str,
        postal_code: str,
        results: Dict[str, Any],
        state: LaPosteState,
    ) -> Optional[Dict[str, Any]]:
        snapshot = results.get("get_live_tracking_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = (
                state.get("iot_snapshot")
                if isinstance(state.get("iot_snapshot"), dict)
                else {}
            )
        snapshot = snapshot or {}

        if tool_name == "get_live_tracking_snapshot":
            return {"tracking_id": tracking_id}

        if tool_name == "list_tracking_events":
            limit = proposed_args.get("limit", 5)
            since_seq = proposed_args.get("since_seq", 0)
            try:
                limit_i = int(limit)
            except (TypeError, ValueError):
                limit_i = 5
            try:
                since_seq_i = int(since_seq)
            except (TypeError, ValueError):
                since_seq_i = 0
            limit_i = max(1, min(limit_i, 10))
            since_seq_i = max(0, since_seq_i)
            return {
                "tracking_id": tracking_id,
                "since_seq": since_seq_i,
                "limit": limit_i,
            }

        if tool_name == "get_pickup_points_nearby":
            limit = proposed_args.get("limit", 3)
            try:
                limit_i = int(limit)
            except (TypeError, ValueError):
                limit_i = 3
            limit_i = max(1, min(limit_i, 5))
            return {"city": city, "postal_code": postal_code, "limit": limit_i}

        if tool_name == "get_route_geometry":
            return {"tracking_id": tracking_id}

        if tool_name == "estimate_compensation":
            return {"tracking_id": tracking_id}

        if tool_name == "get_hub_status":
            hub_id = str(
                proposed_args.get("hub_id")
                or self._safe_get(snapshot, "hub_status", "hub_id", default="")
                or ""
            ).strip()
            tracking_hint = str(proposed_args.get("tracking_id") or tracking_id).strip()
            if not hub_id:
                return None
            return {"hub_id": hub_id, "tracking_id": tracking_hint or None}

        if tool_name == "get_vehicle_position":
            vehicle_id = str(
                proposed_args.get("vehicle_id")
                or self._safe_get(
                    snapshot, "vehicle_position", "vehicle_id", default=""
                )
                or ""
            ).strip()
            tracking_hint = str(proposed_args.get("tracking_id") or tracking_id).strip()
            if not vehicle_id:
                return None
            return {"vehicle_id": vehicle_id, "tracking_id": tracking_hint or None}

        return None

    async def _execute_read_only_plan(
        self,
        *,
        state: LaPosteState,
        tracking_id: str,
        city: str,
        postal_code: str,
        calls: List[Dict[str, Any]],
        tool_map: Dict[str, BaseTool],
    ) -> tuple[Dict[str, Any], List[BaseMessage], List[Dict[str, Any]]]:
        allowed = set(self._read_only_tool_whitelist())
        results: Dict[str, Any] = {}
        msgs: List[BaseMessage] = []
        executed: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for call in calls[:6]:
            tool_name = str(call.get("tool") or "").strip()
            raw_args = call.get("args")
            proposed_args: Dict[str, Any] = {}
            if isinstance(raw_args, dict):
                proposed_args = {str(k): v for k, v in raw_args.items()}
            if not tool_name:
                continue
            if tool_name not in allowed:
                executed.append(
                    {
                        "tool": tool_name,
                        "status": "rejected",
                        "reason": "not_whitelisted_read_only",
                    }
                )
                continue
            if tool_name in seen:
                executed.append(
                    {"tool": tool_name, "status": "skipped", "reason": "duplicate"}
                )
                continue

            resolved_args = self._resolve_read_only_plan_call_args(
                tool_name=tool_name,
                proposed_args=proposed_args,
                tracking_id=tracking_id,
                city=city,
                postal_code=postal_code,
                results=results,
                state=state,
            )
            if resolved_args is None:
                executed.append(
                    {
                        "tool": tool_name,
                        "status": "skipped",
                        "reason": "missing_context",
                    }
                )
                continue

            payload, m = await self._call_tool(
                tool_name, resolved_args, tool_map=tool_map
            )
            msgs.extend(m)
            seen.add(tool_name)
            results[tool_name] = payload
            executed.append(
                {
                    "tool": tool_name,
                    "status": "ok"
                    if not (isinstance(payload, dict) and payload.get("ok") is False)
                    else "error",
                    "args": resolved_args,
                }
            )

        return results, msgs, executed

    @staticmethod
    def _pickup_points_from_response(pickup_resp: Any) -> List[Dict[str, Any]]:
        if not isinstance(pickup_resp, dict):
            return []
        raw_points = pickup_resp.get("pickup_points") or []
        if not isinstance(raw_points, list):
            return []
        return [p for p in raw_points if isinstance(p, dict)]

    async def _enrich_pickup_points_with_locker_telemetry(
        self,
        pickup_points: List[Dict[str, Any]],
        *,
        tool_map: Dict[str, BaseTool],
    ) -> tuple[List[Dict[str, Any]], List[BaseMessage]]:
        msgs: List[BaseMessage] = []
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
        return pickup_points, msgs

    async def _classify_request_mode_with_llm(
        self,
        *,
        latest_user: str,
        has_tracking_context: bool,
    ) -> Optional[str]:
        if not self.model or not has_tracking_context or not latest_user.strip():
            return None

        prompt = (
            "Classify the user's latest message in a parcel operations chat.\n"
            "Context: there is already an active tracking_id in session state.\n"
            "Return JSON only with this exact schema: "
            '{"mode":"followup_info"|"action_flow"}.\n'
            "Choose `followup_info` when the user asks only for status, recap, location, IoT state, explanation, or summary.\n"
            "Choose `action_flow` when the user asks to execute or choose an action such as reroute/reschedule/cancel/notify.\n"
            f"User message: {latest_user}"
        )
        try:
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(resp, "content", ""))
            parsed = self._parse_json_object_from_text(text) or {}
            mode = str(parsed.get("mode") or "").strip()
            if mode in {"followup_info", "action_flow"}:
                return mode
        except Exception as exc:
            logger.warning(
                "[LaPosteDemoAgent] LLM request-mode classification failed (%s: %s); using heuristics/default",
                exc.__class__.__name__,
                exc,
            )
        return None

    async def _llm_followup_summary_text(self, state: LaPosteState) -> Optional[str]:
        if not self.model:
            return None

        latest_user = state.get("latest_user_text") or self._latest_human_text(
            state.get("messages", [])
        )
        extra_read_only = {
            k: v
            for k, v in (state.get("read_only_results") or {}).items()
            if k
            not in {
                "get_live_tracking_snapshot",
                "list_tracking_events",
                "get_pickup_points_nearby",
            }
        }
        payload = {
            "tracking_id": state.get("tracking_id"),
            "business_track": state.get("business_track") or {},
            "iot_snapshot": state.get("iot_snapshot") or {},
            "iot_events": (state.get("iot_events") or [])[:5],
            "pickup_points": (state.get("pickup_points") or [])[:3],
            "read_only_results": extra_read_only,
        }
        prompt = (
            "You are a parcel operations copilot. Answer the user's follow-up using ONLY the JSON data provided.\n"
            "Be concise. Use bullet points. Mention the tracking_id explicitly. If data is missing, say 'n/a'.\n"
            "Do not propose actions unless the user asked for one.\n"
            f"User follow-up: {latest_user}\n\n"
            f"Data:\n{self._json_str(payload)}"
        )
        try:
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(resp, "content", ""))
            if text:
                return text
        except Exception as exc:
            logger.warning(
                "[LaPosteDemoAgent] LLM follow-up summary failed (%s: %s); using deterministic fallback",
                exc.__class__.__name__,
                exc,
            )
        return None

    def _fallback_followup_summary_text(self, state: LaPosteState) -> str:
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        business_track = state.get("business_track") or {}
        iot_snapshot = state.get("iot_snapshot") or {}
        vehicle = (
            iot_snapshot.get("vehicle_position")
            if isinstance(iot_snapshot, dict)
            else {}
        ) or {}
        hub_status = (
            iot_snapshot.get("hub_status") if isinstance(iot_snapshot, dict) else {}
        ) or {}
        phase = iot_snapshot.get("phase") if isinstance(iot_snapshot, dict) else None
        congestion = hub_status.get("congestion_level")
        veh_status = vehicle.get("status")
        veh_lat = vehicle.get("lat")
        veh_lon = vehicle.get("lon")
        route_progress = (
            iot_snapshot.get("route_progress_percent")
            if isinstance(iot_snapshot, dict)
            else None
        )
        return (
            "Récapitulatif de suivi (conversation en cours)\n\n"
            f"- `tracking_id`: `{tracking_id}`\n"
            f"- Statut métier: `{business_track.get('status', 'n/a')}`\n"
            f"- Phase IoT: `{phase or 'n/a'}`\n"
            f"- Congestion hub: `{congestion or 'n/a'}`\n"
            f"- Véhicule: `{vehicle.get('vehicle_id', 'n/a')}` / statut `{veh_status or 'n/a'}`\n"
            f"- Position véhicule: `{veh_lat if veh_lat is not None else 'n/a'}`, `{veh_lon if veh_lon is not None else 'n/a'}`\n"
            f"- Progression route: `{route_progress if route_progress is not None else 'n/a'}%`"
        )

    async def _llm_diagnosis_summary_text(self, state: LaPosteState) -> Optional[str]:
        if not self.model:
            return None
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        request_mode = state.get("request_mode") or "action_flow"
        is_fr = hitl_language_for_agent(self) == "fr"
        extra_read_only = {
            k: v
            for k, v in (state.get("read_only_results") or {}).items()
            if k
            not in {
                "get_live_tracking_snapshot",
                "list_tracking_events",
                "get_pickup_points_nearby",
            }
        }
        payload = {
            "tracking_id": tracking_id,
            "request_mode": request_mode,
            "business_track": state.get("business_track") or {},
            "iot_snapshot": state.get("iot_snapshot") or {},
            "iot_events": (state.get("iot_events") or [])[:5],
            "pickup_points": (state.get("pickup_points") or [])[:3],
            "read_only_results": extra_read_only,
        }
        language = "French" if is_fr else "English"
        mode_hint = (
            "This is pre-HITL diagnostic before proposing actions."
            if request_mode != "followup_info"
            else "This is informational follow-up diagnostic refresh (no action proposal)."
        )
        prompt = (
            "You are a parcel operations copilot.\n"
            f"Write a concise {language} diagnosis summary using ONLY the JSON payload.\n"
            "Use short bullets. Mention tracking_id explicitly.\n"
            "Include: business status, delay estimate if available, IoT phase, hub congestion, vehicle position if available.\n"
            f"{mode_hint}\n"
            "Do not invent fields. If missing, write 'n/a'.\n"
            f"Data:\n{self._json_str(payload)}"
        )
        try:
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(resp, "content", ""))
            if text:
                return text
        except Exception as exc:
            logger.warning(
                "[LaPosteDemoAgent] LLM diagnosis summary failed (%s: %s); using deterministic fallback",
                exc.__class__.__name__,
                exc,
            )
        return None

    def _fallback_diagnosis_summary_text(self, state: LaPosteState) -> str:
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        track_dict = state.get("business_track") or {}
        iot_snapshot = state.get("iot_snapshot") or {}
        delay_min = self._safe_get(track_dict, "eta", "delay_minutes", default=None)
        hub_congestion = self._safe_get(
            iot_snapshot, "hub_status", "congestion_level", default=None
        )
        phase = self._safe_get(iot_snapshot, "phase", default=None)
        vehicle = self._safe_get(iot_snapshot, "vehicle_position", default={}) or {}
        lat = vehicle.get("lat")
        lon = vehicle.get("lon")
        return (
            "Diagnostic colis (synthèse)\n\n"
            f"- `tracking_id`: `{tracking_id}`\n"
            f"- Statut métier: `{track_dict.get('status', 'UNKNOWN')}`\n"
            f"- Retard estimé: `{delay_min if delay_min is not None else 'n/a'} min`\n"
            f"- Phase IoT: `{phase or 'n/a'}`\n"
            f"- Congestion hub: `{hub_congestion or 'n/a'}`\n"
            f"- Véhicule: `{vehicle.get('vehicle_id', 'n/a')}` @ `{lat if lat is not None else 'n/a'}`, `{lon if lon is not None else 'n/a'}`"
        )

    async def _llm_finalize_summary_text(self, state: LaPosteState) -> Optional[str]:
        if not self.model:
            return None
        is_fr = hitl_language_for_agent(self) == "fr"
        extra_read_only = {
            k: v
            for k, v in (state.get("read_only_results") or {}).items()
            if k
            not in {
                "get_live_tracking_snapshot",
                "list_tracking_events",
                "get_pickup_points_nearby",
            }
        }
        payload = {
            "tracking_id": state.get("tracking_id"),
            "action": state.get("chosen_action") or "cancel",
            "reroute_result": state.get("reroute_result") or {},
            "reschedule_result": state.get("reschedule_result") or {},
            "notification_result": state.get("notification_result") or {},
            "business_track": state.get("business_track") or {},
            "iot_snapshot": state.get("iot_snapshot") or {},
            "pickup_points": (state.get("pickup_points") or [])[:3],
            "read_only_results": extra_read_only,
        }
        language = "French" if is_fr else "English"
        prompt = (
            "You are a parcel operations copilot.\n"
            f"Write a concise {language} post-action summary using ONLY the JSON payload.\n"
            "Mention the action performed (or no action), tracking_id, resulting status, and notification outcome.\n"
            "Use short bullets. Do not invent values; use 'n/a' when needed.\n"
            "If action is reroute, include pickup point id/name. If reschedule, include date/window.\n"
            f"Data:\n{self._json_str(payload)}"
        )
        try:
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(resp, "content", ""))
            if text:
                return text
        except Exception as exc:
            logger.warning(
                "[LaPosteDemoAgent] LLM finalize summary failed (%s: %s); using deterministic fallback",
                exc.__class__.__name__,
                exc,
            )
        return None

    def _fallback_finalize_summary_text(self, state: LaPosteState) -> str:
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
            return (
                "Action réalisée via agent métier (HITL de choix)\n\n"
                f"- Colis: `{tracking_id}`\n"
                f"- Action: reroutage vers point relais `{point_id}` ({point_name})\n"
                f"- Nouveau statut: `{reroute.get('status', 'n/a')}`\n"
                f"- Retard estimé (minutes): `{eta.get('delay_minutes', 'n/a')}`\n"
                f"- Notification client: `{notif.get('notification_id', 'non envoyée')}` (SMS)\n\n"
                f"`tracking_id`: `{tracking_id}`"
            )

        if action == "reschedule":
            res = state.get("reschedule_result") or {}
            delivery = res.get("delivery") or {}
            notif = state.get("notification_result") or {}
            return (
                "Action réalisée via agent métier (HITL de choix)\n\n"
                f"- Colis: `{tracking_id}`\n"
                "- Action: replanification de livraison à domicile\n"
                f"- Date: `{delivery.get('scheduled_date', state.get('chosen_reschedule_date', 'n/a'))}`\n"
                f"- Créneau: `{delivery.get('time_window', state.get('chosen_reschedule_window', 'n/a'))}`\n"
                f"- Nouveau statut: `{res.get('status', 'n/a')}`\n"
                f"- Notification client: `{notif.get('notification_id', 'non envoyée')}` (SMS)\n\n"
                f"`tracking_id`: `{tracking_id}`"
            )

        top_points = []
        for point in pickup_points[:3]:
            pp_id = point.get("pickup_point_id")
            if pp_id:
                top_points.append(str(pp_id))
        return (
            "Diagnostic disponible, aucune action exécutée.\n\n"
            f"- Colis: `{tracking_id}`\n"
            f"- Statut métier: `{business_track.get('status', 'n/a')}`\n"
            f"- Phase IoT: `{iot_snapshot.get('phase', 'n/a')}`\n"
            f"- Options relais observées: {', '.join(top_points) if top_points else 'n/a'}\n\n"
            f"`tracking_id`: `{tracking_id}`"
        )

    @staticmethod
    def _point_feature(
        *,
        lon: Any,
        lat: Any,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            lon_f = float(lon)
            lat_f = float(lat)
        except (TypeError, ValueError):
            return None

        props = {"name": name}
        if properties:
            props.update(properties)
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon_f, lat_f]},
            "properties": props,
        }

    def _build_tracking_geojson(
        self,
        state: LaPosteState,
        *,
        highlight_pickup_point_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        features: List[Dict[str, Any]] = []
        seen_point_ids: set[str] = set()
        pickup_points = state.get("pickup_points") or []
        pickup_point_ids: set[str] = set()
        if isinstance(pickup_points, list):
            for point in pickup_points:
                if not isinstance(point, dict):
                    continue
                pp_id = str(point.get("pickup_point_id") or "")
                if pp_id:
                    pickup_point_ids.add(pp_id)

        iot_snapshot = state.get("iot_snapshot") or {}
        map_overlay = (
            iot_snapshot.get("map_overlay") if isinstance(iot_snapshot, dict) else {}
        ) or {}

        route_polyline = map_overlay.get("route_polyline")
        if isinstance(route_polyline, list):
            coords: List[List[float]] = []
            for pt in route_polyline:
                if not isinstance(pt, dict):
                    continue
                pt_dict: Dict[str, Any] = {str(k): v for k, v in pt.items()}
                lat_raw = pt_dict.get("lat")
                lon_raw = pt_dict.get("lon")
                if lat_raw is None or lon_raw is None:
                    continue
                try:
                    lat = float(lat_raw)
                    lon = float(lon_raw)
                except (TypeError, ValueError):
                    continue
                coords.append([lon, lat])  # GeoJSON expects [lon, lat]
            if len(coords) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {
                            "name": "IoT route corridor",
                            "kind": "route",
                            "style": {
                                "color": "#1d4ed8",
                                "weight": 4,
                                "opacity": 0.8,
                            },
                        },
                    }
                )

        markers = map_overlay.get("markers")
        if isinstance(markers, list):
            for marker in markers:
                if not isinstance(marker, dict):
                    continue
                marker_id = str(marker.get("id") or "")
                if marker_id:
                    seen_point_ids.add(marker_id)

                kind = str(marker.get("kind") or "marker")
                if (
                    kind in {"pickup_locker", "pickup_point"}
                    and marker_id in pickup_point_ids
                ):
                    # Prefer the richer business pickup-point feature below (capacity, type, selection highlight).
                    continue
                style: Dict[str, Any] = {
                    "weight": 2,
                    "opacity": 1.0,
                    "fillOpacity": 0.9,
                }
                radius = 6
                if kind == "hub":
                    style.update({"color": "#c2410c", "fillColor": "#fb923c"})
                    radius = 8
                elif kind == "vehicle":
                    style.update({"color": "#1d4ed8", "fillColor": "#60a5fa"})
                    radius = 7
                elif kind in {"pickup_locker", "pickup_point"}:
                    style.update({"color": "#166534", "fillColor": "#4ade80"})
                    radius = 7

                feature = self._point_feature(
                    lon=marker.get("lon"),
                    lat=marker.get("lat"),
                    name=str(marker.get("label") or marker_id or "Marker"),
                    properties={
                        "id": marker_id or None,
                        "kind": kind,
                        "status": marker.get("status"),
                        "radius": radius,
                        "style": style,
                    },
                )
                if feature:
                    features.append(feature)

        # Add current business location if it is not already represented by IoT markers.
        business_track = state.get("business_track") or {}
        current_location = (
            business_track.get("current_location")
            if isinstance(business_track, dict)
            else None
        )
        if isinstance(current_location, dict):
            current_id = str(
                current_location.get("vehicle_id")
                or current_location.get("hub_id")
                or current_location.get("label")
                or ""
            )
            if current_id and current_id not in seen_point_ids:
                kind = str(current_location.get("kind") or "business_location")
                feature = self._point_feature(
                    lon=current_location.get("lon"),
                    lat=current_location.get("lat"),
                    name=str(current_location.get("label") or "Parcel location"),
                    properties={
                        "id": current_id,
                        "kind": kind,
                        "source": "business_track",
                        "radius": 7,
                        "style": {
                            "color": "#7c3aed",
                            "fillColor": "#c4b5fd",
                            "weight": 2,
                            "fillOpacity": 0.85,
                        },
                    },
                )
                if feature:
                    features.append(feature)

        if isinstance(pickup_points, list):
            for point in pickup_points[:5]:
                if not isinstance(point, dict):
                    continue
                pp_id = str(point.get("pickup_point_id") or "")
                is_selected = bool(pp_id) and pp_id == highlight_pickup_point_id
                if pp_id:
                    seen_point_ids.add(pp_id)

                base_color = "#166534"
                fill_color = "#86efac"
                if str(point.get("type")) == "locker":
                    base_color = "#0f766e"
                    fill_color = "#5eead4"
                if is_selected:
                    base_color = "#b45309"
                    fill_color = "#fbbf24"

                desc_bits = []
                if point.get("type"):
                    desc_bits.append(f"type={point.get('type')}")
                if point.get("available_slots") is not None:
                    desc_bits.append(f"slots={point.get('available_slots')}")
                if point.get("distance_hint_km") is not None:
                    desc_bits.append(f"distance={point.get('distance_hint_km')} km")

                feature = self._point_feature(
                    lon=point.get("lon"),
                    lat=point.get("lat"),
                    name=str(point.get("name") or pp_id or "Pickup point"),
                    properties={
                        "id": pp_id or None,
                        "kind": "pickup_point_candidate",
                        "pickup_point_id": pp_id or None,
                        "pickup_type": point.get("type"),
                        "description": ", ".join(desc_bits) if desc_bits else None,
                        "radius": 9 if is_selected else 7,
                        "style": {
                            "color": base_color,
                            "fillColor": fill_color,
                            "weight": 3 if is_selected else 2,
                            "fillOpacity": 0.9,
                        },
                    },
                )
                if feature:
                    features.append(feature)

        if not features:
            return None

        return {"type": "FeatureCollection", "features": features}

    def _build_text_and_map_message(
        self,
        text: str,
        state: LaPosteState,
        *,
        highlight_pickup_point_id: Optional[str] = None,
    ) -> AIMessage:
        geojson = self._build_tracking_geojson(
            state, highlight_pickup_point_id=highlight_pickup_point_id
        )
        if not geojson:
            return AIMessage(content=text)

        parts: List[MessagePart] = [
            TextPart(text=text),
            GeoPart(
                geojson=geojson,
                popup_property="name",
                fit_bounds=True,
            ),
        ]
        return AIMessage(content="", parts=parts)

    # -----------------------------
    # Nodes
    # -----------------------------
    async def route_request(self, state: LaPosteState) -> Dict[str, Any]:
        latest_user = self._latest_human_text(state.get("messages", []))
        previous_tracking_id = str(state.get("tracking_id") or "").strip()
        explicit_tracking_id = self._extract_tracking_id(latest_user)
        has_tracking_context = bool(previous_tracking_id)

        mode = "action_flow"
        source = "default"
        if self._looks_like_action_request(latest_user):
            mode = "action_flow"
            source = "heuristic"
        elif self._looks_like_identification_request(latest_user):
            mode = "followup_info"
            source = "heuristic"
        elif self._looks_like_info_followup(latest_user) and (
            has_tracking_context or bool(explicit_tracking_id)
        ):
            mode = "followup_info"
            source = "heuristic"
        elif has_tracking_context and latest_user.strip():
            llm_mode = await self._classify_request_mode_with_llm(
                latest_user=latest_user, has_tracking_context=True
            )
            if llm_mode in {"followup_info", "action_flow"}:
                mode = llm_mode
                source = "llm"

        resolved_tracking_id = explicit_tracking_id or previous_tracking_id
        update: Dict[str, Any] = {
            "request_mode": mode,
            "routing_mode_source": source,
            "latest_user_text": latest_user,
            "tracking_changed_hint": bool(
                explicit_tracking_id
                and previous_tracking_id
                and explicit_tracking_id != previous_tracking_id
            ),
        }
        if resolved_tracking_id:
            update["tracking_id"] = resolved_tracking_id
        return update

    async def prepare_incident(self, state: LaPosteState) -> Dict[str, Any]:
        tool_map = self._tool_map()
        msgs: List[BaseMessage] = []
        latest_user = state.get("latest_user_text") or self._latest_human_text(
            state.get("messages", [])
        )
        previous_tracking_id = str(state.get("tracking_id") or "").strip()
        tracking_id = self._extract_tracking_id(latest_user) or previous_tracking_id

        business_seed: Dict[str, Any] = {}
        iot_seed: Dict[str, Any] = {}
        tracking_changed = bool(state.get("tracking_changed_hint"))
        has_iot_context = isinstance(state.get("iot_snapshot"), dict) and bool(
            state.get("iot_snapshot")
        )

        if not tracking_id:
            seed_tool_name = (
                "seed_demo_parcel_exception_for_current_user"
                if "seed_demo_parcel_exception_for_current_user" in tool_map
                else "seed_demo_parcel_exception"
            )
            business_seed_raw, m = await self._call_tool(
                seed_tool_name, {}, tool_map=tool_map
            )
            msgs.extend(m)
            if (
                not isinstance(business_seed_raw, dict)
                or business_seed_raw.get("ok") is False
            ):
                raise RuntimeError(f"{seed_tool_name} failed: {business_seed_raw}")
            business_seed = business_seed_raw
            tracking_id = str(business_seed.get("tracking_id") or "")

        if not tracking_id:
            raise RuntimeError("No tracking_id available after seeding/parsing")

        should_seed_iot = (
            bool(business_seed)
            or tracking_changed
            or not previous_tracking_id
            or not has_iot_context
        )
        if should_seed_iot:
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

        track_dict = business_track if isinstance(business_track, dict) else {}
        delivery_addr = (
            self._safe_get(track_dict, "delivery", "address", default={}) or {}
        )
        city = delivery_addr.get("city") or "Paris"
        postal_code = delivery_addr.get("postal_code") or "75015"

        read_only_results: Dict[str, Any] = {}
        executed_read_only_plan: List[Dict[str, Any]] = []
        planned_calls = await self._llm_plan_read_only_calls(
            state=state,
            tracking_id=str(tracking_id),
            city=str(city),
            postal_code=str(postal_code),
        )
        if planned_calls:
            (
                plan_results,
                plan_msgs,
                executed_read_only_plan,
            ) = await self._execute_read_only_plan(
                state=state,
                tracking_id=str(tracking_id),
                city=str(city),
                postal_code=str(postal_code),
                calls=planned_calls,
                tool_map=tool_map,
            )
            read_only_results.update(plan_results)
            msgs.extend(plan_msgs)

        # Ensure baseline data required by the current map/HITL UX even if planner omitted it.
        if "get_live_tracking_snapshot" not in read_only_results:
            iot_snapshot_base, m = await self._call_tool(
                "get_live_tracking_snapshot",
                {"tracking_id": tracking_id},
                tool_map=tool_map,
            )
            msgs.extend(m)
            read_only_results["get_live_tracking_snapshot"] = iot_snapshot_base
            executed_read_only_plan.append(
                {
                    "tool": "get_live_tracking_snapshot",
                    "status": "ok"
                    if not (
                        isinstance(iot_snapshot_base, dict)
                        and iot_snapshot_base.get("ok") is False
                    )
                    else "error",
                    "source": "fallback_baseline",
                }
            )

        if "list_tracking_events" not in read_only_results:
            iot_events_base, m = await self._call_tool(
                "list_tracking_events",
                {"tracking_id": tracking_id, "since_seq": 0, "limit": 5},
                tool_map=tool_map,
            )
            msgs.extend(m)
            read_only_results["list_tracking_events"] = iot_events_base
            executed_read_only_plan.append(
                {
                    "tool": "list_tracking_events",
                    "status": "ok"
                    if not (
                        isinstance(iot_events_base, dict)
                        and iot_events_base.get("ok") is False
                    )
                    else "error",
                    "source": "fallback_baseline",
                }
            )

        if "get_pickup_points_nearby" not in read_only_results:
            pickup_base, m = await self._call_tool(
                "get_pickup_points_nearby",
                {"city": city, "postal_code": postal_code, "limit": 3},
                tool_map=tool_map,
            )
            msgs.extend(m)
            read_only_results["get_pickup_points_nearby"] = pickup_base
            executed_read_only_plan.append(
                {
                    "tool": "get_pickup_points_nearby",
                    "status": "ok"
                    if not (
                        isinstance(pickup_base, dict) and pickup_base.get("ok") is False
                    )
                    else "error",
                    "source": "fallback_baseline",
                }
            )

        iot_snapshot = read_only_results.get("get_live_tracking_snapshot")
        iot_events_raw = read_only_results.get("list_tracking_events")
        pickup_resp = read_only_results.get("get_pickup_points_nearby")

        pickup_points = self._pickup_points_from_response(pickup_resp)
        (
            pickup_points,
            locker_msgs,
        ) = await self._enrich_pickup_points_with_locker_telemetry(
            pickup_points,
            tool_map=tool_map,
        )
        msgs.extend(locker_msgs)

        iot_events = []
        if isinstance(iot_events_raw, dict) and isinstance(
            iot_events_raw.get("events"), list
        ):
            iot_events = [e for e in iot_events_raw["events"] if isinstance(e, dict)]

        request_mode = (state.get("request_mode") or "action_flow").strip().lower()

        diag_messages: List[BaseMessage] = []
        if request_mode != "followup_info":
            geo_state = cast(LaPosteState, dict(state))
            geo_state.update(
                {
                    "tracking_id": tracking_id,
                    "business_track": track_dict,
                    "iot_snapshot": iot_snapshot
                    if isinstance(iot_snapshot, dict)
                    else {},
                    "iot_events": iot_events,
                    "pickup_points": pickup_points,
                    "read_only_results": read_only_results,
                }
            )
            summary_text = await self._llm_diagnosis_summary_text(
                geo_state
            ) or self._fallback_diagnosis_summary_text(geo_state)
            is_fr = hitl_language_for_agent(self) == "fr"
            transition = (
                "Je vais maintenant te proposer une carte de décision (choix relais ou replanification) pour lancer l'action."
                if is_fr
                else "I will now present a decision card (pickup-point reroute or home reschedule) before executing any action."
            )
            summary_text = f"{summary_text}\n\n{transition}"

            diag_message: BaseMessage = self._build_text_and_map_message(
                summary_text, geo_state
            )
            diag_messages = [diag_message]

        return {
            "messages": [*msgs, *diag_messages],
            "business_track": track_dict,
            "iot_snapshot": iot_snapshot if isinstance(iot_snapshot, dict) else {},
            "iot_events": iot_events,
            "pickup_points": pickup_points,
            "read_only_plan": executed_read_only_plan,
            "read_only_results": read_only_results,
        }

    async def respond_followup(self, state: LaPosteState) -> Dict[str, Any]:
        text = await self._llm_followup_summary_text(state)
        if not text:
            text = self._fallback_followup_summary_text(state)
        return {
            "messages": [self._build_text_and_map_message(text, state)],
            "final_text": text,
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
        action = state.get("chosen_action") or "cancel"
        text = await self._llm_finalize_summary_text(state)
        if not text:
            text = self._fallback_finalize_summary_text(state)

        if action == "reroute":
            reroute = state.get("reroute_result") or {}
            delivery = reroute.get("delivery") or {}
            point_id = (
                delivery.get("pickup_point_id")
                or state.get("chosen_pickup_point_id")
                or "n/a"
            )
            return {
                "messages": [
                    self._build_text_and_map_message(
                        text,
                        state,
                        highlight_pickup_point_id=str(point_id),
                    )
                ],
                "final_text": text,
            }

        if action == "reschedule":
            return {
                "messages": [self._build_text_and_map_message(text, state)],
                "final_text": text,
            }

        return {
            "messages": [self._build_text_and_map_message(text, state)],
            "final_text": text,
        }
