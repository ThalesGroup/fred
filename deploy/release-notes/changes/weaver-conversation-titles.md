---
schema: 1
title: "Weaver conversation titles and organization model choice"
impact: minor
configuration: none
configuration_reason: "The optional title choice is organization data in the existing model policy; no new deployment setting or chart value is introduced. Existing source credential provisioning still applies."
---
## Applicability

Weaver deployments upgrading Control Plane, managed Python agent pods and frontend.
The embedded Rust Ralph path is included. This is not a Swift database migration.

## Prerequisites

Use the normal backup and schema-owner procedure. Every title source must be
permitted in its organization and have matching existing workload credential
provisioning in each consuming Python/Rust runtime. No real provider or existing
deployment database was used for this lot's focused tests.

## Configuration

No new deployment configuration key. Each organization Owner may optionally choose
its title model in Models settings. With no choice, the offer admitted for the
answer is used with separate bounded options. An unusable dedicated choice leaves
the initial title; there is no fallback to an unpermitted offer. The technical
platform Admin does not gain model-policy rights.

## Upgrade

Drain active turns and stop application writes before the coordinated rollout.
Run `control-plane init-schema` with the normal schema-owner identity to apply
SQLx migration `0004_conversation_titles.sql`; normal server startup checks schema
freshness and does not run migrations. Deploy matching Control Plane, SDK/runtime
and frontend versions, then resume traffic. Old clients must not write model
policies: complete replacement now requires nullable `title`. Managed Python
execution now POSTs runtime admission; deploying it before the new Control Plane
would reject execution. Do not leave older runtimes creating sessions while the
new server records first-attempt eligibility they cannot consume.

Existing conversations remain ineligible and keep their titles and history. No
backfill or mass generation is required. New conversations need no optional setting
to begin generating titles under their already-admitted model governance.

## Validation

On a newly created conversation, send a first message and observe its initial title
followed by a brief title. Reload history; verify the title persists. Set an optional
permitted title model as organization Owner and reload Models. Verify a manual
rename during generation wins, including unchanged text, and a removed dedicated
offer preserves the initial title while the answer completes. These are deployment
acceptance checks to perform; this lot has not certified k3d/integration behavior.

## Rollback

Drain turns and roll back the application set coherently. An older Control Plane
binary rejects the newer SQLx migration history. There is no supplied down migration:
restore a matching pre-upgrade database backup together with the prior binaries,
using the established recovery procedure and accounting for writes since backup.
Do not remove migration receipts or alter the schema manually to bypass startup.

## Limitations

Only managed Python conversations and embedded Rust Ralph are covered; standalone
SDK calls without session admission do not persist titles. One attempt per new
session, no retry after failure. Input is bounded to 600 characters, target 3–8
words, output to 80 characters; model/cleanup failures preserve the initial title.
The extra call uses normal inference observation and usage reporting. Usage that
the provider never returned on cancellation is not estimated. No latency, cost or
provider compatibility claim is established by mock-based tests.
