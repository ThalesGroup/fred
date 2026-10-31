---
name: fred-contract-reviewer
description: Review FRED cross-stack contract consistency. Use when reviewing a FRED change that touches or depends on backend Pydantic models, FastAPI routes, OpenAPI generation, generated frontend RTK clients, TypeScript types, Redux state, task/event schemas, permissions, or UI consumers. Especially use before accepting changes that span multiple backends and the frontend.
---

## Shared team policy

Read the active checkout's `AGENTS.md`, applicable nested instructions and
`fred-reconstruction-method` for domain/persistence work. Use that checkout's
arc42 and code; never load policy from a hardcoded personal Fred directory.
Apply the reuse, replacement and production-code reduction acceptance rule.
This is a bounded review unless fixes are requested. Propose verification needs
without automatically starting tests, load campaigns or independent agents.

# FRED Contract Reviewer

Review contracts as an evidence exercise, not as a style pass. The goal is to prove that every layer tells the same story.

## Required Workflow

1. Read the repo instructions first: root `AGENTS.md`, then relevant nested instructions.
2. Identify the claimed feature boundary and list all layers it crosses:
   - business invariant, SQL schema and transaction owner
   - backend domain model (Rust or Python)
   - API route and response model
   - OpenAPI JSON
   - generated frontend client/type
   - frontend domain type or Redux state
   - UI consumer
   - authorization scope
   - tests
3. Build an evidence matrix. Use file and line references for every claim.
4. Treat missing evidence as a finding. Do not infer that a generated client was refreshed unless the diff or files prove it.
5. Prefer convergence findings over local fixes. If two layers define the same concept differently, call out the contract split.

## Evidence Matrix

Report this table in the review when applicable:

| Contract item | Backend source | API/OpenAPI | Generated TS | Frontend state/UI | Tests | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `<field/event/role/state>` | file:line | file:line | file:line | file:line | file:line | OK / Missing / Drift |

## Blocking Questions

Check these before lower-level comments:

- Is there exactly one canonical name for each enum, kind, state, permission, and target type?
- If an API model changed, was the generated frontend client regenerated?
- If frontend code imports generated types from one backend, can it safely represent objects produced by the other backend?
- Does the list endpoint enforce the same visibility model as the detail, stream, cancel, and mutation endpoints?
- Does the UI route to the backend that actually owns the resource?
- Is the frontend consuming canonical server state rather than guessing or re-deriving business status?
- Is there a reload/rehydration path that reconstructs the same state after a page refresh?

## Findings Standard

Lead with bugs and risks, ordered by severity. Each finding must include:

- impact in user or operator terms
- exact file/line references
- the contract invariant being violated
- what proof or test is missing

Avoid broad praise. If no issue is found, say which invariants were proven and which remain untested.

## Minimum Test Expectations

For cross-stack changes, expect at least one of:

- backend model/serialization round-trip test
- OpenAPI/generated-client refresh evidence
- frontend type/reducer/component test using generated shape
- authorization parity test across list/detail/stream/mutate endpoints
- integration test proving backend response drives the UI state without local guessing
