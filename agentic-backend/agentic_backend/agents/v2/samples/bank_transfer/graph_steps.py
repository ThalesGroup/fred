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
Business steps for the Bank Transfer graph agent sample.

Read this file to understand how the agent:
- classifies the user message and extracts transfer parameters (intent_router_step)
- answers conversational questions (model_text_step)
- validates the source account via bank-core MCP
- checks KYC compliance via risk-guard MCP
- evaluates transfer risk and asks for confirmation when elevated (choice_step)
- prepares a pending transaction and asks for final HITL confirmation (choice_step)
- commits the transaction via bank-core MCP

Architecture notes:
- Every terminal branch (KYC blocked, risk cancelled, insufficient funds,
  user cancels) writes final_text + done_reason before routing to "finalize".
- The two HITL gates (confirm_risk, confirm_transfer) use choice_step so the
  graph pauses, checkpoints state, and resumes when the user responds.
- MCP tools are called via invoke_runtime_tool; the tool names must match the
  function names declared in the bank-core and risk-guard MCP servers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentic_backend.core.agents.v2 import (
    GraphNodeContext,
    GraphNodeResult,
    HumanChoiceOption,
)
from agentic_backend.core.agents.v2.graph.authoring import (
    StepResult,
    choice_step,
    intent_router_step,
    model_text_step,
    typed_node,
)
from agentic_backend.core.agents.v2.graph.authoring import (
    finalize_step as _finalize_step,
)

from .graph_state import BankTransferState

# ── System prompts ─────────────────────────────────────────────────────────────

_INTENT_SYSTEM_PROMPT = """\
You are a routing assistant for a bank transfer agent.

The agent can execute fund transfers between accounts. It requires:
- source_account_id: the account to debit (e.g. ACC-001)
- destination_account_id: the account or external destination to credit
  (internal: ACC-xxx, external: EXT-xxx)
- amount: a positive number (no currency symbol needed)

Classify the user message:
- "transfer_request": the user explicitly wants to move money. Extract all three
  fields from the message. If a field is not mentioned, leave it null.
- "conversational": anything else — questions, greetings, capability inquiries,
  status questions, or messages that do not request an actual transfer.
"""

_CONVERSATIONAL_SYSTEM_PROMPT = """\
You are a helpful bank transfer assistant.

Answer the user's question clearly and concisely. You can help users:
- Understand how to initiate a transfer (source account, destination, amount)
- Learn which account IDs are available (internal: ACC-001, ACC-002;
  external destinations start with EXT-)
- Understand what happens during the transfer workflow (KYC check, risk
  evaluation, two confirmation steps before money moves)

Keep your reply short and actionable.
"""


# ── Intent model ───────────────────────────────────────────────────────────────


class TransferIntent(BaseModel):
    """Structured classification produced by the intent routing step."""

    intent: Literal["transfer_request", "conversational"] = Field(
        description=(
            "Choose 'transfer_request' when the user wants to transfer funds. "
            "Choose 'conversational' for questions or general conversation."
        )
    )
    source_account_id: str | None = Field(
        default=None,
        description="Source account ID (e.g. ACC-001). Required for transfer_request.",
    )
    destination_account_id: str | None = Field(
        default=None,
        description=(
            "Destination account ID (e.g. ACC-002 or EXT-SWIFT-123). "
            "Required for transfer_request."
        ),
    )
    amount: float | None = Field(
        default=None,
        description="Transfer amount as a positive number. Required for transfer_request.",
    )


# ── Step: analyze_intent ───────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def analyze_intent_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Classify the user message and extract transfer parameters in one model call.

    Why this exists:
    - the workflow must branch early: business transfer vs conversational fallback
    - transfer parameters (source, destination, amount) are extracted in the same
      structured call to avoid a second model round-trip before account loading

    How to use:
    - place as the entry node; declare "transfer_request" and "conversational"
      routes after it in the workflow

    Example:
    ```python
    # User: "Move 300 EUR from ACC-001 to EXT-WIRE-99"
    # → route_key="transfer_request", state gets source/destination/amount
    # User: "What accounts can I use?"
    # → route_key="conversational"
    ```
    """
    context.emit_status("analyze_intent", "Understanding your request.")
    return await intent_router_step(
        context,
        operation="analyze_intent",
        route_model=TransferIntent,
        system_prompt=_INTENT_SYSTEM_PROMPT,
        user_prompt=state.latest_user_text,
        fallback_output={
            "intent": "conversational",
            "source_account_id": None,
            "destination_account_id": None,
            "amount": None,
        },
        route_field="intent",
        state_update_builder=lambda d: {
            "source_account_id": d.source_account_id,
            "destination_account_id": d.destination_account_id,
            "transfer_amount": d.amount,
        },
    )


# ── Step: answer_conversationally ─────────────────────────────────────────────


@typed_node(BankTransferState)
async def answer_conversationally_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Answer a conversational question about transfers or the agent's capabilities.

    Why this exists:
    - the workflow must never dead-end on non-transfer requests; users should
      receive a helpful response explaining what the agent can do

    How to use:
    - place on the "conversational" branch with a direct edge to "finalize"
    """
    context.emit_status("answer", "Preparing response.")
    response = await model_text_step(
        context,
        operation="conversational_answer",
        system_prompt=_CONVERSATIONAL_SYSTEM_PROMPT,
        user_prompt=state.latest_user_text,
        fallback_text=(
            "I'm a bank transfer assistant. "
            "To start a transfer, say for example: "
            "'Transfer 200 EUR from ACC-001 to ACC-002'."
        ),
    )
    return StepResult(
        state_update={"final_text": response, "done_reason": "conversational"}
    )


# ── Step: load_account ────────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def load_account_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Validate transfer parameters and load source account details from bank-core.

    Why this exists:
    - all three transfer parameters must be present before any API call
    - the source account must exist before compliance or risk checks run

    How to use:
    - place after intent routing; route "ok" to check_kyc and "error" to finalize

    Example:
    ```python
    # Calls: get_account_details(account_id="ACC-001")
    # On success: stores source_account in state, routes "ok"
    # On failure: sets final_text, routes "error"
    ```
    """
    context.emit_status("load_account", "Loading account details.")

    if (
        not state.source_account_id
        or not state.destination_account_id
        or state.transfer_amount is None
    ):
        return StepResult(
            state_update={
                "final_text": (
                    "I need a source account, a destination account, and an amount. "
                    "Try: 'Transfer 200 EUR from ACC-001 to ACC-002'."
                ),
                "done_reason": "missing_transfer_params",
            },
            route_key="error",
        )

    raw = await context.invoke_runtime_tool(
        "get_account_details",
        {"account_id": state.source_account_id},
    )
    result = raw if isinstance(raw, dict) else {}

    if not result.get("ok"):
        error = result.get("error", "unknown error")
        return StepResult(
            state_update={
                "final_text": (
                    f"Could not load source account {state.source_account_id}: {error}"
                ),
                "done_reason": "account_not_found",
            },
            route_key="error",
        )

    account = result.get("account") or {}
    return StepResult(state_update={"source_account": account}, route_key="ok")


# ── Step: check_kyc ───────────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def check_kyc_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Check KYC compliance status for the source account via risk-guard.

    Why this exists:
    - transfers must be blocked when the account holder's KYC is expired or
      unknown before any money movement is attempted

    How to use:
    - place after load_account; route "valid" to evaluate_risk, "blocked" to finalize

    Example:
    ```python
    # ACC-001 → VALID  → route "valid"
    # ACC-002 → EXPIRED → route "blocked", final_text explains the block
    ```
    """
    context.emit_status("check_kyc", "Checking compliance status.")

    raw = await context.invoke_runtime_tool(
        "check_kyc_compliance",
        {"account_id": state.source_account_id},
    )
    result = raw if isinstance(raw, dict) else {}
    kyc_status = result.get("status", "EXPIRED")

    if kyc_status != "VALID":
        account = state.source_account or {}
        holder = account.get("holder_name", state.source_account_id)
        return StepResult(
            state_update={
                "final_text": (
                    f"Transfer blocked. KYC status for {holder} "
                    f"({state.source_account_id}) is {kyc_status}. "
                    "Please renew your identity verification before transferring funds."
                ),
                "done_reason": "kyc_blocked",
            },
            route_key="blocked",
        )

    return StepResult(route_key="valid")


# ── Step: evaluate_risk ───────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def evaluate_risk_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Evaluate transfer risk via risk-guard and decide whether HITL is needed.

    Why this exists:
    - high-risk transfers (score >= 50) must surface a warning and require
      explicit user confirmation before the transaction is prepared

    How to use:
    - place after check_kyc; route "low_risk" to prepare_transfer,
      "high_risk" to confirm_risk

    Risk scoring rules (from risk-guard mock):
    - amount > 2000 EUR: +40
    - external destination (EXT-*): +50
    - requires_validation when score >= 50
    """
    context.emit_status("evaluate_risk", "Evaluating transfer risk.")

    raw = await context.invoke_runtime_tool(
        "evaluate_transfer_risk",
        {
            "source_id": state.source_account_id,
            "destination_id": state.destination_account_id,
            "amount": state.transfer_amount,
        },
    )
    result = raw if isinstance(raw, dict) else {}

    risk_score = int(result.get("risk_score", 0))
    risk_reason = str(result.get("reason", ""))
    requires_validation = bool(result.get("requires_validation", False))

    state_update = {"risk_score": risk_score, "risk_reason": risk_reason}

    if requires_validation:
        return StepResult(state_update=state_update, route_key="high_risk")

    return StepResult(state_update=state_update, route_key="low_risk")


# ── Step: confirm_risk ────────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def confirm_risk_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    HITL gate #1 — warn the user about elevated risk and ask whether to proceed.

    Why this exists:
    - high-risk transfers must pause for explicit user consent before money
      is prepared; this is a compliance requirement in the sample workflow

    How to use:
    - place after evaluate_risk on the "high_risk" branch
    - route "confirmed" to prepare_transfer, "cancelled" to finalize

    Example:
    ```python
    # Graph pauses here, emits AwaitingHumanRuntimeEvent
    # User selects "yes_proceed" → resumes with route "confirmed"
    # User selects "no_cancel"   → sets final_text, routes "cancelled"
    ```
    """
    account = state.source_account or {}
    currency = account.get("currency", "EUR")

    question = (
        f"⚠️  This transfer has an elevated risk score ({state.risk_score}/100).\n"
        f"Reason: {state.risk_reason or 'see risk policy'}\n\n"
        f"Transfer details:\n"
        f"  From: {state.source_account_id}\n"
        f"  To:   {state.destination_account_id}\n"
        f"  Amount: {state.transfer_amount} {currency}\n\n"
        "Do you want to proceed despite the elevated risk?"
    )

    choice_id = await choice_step(
        context,
        stage="risk_confirmation",
        title="Risk Warning — Confirm Transfer",
        question=question,
        choices=[
            HumanChoiceOption(id="yes_proceed", label="Yes, proceed"),
            HumanChoiceOption(id="no_cancel", label="No, cancel"),
        ],
    )

    if choice_id != "yes_proceed":
        return StepResult(
            state_update={
                "final_text": "Transfer cancelled. You chose not to proceed with the elevated-risk transfer.",
                "done_reason": "risk_cancelled_by_user",
            },
            route_key="cancelled",
        )

    return StepResult(route_key="confirmed")


# ── Step: prepare_transfer ────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def prepare_transfer_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Create a PENDING_APPROVAL transaction in bank-core without moving money.

    Why this exists:
    - money must never move before the user confirms the exact transaction details
    - prepare_transfer creates a reversible pending record that commit_transfer
      executes only after the user confirms in the next HITL gate

    How to use:
    - place after evaluate_risk (low_risk branch) and confirm_risk (confirmed branch)
    - route "ready" to confirm_transfer, "rejected" to finalize

    Example:
    ```python
    # Calls: prepare_transfer(source_id, destination_id, amount)
    # On success: stores transaction_id, routes "ready"
    # On failure (e.g. insufficient funds): sets final_text, routes "rejected"
    ```
    """
    context.emit_status("prepare_transfer", "Preparing transfer.")

    raw = await context.invoke_runtime_tool(
        "prepare_transfer",
        {
            "source_id": state.source_account_id,
            "destination_id": state.destination_account_id,
            "amount": state.transfer_amount,
        },
    )
    result = raw if isinstance(raw, dict) else {}

    if not result.get("ok"):
        reason = result.get("reason") or result.get("error", "rejected by bank")
        available = result.get("available_balance")
        detail = (
            f" (available: {available} {result.get('currency', '')})"
            if available is not None
            else ""
        )
        return StepResult(
            state_update={
                "final_text": (
                    f"Transfer could not be prepared: {reason}{detail}. "
                    "No money has been moved."
                ),
                "done_reason": f"prepare_rejected_{reason}".lower(),
            },
            route_key="rejected",
        )

    transaction_id = str(result.get("transaction_id", ""))
    currency = str(result.get("currency", "EUR"))
    return StepResult(
        state_update={
            "transaction_id": transaction_id,
            "transaction_currency": currency,
        },
        route_key="ready",
    )


# ── Step: confirm_transfer ────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def confirm_transfer_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    HITL gate #2 — show full transaction details and ask for final confirmation.

    Why this exists:
    - the user must see the exact amount, source, and destination before money
      moves; this is the final safety gate in the transfer workflow

    How to use:
    - place after prepare_transfer on the "ready" branch
    - route "confirmed" to commit_transfer, "cancelled" to finalize

    Example:
    ```python
    # Graph pauses here, emits AwaitingHumanRuntimeEvent with transaction detail
    # User selects "confirm" → resumes, routes "confirmed"
    # User selects "cancel"  → sets final_text, routes "cancelled"
    ```
    """
    currency = state.transaction_currency or "EUR"
    account = state.source_account or {}
    holder = account.get("holder_name", state.source_account_id)
    available_balance = account.get("balance")
    balance_line = (
        f"\n  Balance after: ~{round(float(available_balance) - (state.transfer_amount or 0), 2)} {currency}"
        if isinstance(available_balance, (int, float))
        else ""
    )

    question = (
        f"Please confirm the following transfer:\n\n"
        f"  Transaction: {state.transaction_id}\n"
        f"  From:   {state.source_account_id} ({holder})\n"
        f"  To:     {state.destination_account_id}\n"
        f"  Amount: {state.transfer_amount} {currency}"
        f"{balance_line}\n\n"
        "This action will move money immediately. Do you confirm?"
    )

    choice_id = await choice_step(
        context,
        stage="transfer_confirmation",
        title="Confirm Transfer",
        question=question,
        choices=[
            HumanChoiceOption(id="confirm", label="Yes, confirm transfer"),
            HumanChoiceOption(id="cancel", label="No, cancel"),
        ],
    )

    if choice_id != "confirm":
        return StepResult(
            state_update={
                "final_text": (
                    f"Transfer {state.transaction_id} cancelled. No money has been moved."
                ),
                "done_reason": "transfer_cancelled_by_user",
            },
            route_key="cancelled",
        )

    return StepResult(route_key="confirmed")


# ── Step: commit_transfer ─────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def commit_transfer_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Execute the confirmed transfer via bank-core and report the outcome.

    Why this exists:
    - commit_transfer is the only step that moves money; it runs only after
      both HITL gates have been confirmed

    How to use:
    - place after confirm_transfer on the "confirmed" branch
    - use a direct edge to "finalize"

    Example:
    ```python
    # Calls: commit_transfer(transaction_id=state.transaction_id)
    # On success: writes final_text with balances, routes to finalize
    # On failure: writes final_text with error, routes to finalize
    ```
    """
    context.emit_status("commit_transfer", "Executing transfer.")

    raw = await context.invoke_runtime_tool(
        "commit_transfer",
        {"transaction_id": state.transaction_id},
    )
    result = raw if isinstance(raw, dict) else {}
    currency = state.transaction_currency or "EUR"

    if not result.get("ok"):
        reason = result.get("reason") or result.get("error", "unknown error")
        return StepResult(
            state_update={
                "final_text": (
                    f"Transfer {state.transaction_id} failed: {reason}. "
                    "Please check your balance and try again."
                ),
                "done_reason": f"commit_failed_{reason}".lower(),
            }
        )

    source_balance = result.get("source_balance")
    dest_balance = result.get("destination_balance")
    balance_lines: list[str] = []
    if source_balance is not None:
        balance_lines.append(
            f"  {state.source_account_id} new balance: {source_balance} {currency}"
        )
    if dest_balance is not None:
        balance_lines.append(
            f"  {state.destination_account_id} new balance: {dest_balance} {currency}"
        )
    balance_section = ("\n" + "\n".join(balance_lines)) if balance_lines else ""

    return StepResult(
        state_update={
            "final_text": (
                f"✅ Transfer {state.transaction_id} completed successfully.\n"
                f"  {state.transfer_amount} {currency} moved from "
                f"{state.source_account_id} to {state.destination_account_id}."
                f"{balance_section}"
            ),
            "done_reason": "transfer_completed",
        }
    )


# ── Step: finalize ────────────────────────────────────────────────────────────


@typed_node(BankTransferState)
async def finalize_step(
    state: BankTransferState,
    context: GraphNodeContext,
) -> GraphNodeResult:
    """
    Terminal step — keep existing final_text or set a generic fallback.

    Why this exists:
    - every branch must reach a consistent terminal node; this ensures a
      user-facing message is always set even when a branch omits it

    How to use:
    - register as the "finalize" node; all branches route here last
    """
    return _finalize_step(
        final_text=state.final_text,
        fallback_text="Transfer workflow completed.",
        done_reason=state.done_reason,
    )
