---
schema: 1
title: "Delegation hardening: account status per request, renamed denial causes, bounded audit and logs"
impact: minor
configuration: local
configuration_reason: "Only the error message that rejects a removed OpenFGA setting in libs/fred-pod/fred_pod/security/structure.py changes; no configuration key, default or chart value changes, so production values are unaffected."
---

## Applicability

Existing Fred deployments upgrading to this release, and external agent pods or first-party application backends built on the published Python libraries. With both delegation switches off, the operational change is limited to the `rebac_denied` audit event; everything else applies only with a delegation switch on.

The four Python libraries (`fred-pod`, `fred-core`, `fred-sdk`, `fred-runtime`) are prepared for coordinated publication as 4.4.0, with aligned internal dependency minimums. Publish in the documented order: pod, core, SDK, then runtime.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. Activating delegation still follows the delegated execution activation note.

## Configuration

No configuration changes are required. No key, default or chart value changes, and the authorization model keeps only the `suspended` relation.

## Upgrade

Deploy Fred normally, then:

- If a SIEM or log rule reads `user_id`, `team_id` or `agent_instance_id` from `rebac_denied`, update it: the event now carries only its outcome and reason.
- Upgrade external consumers of the Python libraries to 4.4.0 together. In `fred_core`, `StandingAuthorizationError` becomes `AccountStatusError`, and `resolve_request_principal` and `resolve_delegated_principal` are no longer exported; a subject is established through the shared user dependency. On `RebacEngine`, `enforces_standing`, `require_user_standing` and `validate_standing_model` become `requires_active_accounts`, `require_active_account` and `validate_account_status_model`, and `grant_default_standing`, `mark_standing_seed_ready`, `is_standing_seed_ready` and `remove_user_standing` are removed.

## Validation

With both delegation switches off:

- A managed agent run refused for a missing team permission returns 403 with `X-Fred-Denial-Cause: permission_refused` and writes one `rebac_denied` audit event carrying only outcome `rejected` and reason `permission_refused`.
- No request or tool call reads account status, and Knowledge Flow keeps its `http` request and response lines.

With a delegation switch on:

- Start a receiving service before the control plane and confirm it starts; a person deleted through the platform is refused on their next request.
- Each authenticated request, from a signed-in person, a person named by a grant or a service identity, makes one account status check before its route runs. A suspended subject receives 403 with `X-Fred-Denial-Cause: account_suspended` and one `authorization.account.refused` audit event with reason `account_suspended`. With OpenFGA unreachable, every authenticated request other than a tool mount's initialization and tool listing returns 503 with `X-Fred-Denial-Cause: account_status_unavailable` and the same event with reason `account_status_unavailable`.
- A managed run refused for a missing team permission writes the same bounded `rebac_denied` event; a refused or unavailable account status writes none.
- Each request produces one access line carrying only a neutral event, outcome, method and status; Knowledge Flow's own `http` logger writes nothing.
- A tool mount only authenticates: initializing and listing tools make no account status check, and each mounted tool call makes one, in the route that serves it.
- A delegated run checks account status before every tool call; a run without delegated credentials makes no per-tool account status check.
- A workload presenting a grant receives 403 `requires_own_credential` on agent-instance enrollment and update, with or without asset uploads, on session, bulk session and attachment deletion, and on knowledge-base instance creation and deletion. Managed execution preparation for a person named by a grant succeeds and returns no capability chat controls.
- A grant whose `person`, `run` or `agent` value contains `*` or `#` names nobody: the receiver audits `delegation.grant.rejected` with reason `invalid_parameters` and treats the caller as itself. With `act_for_people` on, admitting such a run returns 403 `delegation_unavailable` and keeps no run record.
- Each delegated onward request records one `fred_auth_m2m_acquire_seconds` sample, plus one per 401 renewal; the retry reuses the renewed token. A failed acquisition ends the run with `delegation_unavailable` and writes one log line naming only the error type.
- A team-wiki call refused under delegation ends the run with `authority_lost`, and a failed workload-token acquisition ends it with `delegation_unavailable`, instead of returning tool text or an unavailable-wiki prompt block.
- With delegated execution on, run the admin session-expiry self-test; it passes and reports that the agent held no person credential.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

- With a delegation switch on, a service serves authenticated requests only while its OpenFGA store answers: during an outage every authenticated request, login bootstrap and profile included, returns 503 `account_status_unavailable`, with no exemption for service identities; a tool mount still initializes and lists tools, and each tool call is refused. A first-party application backend gets this check's engine from the shared ReBAC SDK factory; without it, every authenticated request is answered the same way.
- The frontend has no specific handling for `account_suspended` or `account_status_unavailable`: it shows them as any other 403 or 503 response.
- A suspension applies from the person's next request. A request that has passed its check completes, and background work it admitted finishes; a delegated run rechecks account status before every tool call. A suspended person can still initialize a tool session and list tools; each tool call is refused.
- The denial causes `account_suspended` and `account_status_unavailable` and the audit event `authorization.account.refused` replace the names delegation used before its first release. This is a contract change for unreleased delegation: SIEM and log-pipeline rules prepared for delegation must match the new names.
- `rebac_denied` carries only its outcome and reason in either setting; unlike the last release, it names no user, team or agent instance.
- An application acting for a person through a grant cannot enroll or update agent instances, delete sessions or attachments, or create or delete knowledge-base instances: those operations require the person's own credential. Managed execution preparation for such a person returns no capability chat controls.
- With `act_for_people` on, a person whose identifier contains `*` or `#` cannot start an agent run.
- OpenFGA accepts no `:` inside an identifier, so with a delegation switch on, a person whose subject identifier contains one, such as a user federated without import, is refused on every authenticated request with 503 `account_status_unavailable`, although a grant may name them.
- A refused team-wiki call ends the whole delegated run instead of letting the model continue without the wiki. The team-wiki capability package requires `fred-sdk` 4.2.0 or later.
- With a delegation switch on, log queries built on Knowledge Flow's `http` logger find no lines; use the access line and the `api.request_latency_ms` KPI.

Automated tests cover this behaviour; it has not been exercised in a production deployment.
