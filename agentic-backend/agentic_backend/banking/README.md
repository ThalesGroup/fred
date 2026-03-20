# Bank Transfer Workflow Agent (V1)

This module is a compact reference for building a **transactional agent** in Fred.
It is intentionally small, but it demonstrates the core architectural pattern needed
for reliable business workflows.

## What This Agent Demonstrates

- LLM-assisted intent/parameter understanding (`source_id`, `destination_id`, `amount`)
- Deterministic workflow orchestration for business-critical steps
- Explicit state machine across turns (including short replies like `yes` / `cancel`)
- Real tool execution through MCP servers
- Human-in-the-loop confirmation before irreversible action (`commit_transfer`)

## Why This Is Good Agent Design

The implementation separates responsibilities clearly:

- **LLM**: understand user request, normalize input, generate user-facing text
- **Workflow graph**: enforce allowed transitions and step order
- **State**: persist transaction context safely across turns
- **MCP tools**: execute business operations and return source-of-truth data
- **HITL**: explicit user approval gate before money movement

This split is the key to robustness and auditability.

## Why “Simple ReAct + Tools” Is Not Enough Here

A generic ReAct loop is strong for exploration and ad-hoc tasks, but transactional
workflows need strict guarantees:

- `prepare_transfer` must happen before `commit_transfer`
- `commit_transfer` must never happen without explicit confirmation
- short user replies must be interpreted against a known pending state
- failures (e.g., insufficient funds) must stop the flow deterministically

Without explicit workflow/state constraints, these guarantees become fragile.

## Correct Role of the LLM in This Workflow

Use the model for:

- intent extraction and entity extraction
- linguistic normalization of user replies
- concise, clear response phrasing

Do **not** use the model for:

- deciding that money moved without tool evidence
- inventing balances, transaction IDs, or statuses
- replacing explicit workflow transitions with implicit memory

## Canonical Transaction Pattern

This agent follows the canonical pattern:

1. Parse + validate transfer request
2. Evaluate risk (`evaluate_transfer_risk`)
3. Prepare transfer (`prepare_transfer`) — no money moved yet
4. Request explicit confirmation (HITL)
5. Commit transfer (`commit_transfer`) **only if confirmed**
6. Otherwise cancel with no debit

This `prepare -> confirm -> commit` split is the core safety design.

## Practical Safety Invariants

The code enforces these invariants:

- no commit without explicit confirmation
- no confirmation prompt if preparation failed
- no commit after cancellation
- no fabricated transaction outcome without MCP result
- clear user messaging on what is done vs not done yet

## MCP Dependencies

This workflow uses two MCP servers:

- `mcp-risk-guard-demo`: risk advisory (`evaluate_transfer_risk`)
- `mcp-bank-core-demo`: transfer preparation/commit (`prepare_transfer`, `commit_transfer`)

Both are required for the end-to-end demo behavior.
