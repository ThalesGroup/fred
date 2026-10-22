---
schema: 1
title: "Restore correlated exception tracebacks and separate duplicate filtering"
impact: minor
configuration: none
configuration_reason: "Shared Python logging behavior changes; no configuration keys, defaults or chart values change."
after: [3211-compose-chart-registrations]
---

## Applicability

Fred Python APIs and workers using the updated shared `fred-core` library, including external library consumers. Request-boundary diagnostics apply to APIs using `RequestLoggingFastAPI`.

## Prerequisites

Review deployment log rules that match the former fixed server diagnostic message or assume request exception traces use the `uvicorn.error` logger.

## Configuration

No configuration changes are required. Existing `app.log_format` selects JSON or readable stdout. Exception visibility is independent of either delegation switch.

## Upgrade

Deploy the updated backend/worker images normally. Update affected log rules to match `fred_core.logs.http` for uncaught request exception diagnostics and `http` for HTTP completion. Both retain the same available admitted user/session/agent/team and request/correlation references. Unreported server failures still use their server logger.

Ordinary exception text and traceback frames now appear in stdout. Known token query values and free-access/join-link secrets are redacted, including in exception causes. This replaces blanket suppression with targeted redaction; it does not guarantee removal of arbitrary sensitive text embedded in exceptions. Apply the deployment's log access and retention policy to that diagnostic output. Audit and dependency restrictions are unchanged.

## Validation

Trigger an uncaught synthetic request failure in a non-production environment. Filter by its response's request/correlation IDs and admitted business references: one ERROR from `fred_core.logs.http` must contain the traceback, and one ERROR from `http` must contain status 500, route, duration and outcome. There must be no duplicate Uvicorn exception event for that failure. Verify that an unreported server error remains visible and a known URL token is redacted even when present only in an exception cause.

The local regression suite exercises the actual Knowledge Flow factory and Uvicorn over a Unix socket in all three delegation settings. Live GKE collection remains a deployment validation step.

## Rollback

Deploy the previous shared-library/backend/worker images and restore any rules changed for the new logger/messages. No data migration is involved. Rollback restores the previous traceback suppression and its diagnostic limitations.

## Limitations

This change does not recover old tracebacks, change the optional generic log store, deduplicate arbitrary application log-and-rethrow code, or add HTTP business context to startup, shutdown or WebSocket failures. Identity that has not been admitted/resolved is not invented. Existing runtime support-reference diagnostics remain separate.
