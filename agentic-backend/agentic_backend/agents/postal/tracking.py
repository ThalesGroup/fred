from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from datetime import date, timedelta
from typing import Annotated, Any, Dict, List, Optional, Sequence, Type, TypedDict, cast

from fred_core.common import coerce_bool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.chatbot.chat_schema import GeoPart, MessagePart, TextPart
from agentic_backend.core.interrupts.hitl_i18n import hitl_language_for_agent
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


class LaPosteState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    request_mode: str  # action_flow | followup_info | capabilities_info
    routing_mode_source: str

    # Router outputs
    intent_topic: str
    intent_needs_map: bool
    intent_need_iot_snapshot: bool
    intent_need_iot_events: bool
    intent_need_route_geometry: bool
    intent_need_pickup_points: bool
    intent_need_compensation_estimate: bool
    intent_explicit_action: bool
    intent_requires_parcel_context: bool
    intent_confidence: float
    intent_reason: str

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


def _build_parcel_ops_tuning() -> AgentTuning:
    return AgentTuning(
        role="La Poste Operations Copilot",
        description=(
            "Agent custom démonstratif pour incidents colis (retard, reroutage, "
            "replanification) avec routage d'intention LLM structuré et orchestration MCP déterministe."
        ),
        tags=["laposte", "postal", "iot", "hitl", "demo", "deterministic"],
        mcp_servers=[
            MCPServerRef(id="mcp-postal-business-demo"),
            MCPServerRef(id="mcp-iot-tracking-demo"),
        ],
        fields=[
            FieldSpec(
                key="i18n.default_language",
                type="select",
                title="Default language",
                description="Language used when runtime/UI context does not provide one.",
                required=False,
                default="fr",
                enum=["fr", "en"],
                ui=UIHints(group="I18n"),
            ),
            FieldSpec(
                key="prompts.intent_router",
                type="prompt",
                title="Intent Router Prompt",
                description=(
                    "Prompt du routeur d'intention LLM. Doit retourner uniquement du JSON "
                    "pour décider la branche du graphe (capabilities / info / action) et "
                    "les besoins de données."
                ),
                required=True,
                default=(
                    "Tu es un routeur d'intention pour un agent operations colis (La Poste demo).\n"
                    "Tu NE fais aucune réponse utilisateur. Tu décides uniquement la route du graphe et les besoins de données.\n"
                    "Retourne du JSON UNIQUEMENT, sans markdown, sans texte autour.\n"
                    "\n"
                    "Schema JSON exact (top-level):\n"
                    "{\n"
                    '  "route": "capabilities|followup_info|action_flow",\n'
                    '  "topic": "capabilities|tracking_status|location|iot_state|events|pickup_options|compensation|claim|general_info|other",\n'
                    '  "explicit_action": true,\n'
                    '  "requires_parcel_context": false,\n'
                    '  "needs_map": false,\n'
                    '  "need_iot_snapshot": false,\n'
                    '  "need_iot_events": false,\n'
                    '  "need_route_geometry": false,\n'
                    '  "need_pickup_points": false,\n'
                    '  "need_compensation_estimate": false,\n'
                    '  "confidence": 0.0,\n'
                    '  "reason": "short explanation"\n'
                    "}\n"
                    "\n"
                    "Règles métier importantes:\n"
                    "- `capabilities` si la question demande tes outils, tes capacités, ce que tu peux faire.\n"
                    "- `followup_info` pour statut, suivi, résumé, localisation, état IoT, explication.\n"
                    "- `action_flow` seulement si l'utilisateur exprime clairement une action à exécuter (rerouter, replanifier, notifier, ouvrir réclamation, etc.).\n"
                    "- Si la demande est ambiguë, préfère `followup_info`.\n"
                    "- `needs_map=true` uniquement si l'utilisateur demande explicitement une carte, la localisation, la route/trajet, ou la position.\n"
                    "- `requires_parcel_context=false` pour les questions méta (outils/capacités). Sinon généralement true.\n"
                    "- `confidence` entre 0 et 1.\n"
                    "\n"
                    "Contexte session:\n"
                    "- tracking_id actif présent: {has_tracking_context}\n"
                    "- tracking_id explicite détecté dans le message: {has_explicit_tracking_id}\n"
                    "Message utilisateur: {latest_user}\n"
                ),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.followup_summary",
                type="prompt",
                title="Follow-up Summary Prompt",
                description="Prompt used to answer informational follow-up questions from current parcel state.",
                required=True,
                default=(
                    "Tu es un copilote operations colis.\n"
                    "Reponds en {response_language} en utilisant UNIQUEMENT les donnees JSON fournies.\n"
                    "Sois concis. Utilise des puces courtes. Mentionne explicitement le tracking_id. Si une information manque, ecris 'n/a'.\n"
                    "Ne propose pas d'action si l'utilisateur n'en demande pas.\n"
                    "Question de suivi: {latest_user}\n\n"
                    "Donnees:\n{data_json}"
                ),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.diagnosis_summary",
                type="prompt",
                title="Diagnosis Summary Prompt",
                description="Prompt used to synthesize pre-action diagnostics before HITL choice.",
                required=True,
                default=(
                    "Tu es un copilote operations colis.\n"
                    "Redige une synthese de diagnostic concise en {response_language} en utilisant UNIQUEMENT le JSON fourni.\n"
                    "Utilise des puces courtes. Mentionne explicitement le tracking_id.\n"
                    "Inclure: statut metier, estimation de retard si disponible, phase IoT, congestion du hub, position du vehicule si disponible.\n"
                    "{mode_hint}\n"
                    "N'invente aucun champ. Si une valeur manque, ecris 'n/a'.\n"
                    "Donnees:\n{data_json}"
                ),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.finalize_summary",
                type="prompt",
                title="Post-action Summary Prompt",
                description="Prompt used after reroute/reschedule/cancel to summarize the outcome.",
                required=True,
                default=(
                    "Tu es un copilote operations colis.\n"
                    "Redige une synthese post-action concise en {response_language} en utilisant UNIQUEMENT le JSON fourni.\n"
                    "Mentionne l'action realisee (ou aucune action), le tracking_id, le statut resultant et le resultat de notification.\n"
                    "Utilise des puces courtes. N'invente pas de valeurs; utilise 'n/a' si besoin.\n"
                    "Si l'action est un reroutage, inclus l'id/nom du point relais. Si c'est une replanification, inclus date et creneau.\n"
                    "Donnees:\n{data_json}"
                ),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.hitl_resolution_title_fr",
                type="string",
                title="HITL Title (FR)",
                description="Titre de la carte HITL de resolution (français).",
                required=False,
                default="Choisir une action de résolution",
                ui=UIHints(group="Prompts"),
            ),
            FieldSpec(
                key="prompts.hitl_resolution_question_fr",
                type="prompt",
                title="HITL Question (FR)",
                description="Question affichee dans la carte HITL de resolution (français). Utiliser {tracking_id}.",
                required=False,
                default=(
                    "Le colis `{tracking_id}` est en retard. Quelle action veux-tu que j'exécute ? "
                    "Choisis un point relais ou une replanification à domicile."
                ),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.hitl_resolution_title_en",
                type="string",
                title="HITL Title (EN)",
                description="Title of the HITL resolution card (English).",
                required=False,
                default="Choose a resolution action",
                ui=UIHints(group="Prompts"),
            ),
            FieldSpec(
                key="prompts.hitl_resolution_question_en",
                type="prompt",
                title="HITL Question (EN)",
                description="Question shown in the HITL resolution card (English). Use {tracking_id}.",
                required=False,
                default=(
                    "Parcel `{tracking_id}` is delayed. Which action should I execute? "
                    "Choose a pickup point or a home delivery reschedule."
                ),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="behavior.require_explicit_action_for_hitl",
                type="boolean",
                title="Require Explicit Action For HITL",
                description=(
                    "Si activé, une intention `action_flow` proposée par le routeur LLM est "
                    "déclassée en `followup_info` tant qu'aucune action explicite n'est détectée."
                ),
                required=False,
                default=True,
                ui=UIHints(group="Behavior"),
            ),
            FieldSpec(
                key="behavior.followup_map_only_when_requested",
                type="boolean",
                title="Follow-up Map Only When Requested",
                description=(
                    "Si activé, les réponses informatives n'affichent une GeoMap que si le routeur "
                    "LLM a explicitement demandé une carte."
                ),
                required=False,
                default=True,
                ui=UIHints(group="Behavior"),
            ),
        ],
    )


PARCEL_OPS_TUNING = _build_parcel_ops_tuning()


@expose_runtime_source("agent.ParcelOpsAgent")
class TrackingAgent(AgentFlow):
    tuning = PARCEL_OPS_TUNING

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

    def _default_language(self) -> str:
        raw = str(self.get_tuned_any("i18n.default_language") or "fr").strip().lower()
        return "en" if raw.startswith("en") else "fr"

    def _hitl_lang(self) -> str:
        return hitl_language_for_agent(self, default=self._default_language())

    def _is_french(self) -> bool:
        return self._hitl_lang() == "fr"

    def _response_language_label(self) -> str:
        return "français" if self._is_french() else "English"

    def _render_tuned_prompt(self, key: str, **tokens: Any) -> str:
        template = self.get_tuned_text(key)
        if not template:
            raise RuntimeError(f"Missing tuned prompt template: {key}")
        return self.render(template, **tokens)

    def build_runtime_structure(self) -> None:
        self._graph = self._build_graph()

    async def activate_runtime(self) -> None:
        self.model = get_default_chat_model()
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

    async def aclose(self):
        if self.mcp:
            await self.mcp.aclose()

    def get_graph_mermaid_preview(self) -> str:
        """
        UI-friendly structural graph (not runtime LangGraph internals).
        Kept explicit on purpose so the displayed graph matches business flow semantics.
        """
        return self.build_mermaid_preview(
            nodes=[
                {"id": "start", "label": "Start", "shape": "round"},
                {"id": "route_request", "label": "Route request", "shape": "diamond"},
                {"id": "respond_capabilities", "label": "Respond capabilities"},
                {"id": "prepare_incident", "label": "Prepare incident"},
                {
                    "id": "collect_context",
                    "label": "Collect context",
                    "shape": "diamond",
                },
                {"id": "respond_followup", "label": "Respond follow-up"},
                {"id": "choose_resolution", "label": "HITL choice", "shape": "diamond"},
                {"id": "apply_reroute", "label": "Apply reroute"},
                {"id": "apply_reschedule", "label": "Apply reschedule"},
                {"id": "cancel_flow", "label": "Cancel flow"},
                {"id": "finalize", "label": "Finalize response"},
                {"id": "end", "label": "End", "shape": "round"},
            ],
            edges=[
                {"source": "start", "target": "route_request"},
                {
                    "source": "route_request",
                    "target": "respond_capabilities",
                    "label": "capabilities",
                },
                {
                    "source": "route_request",
                    "target": "prepare_incident",
                    "label": "incident",
                },
                {"source": "respond_capabilities", "target": "end"},
                {"source": "prepare_incident", "target": "collect_context"},
                {
                    "source": "collect_context",
                    "target": "respond_followup",
                    "label": "followup",
                },
                {
                    "source": "collect_context",
                    "target": "choose_resolution",
                    "label": "resolution",
                },
                {"source": "respond_followup", "target": "end"},
                {
                    "source": "choose_resolution",
                    "target": "apply_reroute",
                    "label": "reroute",
                },
                {
                    "source": "choose_resolution",
                    "target": "apply_reschedule",
                    "label": "reschedule",
                },
                {
                    "source": "choose_resolution",
                    "target": "cancel_flow",
                    "label": "cancel",
                },
                {"source": "apply_reroute", "target": "finalize"},
                {"source": "apply_reschedule", "target": "finalize"},
                {"source": "cancel_flow", "target": "finalize"},
                {"source": "finalize", "target": "end"},
            ],
        )

    # -----------------------------
    # Graph (deterministic custom graph)
    # -----------------------------
    def _build_graph(self) -> StateGraph:
        g = StateGraph(LaPosteState)
        g.add_node("route_request", self.route_request)
        g.add_node("respond_capabilities", self.respond_capabilities)
        g.add_node("prepare_incident", self.prepare_incident)
        g.add_node("collect_context", self.collect_context)
        g.add_node("respond_followup", self.respond_followup)
        g.add_node("choose_resolution", self.choose_resolution_hitl)
        g.add_node("apply_reroute", self.apply_reroute)
        g.add_node("apply_reschedule", self.apply_reschedule)
        g.add_node("cancel_flow", self.cancel_flow)
        g.add_node("finalize", self.finalize_response)

        g.set_entry_point("route_request")
        g.add_conditional_edges(
            "route_request",
            self._route_after_request,
            {
                "capabilities": "respond_capabilities",
                "incident": "prepare_incident",
            },
        )
        g.add_edge("respond_capabilities", END)
        g.add_edge("prepare_incident", "collect_context")
        g.add_conditional_edges(
            "collect_context",
            self._route_after_collected_context,
            {
                "followup": "respond_followup",
                "resolution": "choose_resolution",
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
    # MCP / shared helpers
    # -----------------------------
    def _tool_map(self) -> Dict[str, BaseTool]:
        if not self.mcp:
            return {}
        tool_map: Dict[str, BaseTool] = {}
        for tool in self.mcp.get_tools():
            if tool.name in tool_map:
                logger.warning(
                    "[ParcelOpsAgent] Duplicate tool name '%s' detected; last one wins",
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

    async def _ainvoke_internal_non_stream(self, prompt: str) -> Optional[str]:
        if not self.model:
            return None
        invoke_model: Any = self.model
        bind = getattr(self.model, "bind", None)
        if callable(bind):
            try:
                invoke_model = bind(stream=False)
            except Exception:
                logger.debug(
                    "[ParcelOpsAgent] model.bind(stream=False) not available; using default model invocation"
                )
        resp = await invoke_model.ainvoke([HumanMessage(content=prompt)])
        text = self._message_content_to_text(getattr(resp, "content", ""))
        return text or None

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
            raise RuntimeError(f"Tool '{tool_name}' not found for ParcelOpsAgent")

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
                "[ParcelOpsAgent] Tool call failed tool=%s args=%s", tool_name, args
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

    def _route_after_request(self, state: LaPosteState) -> str:
        mode = (state.get("request_mode") or "").strip().lower()
        if mode == "capabilities_info":
            return "capabilities"
        return "incident"

    def _route_after_collected_context(self, state: LaPosteState) -> str:
        mode = (state.get("request_mode") or "").strip().lower()
        if mode == "followup_info":
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
    def _looks_like_action_request(cls, text: str) -> bool:
        t = cls._normalize_intent_text(text)
        if not t:
            return False
        action_keywords = (
            "reroute",
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
        )
        return any(k in t for k in action_keywords)

    @classmethod
    def _looks_like_capabilities_question(cls, text: str) -> bool:
        t = cls._normalize_intent_text(text)
        if not t:
            return False
        patterns = (
            "quels sont les outils",
            "quels outils",
            "tes outils",
            "liste des outils",
            "outils a ta disposition",
            "outils à ta disposition",
            "que peux tu faire",
            "que peux-tu faire",
            "quelles actions peux tu faire",
            "quelles actions peux-tu faire",
            "quelles sont tes capacites",
            "what tools",
            "which tools",
            "tools do you have",
            "what can you do",
            "capabilities",
        )
        if any(cls._normalize_intent_text(p) in t for p in patterns):
            return True
        if "outil" in t and any(
            m in t
            for m in (
                "quels",
                "quel",
                "tes",
                "ta disposition",
                "disposition",
                "liste",
                "peux tu",
                "peux",
            )
        ):
            return True
        if (" tool " in f" {t} " or "tools" in t) and any(
            m in t
            for m in ("what", "which", "available", "do you have", "can you do", "your")
        ):
            return True
        return False

    @classmethod
    def _looks_like_affirmation(cls, text: str) -> bool:
        t = cls._normalize_intent_text(text)
        if not t:
            return False
        if t in {
            "oui",
            "oui stp",
            "oui s il te plait",
            "oui s il vous plait",
            "oui merci",
            "ok",
            "okay",
            "yes",
            "yes please",
            "go ahead",
            "vas y",
            "allez y",
        }:
            return True
        short_yes = any(token in t.split() for token in ("oui", "yes", "ok", "okay"))
        polite = any(
            phrase in t
            for phrase in ("s il te plait", "s il vous plait", "please", "stp", "svp")
        )
        return short_yes and polite

    @classmethod
    def _looks_like_tool_grouping_request(cls, text: str) -> bool:
        t = cls._normalize_intent_text(text)
        if not t:
            return False
        grouping = any(
            kw in t
            for kw in (
                "regroupe",
                "regrouper",
                "grouper",
                "group by",
                "groupes",
                "par cas d usage",
                "par usage",
                "par categorie",
                "par categorie",
            )
        )
        toolish = any(
            kw in t
            for kw in ("outil", "outils", "tools", "cas d usage", "usage", "categorie")
        )
        return grouping and toolish

    @classmethod
    def _looks_like_map_request(cls, text: str) -> bool:
        t = cls._normalize_intent_text(text)
        if not t:
            return False
        keywords = (
            "carte",
            "map",
            "localisation",
            "position",
            "ou est",
            "where is",
            "trajet",
            "route",
            "itineraire",
            "vehicule",
            "hub",
        )
        return any(k in t for k in keywords)

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
                "[ParcelOpsAgent] Router output not pure JSON, attempting extraction"
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
            return {
                "tracking_id": tracking_id,
                "since_seq": max(0, since_seq_i),
                "limit": max(1, min(limit_i, 10)),
            }
        if tool_name == "get_pickup_points_nearby":
            try:
                limit_i = int(proposed_args.get("limit", 3))
            except (TypeError, ValueError):
                limit_i = 3
            return {
                "city": city,
                "postal_code": postal_code,
                "limit": max(1, min(limit_i, 5)),
            }
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

        for call in calls[:8]:
            tool_name = str(call.get("tool") or "").strip()
            raw_args = call.get("args")
            proposed_args: Dict[str, Any] = (
                {str(k): v for k, v in raw_args.items()}
                if isinstance(raw_args, dict)
                else {}
            )
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

    # -----------------------------
    # Summary helpers (LLM + fallback)
    # -----------------------------
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
        prompt = self._render_tuned_prompt(
            "prompts.followup_summary",
            response_language=self._response_language_label(),
            latest_user=latest_user,
            data_json=self._json_str(payload),
        )
        try:
            text = await self._ainvoke_internal_non_stream(prompt)
            if text:
                return text
        except Exception as exc:
            logger.warning(
                "[ParcelOpsAgent] LLM follow-up summary failed (%s: %s); using deterministic fallback",
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
        mode_hint = (
            "Diagnostic avant carte HITL de choix (avant proposition d'action)."
            if request_mode != "followup_info"
            else "Rafraîchissement de diagnostic informatif (aucune proposition d'action)."
        )
        prompt = self._render_tuned_prompt(
            "prompts.diagnosis_summary",
            response_language=self._response_language_label(),
            mode_hint=mode_hint,
            data_json=self._json_str(payload),
        )
        try:
            text = await self._ainvoke_internal_non_stream(prompt)
            if text:
                return text
        except Exception as exc:
            logger.warning(
                "[ParcelOpsAgent] LLM diagnosis summary failed (%s: %s); using deterministic fallback",
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
        prompt = self._render_tuned_prompt(
            "prompts.finalize_summary",
            response_language=self._response_language_label(),
            data_json=self._json_str(payload),
        )
        try:
            text = await self._ainvoke_internal_non_stream(prompt)
            if text:
                return text
        except Exception as exc:
            logger.warning(
                "[ParcelOpsAgent] LLM finalize summary failed (%s: %s); using deterministic fallback",
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

    # -----------------------------
    # Geo rendering helpers
    # -----------------------------
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
                lat_raw = pt.get("lat")
                lon_raw = pt.get("lon")
                if lat_raw is None or lon_raw is None:
                    continue
                try:
                    lat_f = float(lat_raw)
                    lon_f = float(lon_raw)
                except (TypeError, ValueError):
                    continue
                coords.append([lon_f, lat_f])
            if len(coords) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {
                            "name": "IoT route corridor",
                            "kind": "route",
                            "style": {"color": "#1d4ed8", "weight": 4, "opacity": 0.8},
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
            GeoPart(geojson=geojson, popup_property="name", fit_bounds=True),
        ]
        return AIMessage(content="", parts=parts)

    # -----------------------------
    # Intent router (LLM + guardrails)
    # -----------------------------
    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        return coerce_bool(value, default=default)

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _tuned_bool(self, key: str, default: bool) -> bool:
        raw = self.get_tuned_any(key)
        if raw is None:
            return default
        return self._coerce_bool(raw, default=default)

    def _intent_router_prompt(
        self,
        *,
        latest_user: str,
        has_tracking_context: bool,
        has_explicit_tracking_id: bool,
    ) -> str:
        template = self.get_tuned_text("prompts.intent_router")
        if template:
            out = template
            out = out.replace("{latest_user}", latest_user)
            out = out.replace(
                "{has_tracking_context}", "yes" if has_tracking_context else "no"
            )
            out = out.replace(
                "{has_explicit_tracking_id}",
                "yes" if has_explicit_tracking_id else "no",
            )
            return out
        return (
            "Classify the message for a parcel-operations graph. "
            "Return JSON only with keys route/topic/explicit_action/requires_parcel_context/needs_map.\n"
            f"has_tracking_context={'yes' if has_tracking_context else 'no'} "
            f"has_explicit_tracking_id={'yes' if has_explicit_tracking_id else 'no'}\n"
            f"message={latest_user}"
        )

    def _fallback_intent_router(
        self,
        *,
        latest_user: str,
        has_tracking_context: bool,
        has_explicit_tracking_id: bool,
    ) -> Dict[str, Any]:
        t = self._normalize_intent_text(latest_user)
        if self._looks_like_capabilities_question(latest_user):
            return {
                "route": "capabilities",
                "topic": "capabilities",
                "explicit_action": False,
                "requires_parcel_context": False,
                "needs_map": False,
                "need_iot_snapshot": False,
                "need_iot_events": False,
                "need_route_geometry": False,
                "need_pickup_points": False,
                "need_compensation_estimate": False,
                "confidence": 0.55,
                "reason": "fallback: meta capabilities question",
                "_source": "fallback",
            }

        explicit_action = self._looks_like_action_request(latest_user)
        wants_map = self._looks_like_map_request(latest_user)
        mentions_iot = "iot" in t or "congestion" in t or "hub" in t
        mentions_events = "event" in t or "alerte" in t or "alert" in t
        mentions_pickup = (
            "relais" in t
            or "point relais" in t
            or "point de retrait" in t
            or "points de retrait" in t
            or "pickup" in t
            or "locker" in t
        )
        wants_visualization = any(
            kw in t for kw in ("visualiser", "visualise", "afficher", "montre", "voir")
        )
        if mentions_pickup and wants_visualization:
            wants_map = True
        mentions_comp = (
            "compensation" in t or "indemn" in t or "claim" in t or "reclamation" in t
        )

        return {
            "route": "action_flow" if explicit_action else "followup_info",
            "topic": (
                "compensation"
                if mentions_comp
                else "pickup_options"
                if mentions_pickup
                else "events"
                if mentions_events
                else "location"
                if wants_map
                else "iot_state"
                if mentions_iot
                else "tracking_status"
            ),
            "explicit_action": explicit_action,
            "requires_parcel_context": True,
            "needs_map": wants_map,
            "need_iot_snapshot": wants_map or mentions_iot,
            "need_iot_events": mentions_events,
            "need_route_geometry": wants_map,
            "need_pickup_points": mentions_pickup,
            "need_compensation_estimate": mentions_comp,
            "confidence": 0.4,
            "reason": "fallback heuristic routing",
            "_source": "fallback",
        }

    async def _route_intent_with_llm(
        self,
        *,
        latest_user: str,
        has_tracking_context: bool,
        has_explicit_tracking_id: bool,
    ) -> Dict[str, Any]:
        if not self.model or not latest_user.strip():
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
            # Intent routing is an internal control step (JSON-only contract) and should
            # not surface token-by-token partial text in the user stream.
            # Prefer a non-streaming invocation when the model supports binding kwargs.
            invoke_model: Any = self.model
            bind = getattr(self.model, "bind", None)
            if callable(bind):
                try:
                    invoke_model = bind(stream=False)
                except Exception:
                    logger.debug(
                        "[ParcelOpsAgent] model.bind(stream=False) not available for intent router; using default model invocation"
                    )

            resp = await invoke_model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(resp, "content", ""))
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
                route = "followup_info"

            topic = str(parsed.get("topic") or "other").strip().lower() or "other"
            decision = {
                "route": route,
                "topic": topic,
                "explicit_action": self._coerce_bool(
                    parsed.get("explicit_action"), default=(route == "action_flow")
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
                "need_route_geometry": self._coerce_bool(
                    parsed.get("need_route_geometry"), default=False
                ),
                "need_pickup_points": self._coerce_bool(
                    parsed.get("need_pickup_points"), default=False
                ),
                "need_compensation_estimate": self._coerce_bool(
                    parsed.get("need_compensation_estimate"), default=False
                ),
                "confidence": max(
                    0.0, min(1.0, self._coerce_float(parsed.get("confidence"), 0.0))
                ),
                "reason": str(parsed.get("reason") or "").strip(),
                "_source": "llm_router",
            }

            if decision["route"] == "capabilities":
                decision.update(
                    {
                        "topic": "capabilities",
                        "explicit_action": False,
                        "requires_parcel_context": False,
                        "needs_map": False,
                        "need_iot_snapshot": False,
                        "need_iot_events": False,
                        "need_route_geometry": False,
                        "need_pickup_points": False,
                        "need_compensation_estimate": False,
                    }
                )
            if decision["needs_map"]:
                decision["need_route_geometry"] = True
                decision["need_iot_snapshot"] = True
            return decision
        except Exception as exc:
            logger.warning(
                "[ParcelOpsAgent] intent router LLM failed (%s: %s); using fallback",
                exc.__class__.__name__,
                exc,
            )
            return self._fallback_intent_router(
                latest_user=latest_user,
                has_tracking_context=has_tracking_context,
                has_explicit_tracking_id=has_explicit_tracking_id,
            )

    # -----------------------------
    # Deterministic data collection policy
    # -----------------------------
    def _build_info_read_only_calls(self, state: LaPosteState) -> List[Dict[str, Any]]:
        topic = str(state.get("intent_topic") or "other").strip().lower()
        calls: List[Dict[str, Any]] = []

        def add(tool: str, args: Optional[Dict[str, Any]] = None) -> None:
            if any(c.get("tool") == tool for c in calls):
                return
            calls.append({"tool": tool, "args": args or {}})

        if self._coerce_bool(state.get("intent_need_iot_snapshot"), False):
            add("get_live_tracking_snapshot")
        if self._coerce_bool(state.get("intent_need_iot_events"), False):
            add("list_tracking_events", {"limit": 5, "since_seq": 0})
        if self._coerce_bool(state.get("intent_need_route_geometry"), False):
            add("get_route_geometry")
        if self._coerce_bool(state.get("intent_need_pickup_points"), False):
            add("get_pickup_points_nearby", {"limit": 3})
        if self._coerce_bool(state.get("intent_need_compensation_estimate"), False):
            add("estimate_compensation")

        if topic in {"location"}:
            add("get_live_tracking_snapshot")
            if self._coerce_bool(state.get("intent_needs_map"), False):
                add("get_route_geometry")
        elif topic in {"iot_state"}:
            add("get_live_tracking_snapshot")
        elif topic in {"events"}:
            add("get_live_tracking_snapshot")
            add("list_tracking_events", {"limit": 5, "since_seq": 0})
        elif topic in {"pickup_options"}:
            add("get_pickup_points_nearby", {"limit": 3})
        elif topic in {"compensation", "claim"}:
            add("estimate_compensation")

        return calls[:6]

    def _ensure_action_baseline_calls(
        self, calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        out = list(calls)

        def add(tool: str, args: Optional[Dict[str, Any]] = None) -> None:
            if any(c.get("tool") == tool for c in out):
                return
            out.append({"tool": tool, "args": args or {}})

        add("get_live_tracking_snapshot")
        add("list_tracking_events", {"limit": 5, "since_seq": 0})
        add("get_pickup_points_nearby", {"limit": 3})
        add("get_route_geometry")
        return out[:8]

    async def _collect_compact_context(
        self, state: LaPosteState, *, action_mode: bool
    ) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id")
        if not tracking_id:
            raise RuntimeError("Missing tracking_id in collect_context")

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
        city = str(delivery_addr.get("city") or "Paris")
        postal_code = str(delivery_addr.get("postal_code") or "75015")

        planned_calls = self._build_info_read_only_calls(state)
        if action_mode:
            planned_calls = self._ensure_action_baseline_calls(planned_calls)

        read_only_results: Dict[str, Any] = {}
        executed_read_only_plan: List[Dict[str, Any]] = []
        if planned_calls:
            (
                read_only_results,
                plan_msgs,
                executed_read_only_plan,
            ) = await self._execute_read_only_plan(
                state=state,
                tracking_id=str(tracking_id),
                city=city,
                postal_code=postal_code,
                calls=planned_calls,
                tool_map=tool_map,
            )
            msgs.extend(plan_msgs)

        iot_snapshot = read_only_results.get("get_live_tracking_snapshot")
        if not isinstance(iot_snapshot, dict):
            iot_snapshot = {}

        iot_events: List[Dict[str, Any]] = []
        iot_events_raw = read_only_results.get("list_tracking_events")
        if isinstance(iot_events_raw, dict) and isinstance(
            iot_events_raw.get("events"), list
        ):
            iot_events = [
                e for e in iot_events_raw["events"][:10] if isinstance(e, dict)
            ]

        pickup_points = self._pickup_points_from_response(
            read_only_results.get("get_pickup_points_nearby")
        )

        update: Dict[str, Any] = {
            "messages": msgs,
            "business_track": track_dict,
            "iot_snapshot": iot_snapshot,
            "iot_events": iot_events,
            "pickup_points": pickup_points,
            "read_only_plan": executed_read_only_plan,
            "read_only_results": read_only_results,
        }

        if action_mode:
            # Avoid TypedDict.update(...) overload warnings in static type checkers.
            geo_state = cast(LaPosteState, {**dict(state), **update})
            summary_text = await self._llm_diagnosis_summary_text(
                geo_state
            ) or self._fallback_diagnosis_summary_text(geo_state)
            transition = (
                "Je vais maintenant te proposer une carte de décision (choix relais ou replanification) pour lancer l'action."
                if self._is_french()
                else "I will now present a decision card (pickup-point reroute or home reschedule) before executing any action."
            )
            diag_message: BaseMessage = self._build_text_and_map_message(
                f"{summary_text}\n\n{transition}", geo_state
            )
            update["messages"] = [*msgs, diag_message]

        return update

    # -----------------------------
    # Nodes
    # -----------------------------
    async def route_request(self, state: LaPosteState) -> Dict[str, Any]:
        latest_user = self._latest_human_text(state.get("messages", []))
        previous_tracking_id = str(state.get("tracking_id") or "").strip()
        explicit_tracking_id = self._extract_tracking_id(latest_user)
        has_tracking_context = bool(previous_tracking_id)
        previous_request_mode = str(state.get("request_mode") or "").strip().lower()

        # Conversational continuity: after a capabilities answer, a bare "oui / yes please"
        # should complete the suggested follow-up (group tools by use case), not seed a parcel scenario.
        if (
            not has_tracking_context
            and not explicit_tracking_id
            and previous_request_mode == "capabilities_info"
            and self._looks_like_affirmation(latest_user)
        ):
            intent = {
                "route": "capabilities",
                "topic": "capabilities_grouping",
                "explicit_action": False,
                "requires_parcel_context": False,
                "needs_map": False,
                "need_iot_snapshot": False,
                "need_iot_events": False,
                "need_route_geometry": False,
                "need_pickup_points": False,
                "need_compensation_estimate": False,
                "confidence": 0.95,
                "reason": "follow-up affirmation after capabilities suggestion",
                "_source": "contextual_affirmation",
            }
        else:
            intent = await self._route_intent_with_llm(
                latest_user=latest_user,
                has_tracking_context=has_tracking_context,
                has_explicit_tracking_id=bool(explicit_tracking_id),
            )

        route = str(intent.get("route") or "followup_info").strip().lower()
        explicit_action = self._coerce_bool(
            intent.get("explicit_action"), default=False
        )
        source = str(intent.get("_source") or "unknown")

        if (
            route == "action_flow"
            and self._tuned_bool("behavior.require_explicit_action_for_hitl", True)
            and not explicit_action
        ):
            logger.info(
                "[ParcelOpsAgent] Guardrail: downgrading action_flow to followup_info (no explicit action intent)."
            )
            route = "followup_info"
            source = f"{source}+guardrail"

        request_mode = {
            "capabilities": "capabilities_info",
            "action_flow": "action_flow",
        }.get(route, "followup_info")
        resolved_tracking_id = explicit_tracking_id or previous_tracking_id

        update: Dict[str, Any] = {
            "request_mode": request_mode,
            "routing_mode_source": source,
            "latest_user_text": latest_user,
            "tracking_changed_hint": bool(
                explicit_tracking_id
                and previous_tracking_id
                and explicit_tracking_id != previous_tracking_id
            ),
            "intent_topic": str(intent.get("topic") or "other"),
            "intent_needs_map": self._coerce_bool(intent.get("needs_map"), False),
            "intent_need_iot_snapshot": self._coerce_bool(
                intent.get("need_iot_snapshot"), False
            ),
            "intent_need_iot_events": self._coerce_bool(
                intent.get("need_iot_events"), False
            ),
            "intent_need_route_geometry": self._coerce_bool(
                intent.get("need_route_geometry"), False
            ),
            "intent_need_pickup_points": self._coerce_bool(
                intent.get("need_pickup_points"), False
            ),
            "intent_need_compensation_estimate": self._coerce_bool(
                intent.get("need_compensation_estimate"), False
            ),
            "intent_explicit_action": explicit_action,
            "intent_requires_parcel_context": self._coerce_bool(
                intent.get("requires_parcel_context"),
                request_mode != "capabilities_info",
            ),
            "intent_confidence": self._coerce_float(intent.get("confidence"), 0.0),
            "intent_reason": str(intent.get("reason") or ""),
        }
        if resolved_tracking_id:
            update["tracking_id"] = resolved_tracking_id

        logger.info(
            "[ParcelOpsAgent] route_request mode=%s source=%s topic=%s map=%s explicit_action=%s conf=%.2f user=%r",
            request_mode,
            source,
            update.get("intent_topic"),
            update.get("intent_needs_map"),
            explicit_action,
            float(update.get("intent_confidence") or 0.0),
            latest_user[:200],
        )
        return update

    async def respond_capabilities(self, state: LaPosteState) -> Dict[str, Any]:
        is_fr = self._is_french()
        tool_map = self._tool_map()
        names = sorted(tool_map.keys())
        read_only = set(self._read_only_tool_whitelist())
        latest_user = state.get("latest_user_text") or self._latest_human_text(
            state.get("messages", [])
        )
        intent_topic = str(state.get("intent_topic") or "").strip().lower()
        grouped_view = (
            intent_topic == "capabilities_grouping"
            or self._looks_like_tool_grouping_request(latest_user)
        )

        if not names:
            text = (
                "Je n'ai actuellement aucun outil MCP disponible."
                if is_fr
                else "I currently have no MCP tools available."
            )
            return {"messages": [AIMessage(content=text)], "final_text": text}

        ro_names = [n for n in names if n in read_only]
        other_names = [n for n in names if n not in read_only]

        if grouped_view:
            categories: List[tuple[str, List[str]]] = []

            def pick(*tool_names: str) -> List[str]:
                existing = []
                for n in tool_names:
                    if n in names and n not in seen:
                        existing.append(n)
                        seen.add(n)
                return existing

            seen: set[str] = set()
            categories.append(
                (
                    "Suivi colis (métier)" if is_fr else "Parcel tracking (business)",
                    pick("track_package"),
                )
            )
            categories.append(
                (
                    "Suivi IoT / opérations" if is_fr else "IoT / operations tracking",
                    pick(
                        "get_live_tracking_snapshot",
                        "list_tracking_events",
                        "get_hub_status",
                        "get_vehicle_position",
                        "acknowledge_alert",
                        "advance_simulation_tick",
                    ),
                )
            )
            categories.append(
                (
                    "Carte / points de retrait" if is_fr else "Map / pickup points",
                    pick(
                        "get_route_geometry",
                        "get_pickup_points_nearby",
                        "get_locker_occupancy",
                    ),
                )
            )
            categories.append(
                (
                    "Actions client / livraison"
                    if is_fr
                    else "Customer / delivery actions",
                    pick(
                        "reroute_package_to_pickup_point",
                        "reschedule_delivery",
                        "notify_customer",
                    ),
                )
            )
            categories.append(
                (
                    "Compensation / réclamation" if is_fr else "Compensation / claim",
                    pick("estimate_compensation", "open_claim"),
                )
            )
            categories.append(
                (
                    "Création d'envoi" if is_fr else "Shipment creation",
                    pick("validate_address", "quote_shipping", "create_label"),
                )
            )
            categories.append(
                (
                    "Scénarios de démo" if is_fr else "Demo seeding tools",
                    pick(
                        "seed_demo_parcel_exception",
                        "seed_demo_parcel_exception_for_current_user",
                        "seed_demo_tracking_incident",
                        "who_am_i_demo",
                    ),
                )
            )
            leftovers = [n for n in names if n not in seen]
            if leftovers:
                categories.append(
                    (
                        "Autres outils disponibles"
                        if is_fr
                        else "Other available tools",
                        leftovers,
                    )
                )

            if is_fr:
                parts = [
                    "Parfait. Voici les outils regroupés par cas d'usage (sans exécuter de scénario) :"
                ]
            else:
                parts = [
                    "Sure. Here are the tools grouped by use case (without running any scenario):"
                ]
            for title, tool_names in categories:
                if not tool_names:
                    continue
                parts.append(f"\n{title} :")
                parts.extend([f"- `{n}`" for n in tool_names])
        else:
            if is_fr:
                parts = [
                    "Voici les outils MCP à ma disposition (sans exécution de scénario ni diagnostic) :"
                ]
                if ro_names:
                    parts.append("\nOutils de lecture / diagnostic :")
                    parts.extend([f"- `{n}`" for n in ro_names])
                if other_names:
                    parts.append("\nOutils d'action / autres :")
                    parts.extend([f"- `{n}`" for n in other_names])
                parts.append(
                    "\nSi tu veux, je peux ensuite les regrouper par cas d'usage (suivi, reroutage, replanification, notification, réclamations)."
                )
            else:
                parts = [
                    "Here are the MCP tools available to me (without running any demo scenario or diagnosis):"
                ]
                if ro_names:
                    parts.append("\nRead-only / diagnostic tools:")
                    parts.extend([f"- `{n}`" for n in ro_names])
                if other_names:
                    parts.append("\nAction / other tools:")
                    parts.extend([f"- `{n}`" for n in other_names])
                parts.append(
                    "\nIf you want, I can group them by use case (tracking, reroute, reschedule, notification, claims)."
                )

        text = "\n".join(parts)
        return {"messages": [AIMessage(content=text)], "final_text": text}

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

    async def collect_context(self, state: LaPosteState) -> Dict[str, Any]:
        mode = (state.get("request_mode") or "").strip().lower()
        return await self._collect_compact_context(
            state, action_mode=(mode != "followup_info")
        )

    async def respond_followup(self, state: LaPosteState) -> Dict[str, Any]:
        text = await self._llm_followup_summary_text(state)
        if not text:
            text = self._fallback_followup_summary_text(state)

        include_map = (
            self._coerce_bool(state.get("intent_needs_map"), False)
            if self._tuned_bool("behavior.followup_map_only_when_requested", True)
            else True
        )
        message = (
            self._build_text_and_map_message(text, state)
            if include_map
            else AIMessage(content=text)
        )
        return {"messages": [message], "final_text": text}

    async def choose_resolution_hitl(self, state: LaPosteState) -> Dict[str, Any]:
        tracking_id = state.get("tracking_id") or "UNKNOWN"
        pickup_points = state.get("pickup_points") or []
        business_track = state.get("business_track") or {}
        iot_snapshot = state.get("iot_snapshot") or {}
        is_fr = self._is_french()

        recommended_id = (
            str(pickup_points[0].get("pickup_point_id")) if pickup_points else None
        )

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
            choice: Dict[str, Any] = {
                "id": f"reroute:{pp_id}",
                "label": f"{pp_id} - {name}"[:80],
                "description": ", ".join(desc)[:200]
                if desc
                else (
                    "Rerouter vers ce point relais."
                    if is_fr
                    else "Reroute to this pickup point."
                ),
            }
            if idx == 0:
                choice["default"] = True
            choices.append(choice)

        choices.extend(
            [
                {
                    "id": "reschedule:afternoon",
                    "label": "Replanifier domicile (demain après-midi)"
                    if is_fr
                    else "Reschedule home delivery (tomorrow afternoon)",
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
            title = (
                self.get_tuned_text("prompts.hitl_resolution_title_fr")
                or "Choisir une action de résolution"
            )
            question = self._render_tuned_prompt(
                "prompts.hitl_resolution_question_fr", tracking_id=tracking_id
            )
        else:
            title = (
                self.get_tuned_text("prompts.hitl_resolution_title_en")
                or "Choose a resolution action"
            )
            question = self._render_tuned_prompt(
                "prompts.hitl_resolution_question_en", tracking_id=tracking_id
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
            decision if isinstance(decision, dict) else {}, pickup_points=pickup_points
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
            {"tracking_id": tracking_id, "channel": "sms", "message": notify_message},
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
            {"tracking_id": tracking_id, "channel": "sms", "message": notify_message},
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
                        text, state, highlight_pickup_point_id=str(point_id)
                    )
                ],
                "final_text": text,
            }

        if action in {"reschedule", "cancel"}:
            return {
                "messages": [self._build_text_and_map_message(text, state)],
                "final_text": text,
            }

        return {"messages": [AIMessage(content=text)], "final_text": text}
