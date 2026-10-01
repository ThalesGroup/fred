---
schema: 1
title: "Remove the ingestion submission fallback queue"
impact: minor
configuration: none
configuration_reason: "The configured scheduler is unchanged; Fred no longer persists or redelivers failed ingestion submissions."
---
## Applicability

Knowledge-flow deployments with the `kf_ingestion_submission` table.

## Prerequisites

Stop new ingestion requests. Resolve all rows in `kf_ingestion_submission` with the previous deployment before upgrading. Inspect the corresponding Temporal executions and task states; do not discard accepted requests or mark running executions failed. The migration refuses a nonempty queue.

## Configuration

No configuration changes. The explicitly selected local memory scheduler remains supported; Temporal failures never switch to it.

## Upgrade

Drain the legacy queue, stop old knowledge-flow processes, then run the normal Alembic upgrade and deploy the new code. Do not run old writers against the schema after the queue table is removed. The existing task tables and document admission uniqueness constraint remain.

## Validation

A successful ingestion starts normally. A scheduler start error reaches the upload progress stream as a failure, with an unconfirmed-start message and execution identifier. Fred must not automatically resubmit the batch. Confirm the queue table no longer exists.

## Rollback

Stop new processes and downgrade the queue-removal revision before restoring the previous code. Downgrade recreates an empty queue; it does not reconstruct submission payloads or schedule previously unsuccessful requests.

## Limitations

An initial Temporal connection failure is returned before document task admission. Once a client exists, a start error does not prove Temporal rejected the request. Existing document task bindings remain nonterminal to avoid allowing a duplicate execution. If no workflow was created, or Temporal cannot be queried, those tasks require operator diagnosis and explicit resolution before a new admission can proceed; Fred adds no recovery or automatic replay mechanism. The HTTP upload stream may already be open: its existing FAILED progress event communicates the error rather than changing the HTTP status after streaming begins.
