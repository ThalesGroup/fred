---
schema: 1
title: "Handle HITL resume conflicts and rejected cancellations"
impact: none
configuration: none
configuration_reason: "Runtime history availability, frontend notifications, regression tests, and CI scanner installation change; no deployment configuration keys or defaults change."
no_action_reason: "The optional history availability field is additive; existing checkpoints and database schema remain unchanged. Compatible runtime and frontend images are delivered through normal deployment."
---
## Applicability

Weaver deployments using human-input requests in agent conversations. Port source:
Swift #3431 at `059ae1c91b959692f6a0fb61ddc9824c67c90355`.

## Prerequisites

Use the runtime and frontend images from this release for the complete behavior.
History reads retain the existing person, conversation and space checks; the
availability annotation is not an authorization to resume a turn.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally. The optional `resume_status` on unanswered human-input history
parts distinguishes `pending`, `unavailable` and `unknown`. It is computed at read
time from existing execution state; no checkpoint or stored history is rewritten
to annotate a read. The server still decides whether an actual resume is accepted.

The Docker image workflow installs the pinned Trivy scanner from its official
GitHub archive, verifies its SHA-256 and reuses it for the existing scans. The
Weaver image matrix, scan scope and reporting policy are preserved; no deployment
credential or configuration change is required.
The shared installer's path is also included in the Knowledge Flow image inputs,
so a later scanner-only edit still exercises those consumers in pull-request CI.

## Validation

Submit an obsolete HITL card and check that the message explains that no answer was applied.
Reject a resume before acceptance and verify that the card remains answerable and
its tools are not falsely displayed as cancelled. Reload a consumed question and
verify it is readable without response controls; a genuinely pending question
remains answerable. Navigate to an admin page while a turn continues and verify
its human-input toast opens the originating conversation.
Check the same history with an unauthorized account or space: the availability
annotation must not make it readable. Record the deployed image references when
performing this reception. The merge's local checks do not establish k3d or
integration-platform validation.

## Rollback

Roll back runtime and frontend images coherently using the normal procedure.
This change introduces no data migration or checkpoint rewrite.

## Limitations

This change does not recover erased checkpoints or replay an already consumed
approval, reconnect streaming, or persist disconnected-turn history. Older
runtimes without the availability annotation retain legacy reconstruction, which
can still show response controls. An explicit `unknown` annotation instead shows
the request read-only with a retry action; `unavailable` is read-only without that
action. The hint is not a reservation: a request can become unavailable between
history loading and the actual resume admission.
The old-checkpoint regression uses SQLite and a fresh graph instance; it is not
a live multi-pod deployment test. No provider inference or deployment is performed
as part of the merge checks.
