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
Graph definition for the Bank Transfer sample agent.

Purpose:
- demonstrate a complete v2 graph agent that uses two MCP servers (bank-core
  and risk-guard) and two HITL confirmation gates within one workflow
- show the intent_router_step pattern: the entry node classifies the request
  and branches to either the business workflow or a conversational fallback

Workflow overview:
    analyze_intent
     ├─ transfer_request ──► load_account
     │                          ├─ ok  ──► check_kyc
     │                          │            ├─ valid   ──► evaluate_risk
     │                          │            │               ├─ low_risk ──► prepare_transfer
     │                          │            │               └─ high_risk ──► confirm_risk [HITL #1]
     │                          │            │                               ├─ confirmed ──► prepare_transfer
     │                          │            │                               └─ cancelled ──► finalize
     │                          │            │                    prepare_transfer
     │                          │            │                     ├─ ready    ──► confirm_transfer [HITL #2]
     │                          │            │                     │               ├─ confirmed ──► commit_transfer ──► finalize
     │                          │            │                     │               └─ cancelled ──► finalize
     │                          │            │                     └─ rejected ──► finalize
     │                          │            └─ blocked ──► finalize
     │                          └─ error  ──► finalize
     └─ conversational ─────► answer_conversationally ──► finalize

MCP servers required:
- bank-core-mcp  (port 9801 in development): get_account_details,
  prepare_transfer, commit_transfer
- risk-guard-mcp (port 9802 in development): evaluate_transfer_risk,
  check_kyc_compliance
"""

from __future__ import annotations

from agentic_backend.core.agents.agent_spec import MCPServerRef
from agentic_backend.core.agents.v2.graph.authoring import GraphAgent, GraphWorkflow

from .graph_state import BankTransferInput, BankTransferState
from .graph_steps import (
    analyze_intent_step,
    answer_conversationally_step,
    check_kyc_step,
    commit_transfer_step,
    confirm_risk_step,
    confirm_transfer_step,
    evaluate_risk_step,
    finalize_step,
    load_account_step,
    prepare_transfer_step,
)

# MCP server IDs as declared in mcp_catalog.yaml.
MCP_SERVER_BANK_CORE = "mcp-bank-core-demo"
MCP_SERVER_RISK_GUARD = "mcp-risk-guard-demo"


class BankTransferGraphAgent(GraphAgent):
    """
    Sample v2 graph agent that executes a bank transfer through two MCP servers
    and two human-in-the-loop confirmation gates.

    Use this agent as a reference when building workflow agents that:
    - need to call external MCP tools (not Fred native tools)
    - require intent routing at the entry node
    - must pause execution for user confirmation before committing an action

    Change graph_agent.py when the business sequence changes.
    Change graph_state.py when the data model changes.
    Change graph_steps.py when step behaviour changes.
    """

    agent_id: str = "sample.bank_transfer.graph"
    role: str = "Bank Transfer Assistant"
    description: str = (
        "Sample graph agent that validates KYC compliance, evaluates transfer risk, "
        "and executes a fund transfer through two HITL confirmation gates using the "
        "bank-core and risk-guard MCP servers."
    )
    tags: tuple[str, ...] = ("bank", "transfer", "graph", "sample", "hitl", "mcp", "v2")

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_BANK_CORE),
        MCPServerRef(id=MCP_SERVER_RISK_GUARD),
    )

    input_schema = BankTransferInput
    state_schema = BankTransferState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="analyze_intent",
        nodes={
            "analyze_intent": analyze_intent_step,
            "answer_conversationally": answer_conversationally_step,
            "load_account": load_account_step,
            "check_kyc": check_kyc_step,
            "evaluate_risk": evaluate_risk_step,
            "confirm_risk": confirm_risk_step,
            "prepare_transfer": prepare_transfer_step,
            "confirm_transfer": confirm_transfer_step,
            "commit_transfer": commit_transfer_step,
            "finalize": finalize_step,
        },
        edges={
            "answer_conversationally": "finalize",
            "commit_transfer": "finalize",
        },
        routes={
            "analyze_intent": {
                "transfer_request": "load_account",
                "conversational": "answer_conversationally",
            },
            "load_account": {
                "ok": "check_kyc",
                "error": "finalize",
            },
            "check_kyc": {
                "valid": "evaluate_risk",
                "blocked": "finalize",
            },
            "evaluate_risk": {
                "low_risk": "prepare_transfer",
                "high_risk": "confirm_risk",
            },
            "confirm_risk": {
                "confirmed": "prepare_transfer",
                "cancelled": "finalize",
            },
            "prepare_transfer": {
                "ready": "confirm_transfer",
                "rejected": "finalize",
            },
            "confirm_transfer": {
                "confirmed": "commit_transfer",
                "cancelled": "finalize",
            },
        },
    )
