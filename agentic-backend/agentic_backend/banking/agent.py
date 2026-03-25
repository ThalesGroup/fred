from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from typing import Annotated, Any, Dict, List, Optional, Sequence, Type, TypedDict

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
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


class SimpleTransferState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]

    user_input: str
    intent: Optional[str]

    source_id: Optional[str]
    destination_id: Optional[str]
    amount: Optional[float]

    risk_result: Optional[Dict[str, Any]]
    prepared_transfer: Optional[Dict[str, Any]]
    transaction_id: Optional[str]
    commit_result: Optional[Dict[str, Any]]

    awaiting_confirmation: bool
    confirmation_received: Optional[bool]
    cancellation_received: Optional[bool]

    workflow_name: Optional[str]
    workflow_step: Optional[str]
    workflow_status: Optional[str]

    assistant_message: Optional[str]

    error_code: Optional[str]
    error_message: Optional[str]


TRANSFER_TUNING = AgentTuning(
    role="Bank Transfer Workflow Agent",
    description=(
        "Agent bancaire orienté workflow: extraction de demande de virement, "
        "évaluation de risque, préparation, confirmation explicite, puis commit."
    ),
    tags=["banking", "workflow", "transaction", "mcp", "demo"],
    mcp_servers=[
        MCPServerRef(id="mcp-bank-core-demo"),
        MCPServerRef(id="mcp-risk-guard-demo"),
    ],
    fields=[
        FieldSpec(
            key="i18n.default_language",
            type="select",
            title="Default language",
            description="Language used when runtime context does not provide one.",
            required=False,
            default="fr",
            enum=["fr", "en"],
            ui=UIHints(group="I18n"),
        ),
        FieldSpec(
            key="prompts.transfer_parser",
            type="prompt",
            title="Transfer Parser Prompt",
            description=(
                "Prompt used to detect INITIATE_TRANSFER and extract source_id, "
                "destination_id and amount."
            ),
            required=True,
            default=(
                "Tu extrais une demande de virement bancaire.\n"
                "Réponds en JSON strict uniquement.\n"
                "Schema:\n"
                "{\n"
                '  "intent": "INITIATE_TRANSFER|UNKNOWN",\n'
                '  "source_id": "ACC-001|...",\n'
                '  "destination_id": "ACC-002|EXT-XYZ|...",\n'
                '  "amount": 0.0\n'
                "}\n"
                "Règles:\n"
                "- intent=INITIATE_TRANSFER uniquement si la demande vise un virement.\n"
                "- amount est un nombre décimal.\n"
                "- Si un champ manque: mets null.\n"
                "Message utilisateur: {user_input}"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


@expose_runtime_source("agent.BankTransferWorkflowAgent")
class BankTransferWorkflowAgent(AgentFlow):
    tuning = TRANSFER_TUNING

    default_chat_options = AgentChatOptions(
        search_policy_selection=False,
        libraries_selection=False,
        search_rag_scoping=False,
        deep_search_delegate=False,
        attach_files=False,
    )

    WORKFLOW_NAME = "simple_bank_transfer"
    INTENT_INITIATE = "INITIATE_TRANSFER"
    INTENT_CONFIRM = "CONFIRM_TRANSFER"
    INTENT_CANCEL = "CANCEL_TRANSFER"
    INTENT_UNKNOWN = "UNKNOWN"

    CONFIRM_WORDS = {"oui", "confirmer", "ok", "valider", "yes", "confirm"}
    CANCEL_WORDS = {"non", "annuler", "stop", "abandonner", "cancel"}

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)
        self.model = None
        self.mcp: Optional[MCPRuntime] = None

    def get_state_schema(self) -> Type:
        return SimpleTransferState

    def build_runtime_structure(self) -> None:
        self._graph = self._build_graph()

    async def activate_runtime(self) -> None:
        self.model = get_default_chat_model()
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

    async def aclose(self) -> None:
        if self.mcp:
            await self.mcp.aclose()

    def _build_graph(self) -> StateGraph:
        g = StateGraph(SimpleTransferState)
        g.add_node("route_turn", self.route_turn)
        g.add_node("parse_transfer_request", self.parse_transfer_request)
        g.add_node("validate_transfer_input", self.validate_transfer_input)
        g.add_node("evaluate_risk", self.evaluate_risk)
        g.add_node("prepare_transfer", self.prepare_transfer)
        g.add_node("ask_confirmation", self.ask_confirmation)
        g.add_node("commit_transfer", self.commit_transfer)
        g.add_node("cancel_transfer", self.cancel_transfer)
        g.add_node("remind_confirmation", self.remind_confirmation)
        g.add_node(
            "respond_no_pending_confirmation", self.respond_no_pending_confirmation
        )
        g.add_node("respond_help", self.respond_help)

        g.set_entry_point("route_turn")

        g.add_conditional_edges(
            "route_turn",
            self._route_after_turn,
            {
                "initiate": "parse_transfer_request",
                "confirm": "commit_transfer",
                "cancel": "cancel_transfer",
                "waiting_other": "remind_confirmation",
                "no_pending": "respond_no_pending_confirmation",
                "help": "respond_help",
            },
        )
        g.add_edge("parse_transfer_request", "validate_transfer_input")
        g.add_conditional_edges(
            "validate_transfer_input",
            self._route_after_validation,
            {"ok": "evaluate_risk", "final": END},
        )
        g.add_conditional_edges(
            "evaluate_risk",
            self._route_after_risk,
            {"ok": "prepare_transfer", "final": END},
        )
        g.add_conditional_edges(
            "prepare_transfer",
            self._route_after_prepare,
            {"ok": "ask_confirmation", "final": END},
        )
        g.add_conditional_edges(
            "ask_confirmation",
            self._route_after_confirmation_choice,
            {
                "confirm": "commit_transfer",
                "cancel": "cancel_transfer",
                "remind": "remind_confirmation",
            },
        )
        g.add_edge("commit_transfer", END)
        g.add_edge("cancel_transfer", END)
        g.add_edge("remind_confirmation", END)
        g.add_edge("respond_no_pending_confirmation", END)
        g.add_edge("respond_help", END)
        return g

    @staticmethod
    def _route_after_turn(state: SimpleTransferState) -> str:
        awaiting = bool(state.get("awaiting_confirmation"))
        intent = str(state.get("intent") or "UNKNOWN")
        if awaiting:
            if intent == BankTransferWorkflowAgent.INTENT_CONFIRM:
                return "confirm"
            if intent == BankTransferWorkflowAgent.INTENT_CANCEL:
                return "cancel"
            return "waiting_other"
        if intent == BankTransferWorkflowAgent.INTENT_INITIATE:
            return "initiate"
        if intent in {
            BankTransferWorkflowAgent.INTENT_CONFIRM,
            BankTransferWorkflowAgent.INTENT_CANCEL,
        }:
            return "no_pending"
        return "help"

    @staticmethod
    def _route_after_validation(state: SimpleTransferState) -> str:
        return "ok" if state.get("workflow_status") == "IN_PROGRESS" else "final"

    @staticmethod
    def _route_after_risk(state: SimpleTransferState) -> str:
        return "ok" if state.get("workflow_status") == "IN_PROGRESS" else "final"

    @staticmethod
    def _route_after_prepare(state: SimpleTransferState) -> str:
        return (
            "ok"
            if state.get("workflow_status") == "IN_PROGRESS"
            and bool(state.get("transaction_id"))
            else "final"
        )

    @staticmethod
    def _route_after_confirmation_choice(state: SimpleTransferState) -> str:
        if bool(state.get("confirmation_received")) and not bool(
            state.get("awaiting_confirmation")
        ):
            return "confirm"
        if bool(state.get("cancellation_received")) and not bool(
            state.get("awaiting_confirmation")
        ):
            return "cancel"
        return "remind"

    async def route_turn(self, state: SimpleTransferState) -> Dict[str, Any]:
        user_input = self._latest_human_text(state.get("messages", []))
        awaiting_confirmation = bool(
            state.get("awaiting_confirmation") or self._is_confirmation_pending(state)
        )
        normalized = self._normalize_text(user_input)

        if awaiting_confirmation:
            confirmation_reply = self._classify_confirmation_reply(normalized)
            if confirmation_reply == "confirm":
                self._log_event("confirmation_received", state)
                return {
                    "user_input": user_input,
                    "intent": self.INTENT_CONFIRM,
                    "awaiting_confirmation": False,
                    "confirmation_received": True,
                    "cancellation_received": False,
                }
            if confirmation_reply == "cancel":
                self._log_event("transfer_cancelled", state)
                return {
                    "user_input": user_input,
                    "intent": self.INTENT_CANCEL,
                    "awaiting_confirmation": False,
                    "confirmation_received": False,
                    "cancellation_received": True,
                }
            return {
                "user_input": user_input,
                "intent": self.INTENT_UNKNOWN,
                "awaiting_confirmation": True,
            }

        if normalized in self.CONFIRM_WORDS:
            return {"user_input": user_input, "intent": self.INTENT_CONFIRM}
        if normalized in self.CANCEL_WORDS:
            return {"user_input": user_input, "intent": self.INTENT_CANCEL}

        if self._looks_like_transfer_request(user_input):
            self._log_event("workflow_started", state)
            return {"user_input": user_input, "intent": self.INTENT_INITIATE}
        return {"user_input": user_input, "intent": self.INTENT_UNKNOWN}

    async def parse_transfer_request(
        self, state: SimpleTransferState
    ) -> Dict[str, Any]:
        parsed = await self._extract_transfer_request(state.get("user_input") or "")
        source_id = parsed.get("source_id")
        destination_id = parsed.get("destination_id")
        amount = parsed.get("amount")

        if not source_id or not destination_id or amount is None:
            text = (
                "Merci de préciser le compte source, le compte destination et le montant. "
                "Exemple: `Je veux transférer 200 de ACC-001 vers ACC-002`."
            )
            self._log_event(
                "workflow_failed", state, error_code="MISSING_TRANSFER_INPUT"
            )
            return self._final_error_update(
                text=text,
                workflow_status="FAILED",
                workflow_step="START",
                error_code="MISSING_TRANSFER_INPUT",
                error_message="Missing source_id, destination_id or amount in request",
            )

        self._log_event(
            "transfer_request_parsed",
            state,
            source_id=source_id,
            destination_id=destination_id,
            amount=amount,
        )
        return {
            "source_id": source_id,
            "destination_id": destination_id,
            "amount": amount,
            "risk_result": None,
            "prepared_transfer": None,
            "transaction_id": None,
            "commit_result": None,
            "awaiting_confirmation": False,
            "confirmation_received": None,
            "cancellation_received": None,
            "workflow_name": self.WORKFLOW_NAME,
            "workflow_step": "TRANSFER_REQUEST_PARSED",
            "workflow_status": "IN_PROGRESS",
            "assistant_message": None,
            "error_code": None,
            "error_message": None,
        }

    async def validate_transfer_input(
        self, state: SimpleTransferState
    ) -> Dict[str, Any]:
        source_id = str(state.get("source_id") or "").strip().upper()
        destination_id = str(state.get("destination_id") or "").strip().upper()
        amount = state.get("amount")

        if amount is None or float(amount) <= 0:
            self._log_event(
                "workflow_failed", state, error_code="INVALID_TRANSFER_INPUT"
            )
            return self._final_error_update(
                text="Le montant doit être strictement positif.",
                workflow_status="FAILED",
                workflow_step="TRANSFER_REQUEST_PARSED",
                error_code="INVALID_TRANSFER_INPUT",
                error_message="amount must be > 0",
            )
        if not source_id or not destination_id:
            self._log_event(
                "workflow_failed", state, error_code="INVALID_TRANSFER_INPUT"
            )
            return self._final_error_update(
                text="Le compte source et le compte destination sont obligatoires.",
                workflow_status="FAILED",
                workflow_step="TRANSFER_REQUEST_PARSED",
                error_code="INVALID_TRANSFER_INPUT",
                error_message="source_id and destination_id are required",
            )
        if source_id == destination_id:
            self._log_event(
                "workflow_failed", state, error_code="INVALID_TRANSFER_INPUT"
            )
            return self._final_error_update(
                text="Le compte source et le compte destination doivent être différents.",
                workflow_status="FAILED",
                workflow_step="TRANSFER_REQUEST_PARSED",
                error_code="INVALID_TRANSFER_INPUT",
                error_message="source_id and destination_id must differ",
            )
        return {
            "source_id": source_id,
            "destination_id": destination_id,
            "amount": float(amount),
            "workflow_status": "IN_PROGRESS",
            "error_code": None,
            "error_message": None,
        }

    async def evaluate_risk(self, state: SimpleTransferState) -> Dict[str, Any]:
        source_id = state.get("source_id")
        destination_id = state.get("destination_id")
        amount = state.get("amount")
        if not source_id or not destination_id or amount is None:
            return self._final_error_update(
                text="Impossible d’évaluer le risque: paramètres de virement incomplets.",
                workflow_status="FAILED",
                workflow_step="TRANSFER_REQUEST_PARSED",
                error_code="RISK_EVALUATION_FAILED",
                error_message="missing transfer parameters before risk evaluation",
            )

        risk_result, msgs = await self._call_tool(
            "evaluate_transfer_risk",
            {
                "source_id": source_id,
                "destination_id": destination_id,
                "amount": float(amount),
            },
        )
        if not isinstance(risk_result, dict) or risk_result.get("ok") is False:
            self._log_event(
                "workflow_failed", state, error_code="RISK_EVALUATION_FAILED"
            )
            text = "L’évaluation du risque a échoué. Le virement ne peut pas être poursuivi."
            return {
                "messages": [*msgs, AIMessage(content=text)],
                "assistant_message": text,
                "workflow_step": "TRANSFER_REQUEST_PARSED",
                "workflow_status": "FAILED",
                "error_code": "RISK_EVALUATION_FAILED",
                "error_message": str(
                    risk_result.get("error") if isinstance(risk_result, dict) else ""
                )
                or "evaluate_transfer_risk returned an error",
            }

        self._log_event(
            "risk_evaluated",
            state,
            risk_score=risk_result.get("risk_score"),
            requires_validation=risk_result.get("requires_validation"),
        )
        return {
            "messages": msgs,
            "risk_result": risk_result,
            "workflow_step": "RISK_EVALUATED",
            "workflow_status": "IN_PROGRESS",
            "error_code": None,
            "error_message": None,
        }

    async def prepare_transfer(self, state: SimpleTransferState) -> Dict[str, Any]:
        source_id = state.get("source_id")
        destination_id = state.get("destination_id")
        amount = state.get("amount")
        if not source_id or not destination_id or amount is None:
            return self._final_error_update(
                text="Impossible de préparer le virement: paramètres incomplets.",
                workflow_status="FAILED",
                workflow_step="RISK_EVALUATED",
                error_code="PREPARE_TRANSFER_FAILED",
                error_message="missing transfer parameters before prepare_transfer",
            )

        prepared, msgs = await self._call_tool(
            "prepare_transfer",
            {
                "source_id": source_id,
                "destination_id": destination_id,
                "amount": float(amount),
            },
        )

        if not isinstance(prepared, dict) or prepared.get("ok") is False:
            reason = (
                str(prepared.get("reason") or "") if isinstance(prepared, dict) else ""
            )
            if reason == "INSUFFICIENT_FUNDS":
                text = "Le virement ne peut pas être préparé: fonds insuffisants."
            else:
                text = "Le virement n’a pas pu être préparé."
            self._log_event(
                "workflow_failed", state, error_code="PREPARE_TRANSFER_FAILED"
            )
            return {
                "messages": [*msgs, AIMessage(content=text)],
                "assistant_message": text,
                "workflow_step": "RISK_EVALUATED",
                "workflow_status": "FAILED",
                "error_code": "PREPARE_TRANSFER_FAILED",
                "error_message": str(
                    prepared.get("error") if isinstance(prepared, dict) else ""
                )
                or reason
                or "prepare_transfer returned an error",
            }

        transaction_id = str(prepared.get("transaction_id") or "").strip()
        if not transaction_id:
            self._log_event(
                "workflow_failed", state, error_code="PREPARE_TRANSFER_FAILED"
            )
            return {
                "messages": [
                    *msgs,
                    AIMessage(content="Le virement n’a pas pu être préparé."),
                ],
                "assistant_message": "Le virement n’a pas pu être préparé.",
                "workflow_step": "RISK_EVALUATED",
                "workflow_status": "FAILED",
                "error_code": "PREPARE_TRANSFER_FAILED",
                "error_message": "missing transaction_id in prepare_transfer result",
            }

        self._log_event("transfer_prepared", state, transaction_id=transaction_id)
        return {
            "messages": msgs,
            "prepared_transfer": prepared,
            "transaction_id": transaction_id,
            "workflow_step": "TRANSFER_PREPARED",
            "workflow_status": "IN_PROGRESS",
            "error_code": None,
            "error_message": None,
        }

    async def ask_confirmation(self, state: SimpleTransferState) -> Dict[str, Any]:
        source_id = state.get("source_id") or "n/a"
        destination_id = state.get("destination_id") or "n/a"
        amount = state.get("amount")
        currency = self._safe_get(
            state.get("prepared_transfer"), "currency", default="EUR"
        )
        transaction_id = state.get("transaction_id") or "n/a"
        risk_result = state.get("risk_result") or {}
        risk_score = self._safe_get(risk_result, "risk_score", default="n/a")
        risk_reason = self._safe_get(risk_result, "reason", default="n/a")
        requires_validation = bool(
            self._safe_get(risk_result, "requires_validation", default=False)
        )
        risk_score_value = self._coerce_amount(risk_score)
        high_risk = bool(
            requires_validation
            or (risk_score_value is not None and risk_score_value >= 50.0)
        )

        risk_alert = ""
        title = "Confirmer le virement"
        confirm_description = "Exécuter le virement maintenant."
        if high_risk:
            risk_alert = (
                "ALERTE : ce virement est classé `RISQUE ÉLEVÉ`.\n"
                "Merci de vérifier attentivement les paramètres avant confirmation.\n"
            )
            title = "Confirmer le virement (Risque élevé)"
            confirm_description = "Exécuter le virement malgré le risque élevé."

        text = (
            "Le virement a été préparé avec succès.\n"
            f"Source : `{source_id}`\n"
            f"Destination : `{destination_id}`\n"
            f"Montant : `{amount}` `{currency}`\n"
            f"Transaction : `{transaction_id}`\n"
            f"Risque : score `{risk_score}`, raison `{risk_reason}`.\n"
            f"{risk_alert}"
            "Aucun débit n’a encore été effectué.\n"
            "Répondez `confirmer` pour exécuter le virement ou `annuler` pour l’abandonner."
        )
        self._log_event("confirmation_requested", state, transaction_id=transaction_id)
        decision = interrupt(
            {
                "stage": "bank_transfer_confirmation",
                "title": title,
                "question": text,
                "choices": [
                    {
                        "id": "confirm",
                        "label": "Confirmer",
                        "description": confirm_description,
                        "default": True,
                    },
                    {
                        "id": "cancel",
                        "label": "Annuler",
                        "description": "Abandonner le virement sans débit.",
                        "default": False,
                    },
                ],
                "free_text": False,
                "metadata": {
                    "workflow_name": self.WORKFLOW_NAME,
                    "transaction_id": transaction_id,
                    "source_id": source_id,
                    "destination_id": destination_id,
                    "amount": amount,
                    "currency": currency,
                    "risk_score": risk_score,
                    "requires_validation": requires_validation,
                    "high_risk": high_risk,
                    "risk_reason": risk_reason,
                },
            }
        )
        choice = self._extract_choice_id(decision)
        if choice in {"confirm", "proceed"}:
            self._log_event(
                "confirmation_received", state, transaction_id=transaction_id
            )
            return {
                "awaiting_confirmation": False,
                "confirmation_received": True,
                "cancellation_received": False,
                "workflow_step": "AWAITING_CONFIRMATION",
                "workflow_status": "IN_PROGRESS",
            }
        if choice == "cancel":
            self._log_event("transfer_cancelled", state, transaction_id=transaction_id)
            return {
                "awaiting_confirmation": False,
                "confirmation_received": False,
                "cancellation_received": True,
                "workflow_step": "AWAITING_CONFIRMATION",
                "workflow_status": "CANCELLED",
            }
        return {
            "awaiting_confirmation": True,
            "confirmation_received": None,
            "cancellation_received": None,
            "workflow_step": "AWAITING_CONFIRMATION",
            "workflow_status": "AWAITING_CONFIRMATION",
        }

    async def remind_confirmation(self, state: SimpleTransferState) -> Dict[str, Any]:
        text = (
            "Le virement est prêt mais pas encore exécuté.\n"
            "Répondez `confirmer` pour l’exécuter ou `annuler` pour l’abandonner."
        )
        return {
            "messages": [AIMessage(content=text)],
            "assistant_message": text,
            "workflow_step": "AWAITING_CONFIRMATION",
            "workflow_status": "AWAITING_CONFIRMATION",
            "awaiting_confirmation": True,
        }

    async def commit_transfer(self, state: SimpleTransferState) -> Dict[str, Any]:
        transaction_id = state.get("transaction_id")
        if not transaction_id:
            return self._final_error_update(
                text="Aucun virement préparé n’est disponible pour exécution.",
                workflow_status="FAILED",
                workflow_step=state.get("workflow_step") or "START",
                error_code="COMMIT_TRANSFER_FAILED",
                error_message="missing transaction_id before commit_transfer",
            )
        if not state.get("confirmation_received") or state.get("awaiting_confirmation"):
            return self._final_error_update(
                text="Confirmation explicite requise avant exécution du virement.",
                workflow_status="FAILED",
                workflow_step=state.get("workflow_step") or "AWAITING_CONFIRMATION",
                error_code="COMMIT_TRANSFER_FAILED",
                error_message="explicit confirmation missing",
            )

        commit_result, msgs = await self._call_tool(
            "commit_transfer",
            {"transaction_id": transaction_id},
        )
        if not isinstance(commit_result, dict) or commit_result.get("ok") is False:
            text = "Le virement n’a pas pu être exécuté."
            self._log_event(
                "workflow_failed", state, error_code="COMMIT_TRANSFER_FAILED"
            )
            return {
                "messages": [*msgs, AIMessage(content=text)],
                "assistant_message": text,
                "commit_result": commit_result
                if isinstance(commit_result, dict)
                else None,
                "awaiting_confirmation": False,
                "workflow_status": "FAILED",
                "workflow_step": "AWAITING_CONFIRMATION",
                "error_code": "COMMIT_TRANSFER_FAILED",
                "error_message": str(
                    commit_result.get("error")
                    if isinstance(commit_result, dict)
                    else ""
                )
                or "commit_transfer returned an error",
            }

        source_balance = self._safe_get(commit_result, "source_balance", default="n/a")
        destination_balance = self._safe_get(
            commit_result, "destination_balance", default=None
        )
        lines = [
            "Le virement a été exécuté avec succès.",
            f"Transaction : `{transaction_id}`",
            f"Statut : `{commit_result.get('status', 'COMPLETED')}`",
            f"Nouveau solde source : `{source_balance}` EUR",
        ]
        if destination_balance is not None:
            lines.append(f"Nouveau solde destination : `{destination_balance}` EUR")
        text = "\n".join(lines)

        self._log_event("transfer_committed", state, transaction_id=transaction_id)
        self._log_event("workflow_completed", state, transaction_id=transaction_id)
        return {
            "messages": [*msgs, AIMessage(content=text)],
            "assistant_message": text,
            "commit_result": commit_result,
            "awaiting_confirmation": False,
            "confirmation_received": True,
            "cancellation_received": False,
            "workflow_step": "TRANSFER_COMMITTED",
            "workflow_status": "COMPLETED",
            "error_code": None,
            "error_message": None,
        }

    async def cancel_transfer(self, state: SimpleTransferState) -> Dict[str, Any]:
        text = "Le virement préparé a été annulé. Aucun débit n’a été effectué."
        self._log_event(
            "transfer_cancelled", state, transaction_id=state.get("transaction_id")
        )
        return {
            "messages": [AIMessage(content=text)],
            "assistant_message": text,
            "awaiting_confirmation": False,
            "confirmation_received": False,
            "cancellation_received": True,
            "workflow_status": "CANCELLED",
            "workflow_step": "AWAITING_CONFIRMATION",
            "error_code": None,
            "error_message": None,
        }

    async def respond_no_pending_confirmation(
        self, state: SimpleTransferState
    ) -> Dict[str, Any]:
        text = (
            "Aucun virement n’est actuellement en attente de confirmation.\n"
            "Je peux vous aider à préparer un virement.\n"
            "Exemple : `Je veux transférer 200 de ACC-001 vers ACC-002`."
        )
        return {
            "messages": [AIMessage(content=text)],
            "assistant_message": text,
        }

    async def respond_help(self, state: SimpleTransferState) -> Dict[str, Any]:
        text = (
            "Je peux vous aider à préparer un virement.\n"
            "Exemple : `Je veux transférer 200 de ACC-001 vers ACC-002`."
        )
        return {
            "messages": [AIMessage(content=text)],
            "assistant_message": text,
        }

    async def _extract_transfer_request(self, user_input: str) -> Dict[str, Any]:
        # Keep the fast deterministic path first to avoid leaking internal parser
        # outputs in streamed UI events for straightforward transfer phrases.
        parsed = self._extract_transfer_request_with_regex(user_input)
        if parsed.get("intent") == self.INTENT_INITIATE:
            return parsed
        return await self._extract_transfer_request_with_llm(user_input)

    async def _extract_transfer_request_with_llm(
        self, user_input: str
    ) -> Dict[str, Any]:
        if not self.model or not user_input.strip():
            return {"intent": self.INTENT_UNKNOWN}

        prompt = self._render_transfer_parser_prompt(user_input)
        try:
            invoke_model: Any = self.model
            bind = getattr(self.model, "bind", None)
            if callable(bind):
                try:
                    invoke_model = bind(stream=False)
                except Exception:
                    invoke_model = self.model

            response = await invoke_model.ainvoke([HumanMessage(content=prompt)])
            text = self._message_content_to_text(getattr(response, "content", ""))
            payload = self._parse_json_object(text) or {}
            intent = str(payload.get("intent") or self.INTENT_UNKNOWN).upper().strip()
            source_id = self._coerce_account_id(payload.get("source_id"))
            destination_id = self._coerce_account_id(payload.get("destination_id"))
            amount = self._coerce_amount(payload.get("amount"))
            return {
                "intent": intent
                if intent == self.INTENT_INITIATE
                else self.INTENT_UNKNOWN,
                "source_id": source_id,
                "destination_id": destination_id,
                "amount": amount,
            }
        except Exception:
            return {"intent": self.INTENT_UNKNOWN}

    def _extract_transfer_request_with_regex(self, user_input: str) -> Dict[str, Any]:
        text = user_input or ""
        accounts = re.findall(r"\b(?:ACC|EXT)-[A-Z0-9-]+\b", text.upper())
        amount_match = re.search(r"(\d+(?:[.,]\d+)?)", text)
        amount = self._coerce_amount(amount_match.group(1)) if amount_match else None
        if (
            len(accounts) >= 2
            and amount is not None
            and self._looks_like_transfer_request(text)
        ):
            return {
                "intent": self.INTENT_INITIATE,
                "source_id": accounts[0],
                "destination_id": accounts[1],
                "amount": amount,
            }
        return {"intent": self.INTENT_UNKNOWN}

    def _render_transfer_parser_prompt(self, user_input: str) -> str:
        template = self.get_tuned_text("prompts.transfer_parser") or ""
        if not template:
            return (
                "Extract bank transfer request as JSON with intent/source_id/"
                f"destination_id/amount. User message: {user_input}"
            )
        return template.replace("{user_input}", user_input).strip()

    def _tool_map(self) -> Dict[str, BaseTool]:
        if not self.mcp:
            return {}
        tool_map: Dict[str, BaseTool] = {}
        for tool in self.mcp.get_tools():
            if tool.name in tool_map:
                logger.warning(
                    "[BankTransferWorkflowAgent] duplicate tool name %s ignored",
                    tool.name,
                )
            tool_map[tool.name] = tool
        return tool_map

    async def _call_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> tuple[Any, List[BaseMessage]]:
        tool = self._tool_map().get(tool_name)
        if not tool:
            payload = {"ok": False, "error": f"Tool '{tool_name}' not found"}
            return payload, [AIMessage(content=self._json_str(payload))]

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
            payload = {"ok": False, "error": str(exc)}
            tool_result_msg = ToolMessage(
                content=self._json_str(payload),
                tool_call_id=call_id,
                name=tool_name,
                status="error",
            )
            return payload, [tool_call_msg, tool_result_msg]

    @staticmethod
    def _latest_human_text(messages: Sequence[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                if isinstance(message.content, str):
                    return message.content.strip()
                return str(message.content).strip()
        return ""

    @staticmethod
    def _normalize_text(text: str) -> str:
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
    def _extract_choice_id(cls, decision: Any) -> str:
        if isinstance(decision, str):
            return cls._classify_confirmation_reply(cls._normalize_text(decision))
        if not isinstance(decision, dict):
            return ""
        for key in ("choice_id", "answer", "id"):
            value = decision.get(key)
            if isinstance(value, str) and value.strip():
                classified = cls._classify_confirmation_reply(
                    cls._normalize_text(value)
                )
                if classified:
                    return classified
        for key in ("text", "notes"):
            value = decision.get(key)
            if isinstance(value, str) and value.strip():
                classified = cls._classify_confirmation_reply(
                    cls._normalize_text(value)
                )
                if classified:
                    return classified
        nested_choice = decision.get("choice")
        if isinstance(nested_choice, dict):
            nested_id = nested_choice.get("id")
            if isinstance(nested_id, str) and nested_id.strip():
                classified = cls._classify_confirmation_reply(
                    cls._normalize_text(nested_id)
                )
                if classified:
                    return classified
        return ""

    @classmethod
    def _classify_confirmation_reply(cls, normalized_text: str) -> str:
        if not normalized_text:
            return ""
        if normalized_text in cls.CONFIRM_WORDS:
            return "confirm"
        if normalized_text in cls.CANCEL_WORDS:
            return "cancel"
        padded = f" {normalized_text} "
        for marker in cls.CONFIRM_WORDS:
            if marker and f" {marker} " in padded:
                return "confirm"
        for marker in cls.CANCEL_WORDS:
            if marker and f" {marker} " in padded:
                return "cancel"
        return ""

    @staticmethod
    def _is_confirmation_pending(state: SimpleTransferState) -> bool:
        status = str(state.get("workflow_status") or "").strip().upper()
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return False
        if not state.get("transaction_id"):
            return False
        if not isinstance(state.get("prepared_transfer"), dict):
            return False
        if isinstance(state.get("commit_result"), dict) and state.get("commit_result"):
            return False
        if state.get("confirmation_received") or state.get("cancellation_received"):
            return False
        return True

    @classmethod
    def _looks_like_transfer_request(cls, text: str) -> bool:
        normalized = cls._normalize_text(text)
        has_transfer_word = any(
            marker in normalized
            for marker in ("transfer", "transfere", "virement", "virer", "envoyer")
        )
        has_two_accounts = (
            len(re.findall(r"\b(?:ACC|EXT)-[A-Z0-9-]+\b", text.upper())) >= 2
        )
        has_amount = re.search(r"(\d+(?:[.,]\d+)?)", text) is not None
        return bool(
            (has_transfer_word and has_amount) or (has_two_accounts and has_amount)
        )

    @staticmethod
    def _coerce_amount(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().replace(",", ".")
            try:
                return float(normalized)
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_account_id(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        normalized = value.strip().upper()
        return normalized if re.match(r"^(ACC|EXT)-[A-Z0-9-]+$", normalized) else None

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text.strip())
            return "\n".join(chunk for chunk in chunks if chunk).strip()
        return str(content).strip()

    @staticmethod
    def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
        stripped = (text or "").strip()
        if not stripped:
            return None
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _safe_get(payload: Any, key: str, default: Any = None) -> Any:
        if not isinstance(payload, dict):
            return default
        value = payload.get(key)
        return default if value is None else value

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

    @staticmethod
    def _json_str(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    @staticmethod
    def _final_error_update(
        *,
        text: str,
        workflow_status: str,
        workflow_step: str,
        error_code: str,
        error_message: str,
    ) -> Dict[str, Any]:
        return {
            "messages": [AIMessage(content=text)],
            "assistant_message": text,
            "awaiting_confirmation": False,
            "confirmation_received": False,
            "cancellation_received": False,
            "workflow_status": workflow_status,
            "workflow_step": workflow_step,
            "error_code": error_code,
            "error_message": error_message,
        }

    def _log_event(self, event: str, state: SimpleTransferState, **extra: Any) -> None:
        payload = {
            "event": event,
            "session_id": getattr(self.runtime_context, "session_id", None),
            "workflow_name": state.get("workflow_name") or self.WORKFLOW_NAME,
            "workflow_step": state.get("workflow_step"),
            "workflow_status": state.get("workflow_status"),
            "source_id": state.get("source_id"),
            "destination_id": state.get("destination_id"),
            "amount": state.get("amount"),
            "transaction_id": state.get("transaction_id"),
        }
        payload.update(extra)
        logger.info("[BankTransferWorkflowAgent] %s", payload)
