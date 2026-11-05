---
schema: 1
title: "Weaver: complete Python conversation erasure with durable write ownership"
impact: minor
configuration: local
configuration_reason: "The local k3d profile overrides the existing lifecycle sweep interval to PT1M for retesting. Production defaults and configuration keys are unchanged. Mandatory migration and storage/IAM checks are described below; no user grants are added."
after:
  - weaver-conversation-persistence-and-purge
---
## Applicability

Weaver installations using Python/ReAct, Deep conversation files, writable
documents or PPT outputs, including receipts already blocked with
`session_purge_unavailable`. This implements their effective deletion through the
existing Control Plane lifecycle. It does not migrate Swift conversation content.
The changes are locally validated; this note is not evidence of a deployment.

## Prerequisites

Back up Control Plane, runtime and capability SQL and their matching object stores
together. All conversation SQL must share one PostgreSQL database: CP owns
`control_plane.session_metadata`, runtime/capabilities own their private tables.
The normal bootstrap and CP migration grant runtime only `USAGE` on the CP schema
and `REFERENCES(session_id)` on the root, never SELECT or mutation privileges.

Every historical session identifier must be a UUID with an existing CP root.
For derived checkpoint threads, the UUID is the prefix before `:`. Migrations fail
atomically on malformed identities or orphaned content; they neither invent roots
nor silently delete data. Diagnose and resolve such legacy content through an
explicit recovery decision before retrying the supported migration command.
Audit existing `conversations/{id}/` object prefixes before activation as well:
legacy code accepted UUID aliases (uppercase/compact spellings). New filesystem producers
canonicalize the UUID, but this does not rename previously written object keys.
Consolidate any historical aliases into their canonical conversation prefix
through an explicit storage recovery before resuming cleanup; do not assume that
SQL migration scans or repairs a bucket. Orphaned prefixes likewise require an
explicit ownership decision.

Uninstalled capabilities can leave data: writable-document's migration remains
required if its table exists, even when its plugin is no longer installed.

Stop and drain **all old producers** before activation, including CP uploads, KF
processing/visibility work and Python runtime writes/conversions. Stopping a pod
alone does not prove an already dispatched remote write has ended. Establish
storage-side quiescence of old requests and multipart uploads as part of this
transition. The new journal cannot retroactively describe old network requests.
Do not enable cleanup during a mixed old/new rollout.

## Configuration

The local k3d profile sets `scheduler.lifecycle.sweep_interval: PT1M` for retesting;
its retention is already `PT1M`. Production defaults retain `PT10M`. The CP worker
reconciles the existing Temporal schedule on startup after configuration is applied.
Existing lifecycle policies, runtime sources, public history routing and M2M
configuration are reused; no parallel worker is introduced.

The runtime purge request uses the configured **private** runtime URL and existing
CP M2M token. CP accepts `manage_platform` for its own verified service account,
matching the configured client ID and issuer, only without person/run/agent
assertions. Other workloads and users keep their existing authorization and
consent rules. No user or delegated caller inherits this service exception. Its scope is the
existing `manage_platform` decision for that workload identity, not an invented
purge-only permission. Other consumers of that decision still enforce their own
authentication guards; other platform permissions and CP business routes are not
implicitly granted. The new runtime purge dependency admits this service identity
without borrowing a person's consent.

All replicas must use the same runtime object namespace across restarts. Managed
PostgreSQL runtimes reject the local filesystem backend because it cannot establish
shared ownership across pods. Standalone SQLite SDK use retains local filesystem
support but cannot certify Weaver conversation erasure.

Runtime Minio/S3 buckets must never have versioning enabled; grant their workload
`GetBucketVersioning` in addition to the existing object permissions. GCS requires
bucket metadata inspection (`storage.buckets.get`) and object listing/deletion;
versioning, soft-delete retention and bucket retention must be disabled. Startup
and purge reject storage configurations that cannot establish physical deletion.
These are service/storage permissions, not application user grants. CP original
and derived buckets retain their existing corresponding checks.

## Upgrade

1. Keep lifecycle cleanup paused through the normal configuration/deployment
   procedure while performing the prerequisite drain and coordinated backup.
2. Apply CP migrations 0011–0013 with the normal `initialize-schema` command.
   Never edit migrations 0001–0010 or existing SQLx checksums.
3. Run the normal runtime migration command, `python -m fred_runtime migrate`,
   with the runtime role/schema and all applicable capability migrations. New
   runtime revisions adopt checkpoint tables, add validated cascading ownership
   and create the durable filesystem manifest. Writable-document adds the same
   root FK. PostgreSQL startup verifies these constraints; it no longer creates
   checkpoint tables implicitly.
4. Replace all CP, KF and runtime producers with compatible binaries and verify
   shared storage settings and M2M authorization. Keep any uncertain old storage
   operation under investigation; a missing response is not success.
5. Resume the existing lifecycle worker. Past-due blocked receipts are selected
   automatically. No SQL status reset or manual deletion is required.

No deployment or push is performed by this change itself.

## Validation

The post-deployment UI journey is intentionally ordinary:

1. Create two Python conversations in one space. In the first, send messages,
   attach a document and wait for indexing; create a writable document and a PPT
   with PDF preview. With a Deep agent, also create a scratchpad/file. Verify the
   exported files download and the second conversation remains usable.
2. Start another turn or upload in the first conversation, then delete it. It must
   disappear immediately, remain absent after refresh, and reject history,
   downloads, new runs and resumptions. Existing accepted work may finish, but
   must not recreate content after effective purge.
3. After the configured deadline and sweep, inspect its deletion receipt through
   the existing lifecycle status path. `completed` requires originals, all
   derivatives, runtime files and SQL content to be removed. Confirm the second
   conversation's messages, attachments and exports are unchanged.
4. On a disposable environment, interrupt cleanup or make storage/runtime
   temporarily unavailable. The receipt must remain pending/retrying/blocked and
   complete after recovery when results are known. Repeated sweeps must be harmless.
   A deliberately unacknowledged write must remain explicitly blocked.
5. Delete a team/space containing Python and Ralph conversations. Their child
   receipts must complete before the parent; repeat through an organization.
6. Check personal and organizational usage/KPI views after session, agent and space
   metadata deletion. Previously received usage and a late finishing run's report
   must remain readable under the existing KPI permissions.

Local automated evidence and the inventory/ownership decisions are recorded in the
conversation coordination PLAN. Tests cover both orders of the SQL write/delete
race, real PostgreSQL roles/cascades and rollback, cancelled file writes, uncertain
writes across engine restart, late admitted uploads, generation writes, repeated
calls, isolation, parental progress, M2M identity and late usage attribution.
Service-specific live GCS behavior and a complete deployed UI journey still require
verification in the target environment; mocked transports are not presented as
live-provider or deployment evidence. GCS must also permit the post-delete
soft-deleted-object inventory: providers returning 400/unsupported for that check
remain explicitly unavailable rather than being interpreted as empty. Disabling
a GCS soft-delete policy does not remove historical soft-deleted objects.
See the provider's [soft-delete behavior](https://docs.cloud.google.com/storage/docs/disable-soft-delete)
and [object-list contract](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/list).

## Rollback

Effective deletion is irreversible. Restoring only CP SQL without its matching
runtime/capability/object snapshot breaks ownership and is unsupported.
PostgreSQL ownership migrations deliberately refuse downgrade: removing their FKs
would reopen the write-after-purge race. Stop cleanup and producers before any
coordinated recovery; do not restore old writing binaries into the new lifecycle.

## Limitations

An acknowledged external write and an unknown result are different facts. A crash,
lost response or unconfirmed local workspace cleanup leaves its durable intent
pending; there is no timeout that silently turns it into success. Late acknowledgements
allow normal automatic resumption. If no producer can certify the outcome, the
receipt and its parents remain blocked pending an explicit operational recovery
procedure; this change supplies no unsafe force-complete or SQL workaround.

Retained receipts contain the minimal attribution needed for late usage reports.
The usage delivery mechanism remains best effort: a runtime crash or outage that
loses an unreported consumption event is not repaired by a new accounting outbox.
Independent web-research security retention is unchanged. Memory already held by
an admitted process, external user downloads, storage backups and provider backup
retention are outside the live conversation-content deletion transaction.
