# Rolling back a Fred deployment on Docker Compose

This runbook is for an operator deploying the Fred application with a **site-owned
Docker Compose file** and persistent services. Fill in the service map and rehearsal
results before the production change. It covers an unsatisfactory release, including
one that has already applied database migrations.

The maintained Compose files in `fred-deployment-factory/docker/` deploy supporting
services, not the complete Fred application. `deploy/docker-compose/docker-compose.yml`
in this repository is an older development setup and is not a production release
manifest. Do not copy service names or commands from either into a live procedure
without checking the actual rendered configuration.

Read the [deployment guide](../platform/DEPLOYMENT_GUIDE.md),
[database migration guide](DATABASE_MIGRATIONS.md), and the **migration guide for
the release being installed** in `releases/vX.Y.Z/migration.md`. The release guide
controls special ordering, data transformations, feature activation, OpenFGA model
changes and downgrade limits. This runbook supplies the Compose sequence around it.

## 1. Prepare a release-specific rollback sheet

Record the following before the maintenance window:

| Item | Record for this deployment |
| --- | --- |
| Old and new paired Fred code/chart versions | Exact tags and immutable image digests for frontend, control plane, Knowledge Flow API/workers, agent pods and any other Fred workers |
| Compose inputs | Compose files, project name, profiles, `.env`/secret sources, mounted configuration and reverse proxy routes for both versions |
| Service map | Actual service names for frontend, control plane, Knowledge Flow API/workers, agent pods, Temporal workers and migration jobs |
| Dependencies | PostgreSQL database names, Keycloak, OpenFGA store/model ID, object-store buckets, OpenSearch/pgvector, Temporal, external agent pods and persistent volumes |
| Alembic positions | Current and target revisions of every tree in the table below; all migrations crossed, their `downgrade()` effects and any irreversible data changes |
| Recovery | Tested backup location, restore command/procedure, encryption/access, recovery point and expected data loss; owner of the go/no-go decision |
| Validation | Login, authorization, chat, document upload/search, worker completion and any release-specific checks |

Use immutable image digests or retained, immutable tags. Keep the old Compose files,
configuration, secrets, model catalog and images available. A tag that has been
overwritten is not a rollback artifact. Render both configurations with
`docker compose -f <app-compose> -p <project> config` and review images, mounts,
environment, services and named volumes. Keep rendered output containing secrets
out of tickets and logs.

The database is shared, but migrations are **separate version chains**:

| Owner | Version table | Migration command from the matching new image |
| --- | --- | --- |
| Control plane | `alembic_version_control_plane` | `alembic upgrade head` |
| Knowledge Flow | `alembic_version_knowledge_flow` | `alembic upgrade head` |
| Agent runtime | `alembic_version_runtime` | `python -m fred_runtime migrate` |
| Installed capabilities with migrations | Their own `cap_*_alembic_version` tables, for example `cap_writable_document_alembic_version` | Included in `python -m fred_runtime migrate` |

The runtime command upgrades its own tree and then every installed capability tree.
It is **not** a downgrade command. Check the actual installed capabilities in the
new and old agent images. Record all version tables, not just one generic
`alembic_version`. The old image may not contain migration files for the new
revision, so any required downgrade must run with the **new image** before old
application processes start.

For each affected database, take an application-consistent backup immediately
before migration. Quiesce new writes first: block ingress or put Fred in
maintenance mode; stop API, agent and worker writers; drain or pause Temporal
tasks and scheduled ingestion. Capture PostgreSQL with a tested `pg_dump -Fc`
or managed snapshot, including the Fred database and separate Keycloak,
OpenFGA, Temporal or other databases that the release changes. Include roles and
extensions if the restore method needs them. Capture object-store buckets and
versions, OpenSearch indexes/snapshots if used, and any local persistent files.
Coordinate the recovery point across stores. A PostgreSQL backup alone cannot
recover files uploaded to object storage or external authorization changes.
Verify that backup files are nonempty, readable and restorable on an isolated
instance; record checksums and the exact point in time. Protect them as secrets.

`fred-deployment-factory` has `make checkpoint-save` and
`checkpoint-restore` for local testing. Its save script stops the stack and
archives a hard-coded volume list; restore calls `docker-wipe`. The list does
not cover every current persistent store (including SeaweedFS). Do not treat
that checkpoint as a complete production backup or use its restore against a
live deployment.

## 2. Deploy with a rollback gate

1. In staging, rehearse **the same old-to-new jump and the chosen rollback**
   using a representative backup. Review every release-specific migration note.
   Mark each change as reversible in place, forward compatible with old code,
   or requiring full data restoration. Decide how writes made after cutover will
   be exported or lost if the pre-upgrade snapshot is restored.
2. Quiesce Fred writers and take the coordinated pre-upgrade backup. Keep
   PostgreSQL and the other data services running. Record the old Alembic
   revisions using read-only SQL such as
   `SELECT version_num FROM alembic_version_control_plane;` and the equivalent
   queries for every tree. A missing version table needs investigation, not a
   guessed `alembic stamp`.
3. Prepare any OpenFGA model, secrets, storage or external services required
   **before** new readers start, in the order specified by the release guide.
   Stop old readers when the schema change is not backward compatible.
4. Run each required migration **once**, using a one-off container from its
   matching new image with the same `CONFIG_FILE`, database connection, secrets
   and network as the application. For example, after substituting actual
   service names and Compose options:

   ```bash
   docker compose -f <app-compose> -p <project> run --rm --no-deps --entrypoint alembic <control-plane-service> upgrade head
   docker compose -f <app-compose> -p <project> run --rm --no-deps --entrypoint alembic <knowledge-flow-service> upgrade head
   docker compose -f <app-compose> -p <project> run --rm --no-deps --entrypoint python <agent-service> -m fred_runtime migrate
   ```

   The production images contain the migration code and `alembic` CLI. A
   normal Compose `up` starts application entrypoints; it does not implicitly
   run these migrations. Do not run concurrent migration containers against
   the same tree. If a migration fails, keep writers stopped, inspect the
   actual schema and version rows, and restore the backup or repair the
   partial change deliberately. Do not use `stamp` to bypass failed SQL.
5. Check the resulting version rows against the heads in the new images.
   Start new workers, APIs, agent pods and frontend in the order required by
   the release guide. Run canaries before reopening traffic. Record the
   cutover time, image digests and observed checks. Do not enable optional
   features until their separate prerequisites and rollback are ready.

## 3. Decide what kind of rollback is safe

At the first serious failure, stop new ingress, ingestion and scheduled work.
Preserve logs and the database state. Determine whether new-version writes or
external side effects occurred. Stop or drain workers before changing schemas;
new workers must not keep writing while old readers start. Use one of these paths:

| Condition | Action |
| --- | --- |
| Failure before migration or before any new writes | Restore old application images and configuration; validate revisions and dependencies before reopening traffic. |
| Migration applied, but release guide and rehearsal prove the old code works with the **current** schema and data | Roll back application images/configuration only. Leave additive tables/columns and Alembic version rows at their new revisions. Do not run old migration jobs. |
| Old code needs the old schema, and all crossed `downgrade()` functions plus data changes are reviewed and rehearsed | Keep **all** affected readers/writers stopped. Run the exact planned downgrades with new-version migration code, in dependency order, then restore old images/configuration. Confirm no post-cutover data will be destroyed unexpectedly. |
| Downgrade is missing, destructive, ambiguous, or external stores must be reverted together | Restore the coordinated pre-upgrade snapshot to an isolated target, validate it, then cut over all related stores and old application images as one recovery operation. Accept or reconcile the documented post-backup data loss. |

Do not equate `alembic downgrade -1` with a release rollback. One release may
span multiple revisions in multiple trees. A downgrade can drop columns,
indexes or tables and **cannot reconstruct deleted data**; some `downgrade()`
functions are deliberately no-ops. Inspect the complete path from each
current revision to its recorded old revision. If a capability package was
removed in the target release, retain the newer image for its migration tree
until the database decision is complete. Never run `alembic upgrade head`
from the old image against a database stamped at a newer revision.

## 4. Execute the selected rollback

1. Record the current recovery point and make a **second** snapshot if useful
   for forensic analysis or selective data recovery. Keep the pre-upgrade
   backup immutable. Stop Fred frontends, APIs, agent pods and **all** relevant
   workers. Keep dependency services running for an in-place downgrade.
2. For a code-only rollback, set every Fred service to its retained old image
   digest and restore its old configuration, secrets and model catalog. Use
   `docker compose -f <old-app-compose> -p <project> up -d --no-build` for the
   selected services after reviewing `config` output. Do not run old migration
   jobs or an `up` command that silently selects newly built images.
3. For an in-place schema rollback, use the **new** image to run `alembic
   downgrade <recorded-old-revision>` separately for control plane and
   Knowledge Flow. For runtime and each capability, invoke Alembic against
   its own migration directory and version table with the new agent image;
   `python -m fred_runtime migrate` cannot downgrade. Use the release guide's
   exact targets and ordering, not a blanket `base` or `-1`. Check the
   version table and affected data after each tree. Then perform step 2.
4. For snapshot restoration, keep all application writers stopped. Restore
   PostgreSQL and any affected Keycloak/OpenFGA/Temporal databases, object
   storage, OpenSearch and local files from the **same coordinated recovery
   point**, using the rehearsed environment-specific restore procedure.
   Restore into isolated instances or empty targets where possible; validate
   before changing service endpoints. Switch old application images and
   configuration only after the restored stores agree. Do not overlay a live
   PostgreSQL data directory or reuse a partially restored volume.
5. Revert release-specific feature flags, OpenFGA model selection and external
   integrations as directed by the release guide. Restore old worker/API
   ordering, then frontend/traffic. A rollback of Fred containers does not
   undo external LLM calls, tool actions, emails or writes to third-party
   systems; reconcile those separately.

## 5. Verify and close the incident

- Confirm all containers run the recorded old image digests and effective
  configuration. Check health, logs, dependency connections and worker queues.
- Compare **every** Alembic version table to the selected plan. For a code-only
  rollback, new revisions are expected; for a schema or snapshot rollback,
  old revisions must match the recorded targets. Do not stamp them to hide drift.
- Test sign-in and a known authorization decision, team/agent listing, a new
  chat, an existing conversation where supported, document upload and search,
  and at least one queued or scheduled task. Validate object references and
  OpenFGA behavior, not just HTTP health checks.
- Reopen traffic only after the checks pass. Record the rollback time, chosen
  recovery point, data lost or reconciled, outstanding tasks, and the evidence
  needed to retry the release. Retain both backups until the incident is closed.

If the current state does not fit a rehearsed path, keep writers stopped and
escalate to the release and data owners. Guessing a revision or restoring only
one store can turn a recoverable failed deployment into data corruption.

## Kubernetes deployments

The same database decision applies to Kubernetes. The Fred chart's migration
Jobs run on `pre-install,pre-upgrade`, not on rollback, and migration Jobs are
disabled by default unless the platform overlay enables them. The local k3d
deployment factory uses Helm's `--rollback-on-failure` or `--atomic`. These
options can restore an earlier Helm release after a failed rollout, but cannot
undo SQL or changes in OpenFGA/object storage. Check the **database revisions
after any automatic Helm rollback** before serving traffic with old pods.
Do not assume `helm rollback` is a complete Fred rollback. Follow the release
guide and the same code-only, reviewed downgrade or coordinated snapshot
decision above; the exact Kubernetes commands depend on the deployment overlay.
