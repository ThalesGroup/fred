---
schema: 1
after: [ppt-builder-capability]
title: "Move PPT Builder preparation to the capability worker"
impact: minor
configuration: production
configuration_reason: "The cutover requires a Knowledge Flow vision model, a preparation worker with Temporal and object-store access, and explicit serving and control-plane preparation flags after backfill."
---
## Applicability

This migration moves Swift PPT Builder originals from `cap_ppt_builder_analysis`
into control-plane capability assets, and moves inventories and preview PDFs into
the runtime object store. It also imports the active platform template, a failed
or pending replacement, and the manager's pattern overrides. The old SQL rows
remain intact for the migration window.

## Prerequisites

Make the control-plane and runtime databases and object stores available to the
backfill command. For local storage, mount both storage roots at the same paths
as their services. For MinIO or GCS, supply the same bucket configuration and
credentials as the services. Keep the old PPT reader active until backfill and
worker readiness checks complete.

## Configuration

Set `vision_model` once on the Knowledge Flow API and its worker configuration.
The preparation worker calls Knowledge Flow's internal vision endpoint using
the workload identity named by `vision_worker_client_id`; the caller never
chooses a model. The PPT settings retain only `use_vision`. When Knowledge
Flow reports that no vision model is available, the form disables this switch
and preparation uses the slide labelling rules. If the availability lookup fails,
the form preserves the saved choice and reports that it could not be checked.

The Helm chart defines `applications.fred-agents-preparation-worker` as a
separate deployment using the same capability registry and runtime storage as
`applications.fred-agents`. The Fred chart starts this worker by default;
the cutover still requires explicit preparation flags after backfill. Give it
the same `ai.knowledge_flow_url`, service credentials, Temporal namespace and
object-store configuration as the serving pods. `preparation.max_concurrent_jobs`
bounds work per worker replica. `preparation.per_capability_concurrency` bounds
each installed capability's work within that replica. Set the control-plane
runtime catalog source's `preparation_enabled` and serving pod's
`preparation.enabled_capabilities` only after backfill and worker readiness
checks are complete.
The deployment command is `python -m fred_runtime preparation-worker`, also
available through `make run-worker` and `make run-worker-docker` in `fred-agents`.
Other agent pod images with `fred-runtime` installed use the same command; the
generic `agent-pod` chart exposes it with `preparationWorker.enabled: true`.
Temporal retries a worker activity after two minutes without a heartbeat.
Agent multipart saves accept at most 64 MiB across all capability assets.

## Upgrade

1. Deploy the additive control-plane migration, Knowledge Flow vision endpoint,
   and the separate `fred-agents` preparation worker. Keep
   `preparation.enabled_capabilities` empty on serving pods while backfilling.
2. Stop PPT template edits during the final pass. Let old analyses finish or
   repeat the pass until their status and hashes stop changing. Do not enable
   the new reader while a legacy `__platform_next__` row has succeeded but has
   not yet been promoted by the old job.
3. Run a dry pass and then the import. The command scans one legacy row at a
   time, verifies every template hash, writes immutable objects under stable
   keys, and commits one control-plane row at a time. Re-running it is safe.

```bash
python -m control_plane_backend.capability_preparations.backfill_cli \
  --control-plane-config /path/to/control-plane/configuration.yaml \
  --control-plane-env /path/to/control-plane/.env \
  --runtime-config /path/to/fred-agents/configuration.yaml \
  --rules-version 23 --dry-run

python -m control_plane_backend.capability_preparations.backfill_cli \
  --control-plane-config /path/to/control-plane/configuration.yaml \
  --control-plane-env /path/to/control-plane/.env \
  --runtime-config /path/to/fred-agents/configuration.yaml \
  --rules-version 23
```

Run from the control-plane application directory with an environment containing
`control_plane_backend`, `fred_core`, `fred_sdk`, `fred_pod`, SQLAlchemy, and the
configured object-store clients. Set `PPT_BACKFILL_RUNTIME_POSTGRES_PASSWORD` if
the runtime database has a different password from `FRED_POSTGRES_PASSWORD`.
The rules version must match PPT Builder's `PreparationSpec.rules_version` in
the serving image.

## Validation

The JSON result reports `total` and counts for `imported`, `imported_builtin`,
`existing`, and `skipped_*`. Check that their sum equals `total`. Deleted agents
can be skipped.
The import command exits with an error if any live agent with a selected PPT
template has no current preparation, including one skipped because its template
changed. It also refuses a successful legacy analysis made with older rules;
re-run that analysis on the old service, then repeat the import. Stop edits for
the final pass so this check remains valid until the flags are enabled.
Investigate changed or unconfigured agents before cutover, and check the active
platform default and replacement in the PPT admin panel. The dry pass never
writes to the control-plane database or either object store.

After reconciliation, enable `ppt_builder` in
`preparation.enabled_capabilities` on every `fred-agents` serving pod and set
the matching control-plane runtime catalog source to `preparation_enabled`.
Verify the already deployed worker uses the same capability registry, runtime
object store, and Temporal namespace. Existing agent configs retain their
historical fields in SQL, but the enabled reader uses the imported result. The
next save removes the legacy model selection. A failed imported preparation can
be retried without a new upload.

## Rollback

Before new template edits, rollback is a switch back to the old reader and
writer because the legacy SQL rows were not deleted. After new edits begin, do
not switch back without first reconciling those new assets into the legacy
store; the old SQL rows no longer contain the latest uploaded templates.

## Limitations

During the migration window, stop template edits for the final backfill pass.
After cutover, the legacy SQL rows no longer contain new template assets.
