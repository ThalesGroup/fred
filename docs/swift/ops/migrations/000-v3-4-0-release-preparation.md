---
schema: 1
title: "Staged v3.4.0 upgrade and rollback"
impact: minor
configuration: none
configuration_reason: "Release preparation adds user-facing notes and consolidates existing migration procedures; it introduces no additional configuration setting."
---

## Applicability

Upgrade from Fred v3.3.0 to v3.4.0 using the paired code and chart release.
This release-preparation contribution consolidates the operational changes below;
its minor impact comes from those existing procedures, not an additional migration.
Use this sequence once, then use the following feature sections for configuration,
validation and limitations. Their database revisions are applied together, not as
separate deployments. Python package publication is a separate maintainer workflow.

## Prerequisites

Back up the shared PostgreSQL database and retain the previous chart, values,
images and OpenFGA model identifier. Plan database migrations through the normal
deployment procedure; large installations may need a database migration window
for the agent-name backfill and unique index. Admission readers must use the same
PostgreSQL authority. Filtering will be activated later, after all readers are
updated, so no synchronized backend cutover is needed for that activation.
Prepare a verified administrator account and a recovery path before activation.
Review the agent-name collision query below before migration: duplicate names
will be renamed, and schema rollback does not restore their former names.

## Configuration

Reconcile private overlays against the new Fred chart values, including worker
values separately from API values. `configuration_prod.yaml` is for local Compose.
Prepare JSON log parsers for APIs, workers and frontend; review access and retention
for diagnostic identity references and native nginx text errors. Remove obsolete
admission or web-egress settings only if an earlier draft introduced them.

If using a custom `FRED_PLATFORM_PROMPT_FILE`, merge the shipped skill-use and
precedence guidance before restarting agents. Rename saved prompt commands named
`skill` if their slash shortcut must remain available. Neither step enables skills.

## Upgrade

### Required staged deployment

1. Publish and select the compatible OpenFGA model containing
   `organization.suspended` before starting any updated reader, including on
   deployments without delegation. This can be prepared ahead of the application
   rollout. Keep ordinary authentication and resource authorization enabled.
2. Run the release's database migrations through the normal deployment process
   before starting updated applications. Chart migration hooks default to disabled:
   explicitly enable the deployment's migration jobs or run the equivalent documented migration command
   for each backend; API startup alone does not migrate the database. For the
   runtime, the command is `python -m fred_runtime migrate`. The control-plane
   chain from `aac66348e27b` is
   `f9a2c7d81e40` -> `a4d85307ea0e` -> `c82f6a91d043` -> `cb6f39c6d80c` ->
   `93427a5fe874`. It adds admission state, unique agent names, conversation name
   snapshots, patch-note history and creation-assistant settings. The runtime
   advances from `d4e5c6b7a8f9` to `e5f6a7b8c9d0` for web-research activity.
   Run the normal Knowledge Flow migration check as part of the release as well.
3. Roll out the updated control-plane API and verify it initialized the shared
   admission authority. Filtering remains disabled and saved policy survives
   restarts. Start updated runtime and Knowledge Flow readers only after the
   authority is available; this dependency does not require simultaneous rollout.
4. Roll out the Control Plane worker and all Knowledge Flow workers, including
   common and extraction workers, before the updated API submits new ingestion
   arguments. New workers accept old queued payloads, so the old API may continue
   submitting during worker rollout. Check the entire worker cohort before step 5.
5. Roll out the matching Knowledge Flow API, agent pods and frontend. The chart
   does not order Deployments across services: use staged upgrades to enforce the
   authority and worker dependencies. Verify all replicas use the expected
   settings and resources, then run the checks below.
6. Update saved logging queries for the fields documented below. Run the real
   collector/proxy and Temporal canaries; local checks do not establish production
   log parsing or multi-worker rollout compatibility.

### Optional activation after the ordinary upgrade

- Platform admission filtering: activate it later, after the updated readers
  are in place. At that time, configure and test rules, import existing users if
  desired, review live user/team exceptions and the activation preview, then
  enable deliberately. Link access is separately managed by platform admins.
- Web research: configure the provider secret and approved direct/proxy egress,
  retention and quotas, then enable the team and agent capability. Run the built-in
  deployment checks. It remains disabled without activation.
- Shared skills: select packaged or trusted read-only resources, distribute the
  same files to every replica, drain turns and restart agent pods. Graph agents
  do not support these skills. Existing checkpoints retain already loaded text.
- Autoscaling: prepare metrics, resource requests and shared agent object storage
  before enabling any HPA. Reconcile existing HPA ownership first.
- Creation assistant: optionally select an allowed model, instructions and reasoning
  in platform administration. Defaults require no extra model configuration.

### Conditional data operations

No document re-ingestion is required. Only deployments that already recorded skill
usage before installing its index mappings need the targeted skill-event reindex
shown in the skills section; a normal upgrade from v3.3.0 does not. Earlier draft
admission databases require the schema reconciliation described below, not a blind
stamp. Separately rebuilt external Knowledge Base pods must follow their own SDK
configuration and code compatibility note; publishing this Fred release does not
rebuild or publish those pods or Python packages.

## Validation

After the staged rollout, verify migration heads, initialized admission authority,
matching OpenFGA model selection and worker versions. Test sign-in, an ordinary
chat, an upload through extraction and output, and an ingestion retry. Check API,
worker and frontend log parsing and correlation through the real deployment.
Then validate renamed agents, read-only deleted-agent history, patch notes and
agent creation. Exercise each optionally enabled feature using its checks below.
Validate platform admission with direct and delegated requests and across replicas.

## Rollback

Pause new ingestion submissions. While updated workers are still available,
drain all tasks carrying new diagnostic envelopes. Disable optional admission
filtering deliberately before rollback, and disable web research and its capability.
For retained web-research activity, erase it first or keep the updated runtime
available for purge/erasure until expiry. Disabling admission widens access;
ordinary authentication and resource authorization must remain enforced.

Restore the previous API submission code before rolling back workers, keeping
new ingestion submissions paused throughout. Restore the matching application/chart
versions, prior logging parsers and fixed replica counts as appropriate. Prefer leaving additive
SQL tables/columns in place. The per-feature downgrade targets below are references,
not a sequence to execute: Alembic also downgrades every later revision, deleting
saved settings, patch notes, dismissals, activation history and admission state.
If a schema downgrade is necessary, stop all affected readers/writers and review
the complete chain against the database backup first. Agent renames persist after
downgrade. Restore the recorded prior OpenFGA model selection only with the old
readers; verify access before resuming normal operations.

## Limitations

This guide does not certify private overlays, identity providers, proxy destination
controls, GKE log collectors, live Temporal rollout or production load. Validate the
combined sequence in staging. Deleted agents without recoverable runtime snapshots
still lack readable history. Optional research retains restricted activity subject
to the documented expiry/erasure policy; skills retain loaded checkpoint context.
