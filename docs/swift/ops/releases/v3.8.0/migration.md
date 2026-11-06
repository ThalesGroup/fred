# Migration guide - v3.8.0

Upgrade from: `code/v3.7.1`
Operational impact: **minor** (minimum version: `3.8.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Derive document and resource access from readable folders

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/2845-derive-document-access-from-folders.md)

A normal image deployment applies the fix. If Knowledge Flow or the control plane log event=authorization_list_objects outcome=possibly_truncated, one user reaches OpenFGA's ListObjects limits: raise OPENFGA_LIST_OBJECTS_MAX_RESULTS or OPENFGA_LIST_OBJECTS_DEADLINE on the OpenFGA server.

See the source note for applicability, validation and rollback.

## Team descriptions become required; platform admins edit any team

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/3067-require-team-description.md)

### Applicability

Every Fred deployment. Teams without a description, or with one shorter than 20
characters, are affected by the data migration. Deployments that pin
`openfga.authorization_model_id` with `sync_schema_on_init: false` must also
publish the new authorization model.

### Prerequisites

Before upgrading, count the teams that will receive the default description
(read-only, on the control-plane database):

```sql
SELECT count(*) FROM teammetadata
WHERE description IS NULL OR length(trim(description)) < 20;
```

No preparation is required: the count only tells you how many team
administrators will have a description to write.

### Configuration

No configuration changes are required.

The OpenFGA authorization model gains one relation,
`organization#can_edit_team_registry` (`platform_admin` only). With the default
`sync_schema_on_init: true` the control plane writes the new model at startup.
With `sync_schema_on_init: false` and a pinned `authorization_model_id`, write
`libs/fred-core/fred_core/security/rebac/schema.fga.json` from this release to
the store and point `authorization_model_id` at the new model before starting
the new control plane; otherwise the new edit action answers 403.

### Upgrade

Deploy Fred normally. The control-plane database migration (revision
`c9acb7dd3ad0`) runs with the usual `alembic upgrade head` step:

1. Every team whose description is missing, blank or shorter than 20 characters
   receives the default text « Description à compléter par l'administrateur de
   l'équipe. ». Valid descriptions are kept, without surrounding spaces.
2. `teammetadata.description` becomes `VARCHAR(500) NOT NULL`, with the check
   constraint `ck_teammetadata_description_min_length` (at least 20 characters
   once trimmed).

After the upgrade:

- Creating a team requires a description of 20 to 500 characters.
- A team description can be edited but no longer cleared.
- Team administrators of a team carrying the default text see a reminder on
  the team's home page and in its settings. Ask them to write it: the
  description is shown on every marketplace team card.
- A platform import never fails on a description: imported teams without a
  valid one receive the default text, and the import report states how many.
- The administration teams page opens team creation in a dialog from its
  header. Platform administrators (never team managers) also get an Edit
  action on each team: name, description and team administrators. A team keeps
  at least one active administrator; a new administrator still has to accept
  the team administrator charter. Every edit writes a `team.registry.edited`
  audit event (actor, team, changed fields, administrator ids added and
  removed).

### Validation

List the teams that still carry the default description:

```sql
SELECT id, name FROM teammetadata
WHERE description = 'Description à compléter par l''administrateur de l''équipe.';
```

In the UI, open the administration teams page as a platform administrator:
the create dialog refuses to submit without a description of at least 20
characters, and the Edit action on a team saves a new name or description.
As a team manager, the page shows no Edit action. Open the marketplace
teams page: every card shows a description.

### Rollback

Downgrade the control-plane database to revision `d4e8b2a6f091` **with this
release**, then redeploy the previous one: the previous release does not know
the revision and cannot downgrade it. A previous control-plane running against
the upgraded database cannot create a team (it sends no description, the
database refuses the row and the API answers a misleading 409), so do not leave
both in place. The same holds during a rolling update: team creation can fail
on the old pods until they are replaced.

The downgrade restores an optional `VARCHAR(180)` column and is lossy:

- descriptions equal to the default text are cleared (`NULL`);
- descriptions longer than 180 characters are **cut to their first 180
  characters**. Export them first if they must be kept:

```sql
SELECT id, name, description FROM teammetadata WHERE length(description) > 180;
```

The OpenFGA relation needs no rollback: the previous release ignores it.

### Limitations

- `POST /teams` now requires `description`, and `PATCH /teams/{team_id}`
  refuses `description: null` or a value outside 20 to 500 characters (422). Only
  the Fred frontend and the platform importer call these routes; adapt any
  custom client.
- The default text is stored in French whatever the platform language; the UI
  shows it translated.
- The Knowledge Flow storage backfill script from an older release cannot
  create missing team records on an upgraded database; use the script shipped
  with this release.
- Direct SQL writes to `teammetadata` must provide a description of at least
  20 characters.
- `PATCH /teams/{team_id}/registry` is new and `platform_admin` only. Removing
  the only active administrator, including replacing them with a user who has
  not accepted the charter yet, is refused (409) until the new one accepts.

## Expose agent pods through an optional Gateway API HTTPRoute

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/agent-pod-http-route.md)

### Applicability

Deployments that use Fred's published `agent-pod` chart. Existing releases remain
unchanged when `httpRoute.enabled` is omitted or false.

### Prerequisites

Optional activation requires a Gateway API v1 controller and a Gateway listener
that accepts HTTPRoutes from the agent pod namespace and the browser-facing
hostname. The pod's `configuration.app.base_url` and Fred's
`runtime_catalog_sources[].ingress_prefix` must be the same canonical path.

### Configuration

To activate the route, set `httpRoute.enabled: true`, `httpRoute.parentRefs`
with the Gateway name and namespace, and `httpRoute.hostnames` with the Fred
browser hostname in the agent pod chart values. Set `httpRoute.requestTimeout`
when streaming needs a longer request timeout, if the Gateway controller
supports it. The chart forwards the pod's base path to its own Service.
No new Secret or Fred Control Plane setting is introduced.

### Upgrade

Upgrade the `agent-pod` chart normally. Current values render no HTTPRoute.
For optional activation, add the values above and upgrade that pod's release
using the chart version that includes this feature. A separately maintained
HTTPRoute for the same pod path should be removed during the switch so route
ownership remains clear.

### Validation

Render the release with `helm template` and confirm the HTTPRoute matches the
pod base path and targets its Service. After activation, check that the route
is accepted by the Gateway and that browser chat requests reach the agent pod.

### Rollback

Set `httpRoute.enabled: false` and upgrade, or restore the previous chart
version. No data migration is involved.

### Limitations

The chart cannot grant Gateway listener permissions or install Gateway API
CRDs. Request timeout support depends on the Gateway controller.

## Pod charts (knowledge-base, agent-pod) can be used as a Helm dependency

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/pod-charts-as-helm-dependency.md)

Releases of the agent-pod and knowledge-base charts render the same resources; the knowledge-base README and install notes now name the `knowledge_bases.publishers` entry Fred already required.

See the source note for applicability, validation and rollback.

## Restore the initial T0 whitelist import action

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/t0-initial-import-null-body.md)

The initial import works after the normal frontend rollout; no data migration or operator action is required.

See the source note for applicability, validation and rollback.

## Recognize published pod chart values in migration checks

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/3185-recognize-pod-chart-production-values.md)

The validation fix changes release preparation checks only. Existing deployments need no additional upgrade action.

See the source note for applicability, validation and rollback.

## Prepare the Fred 3.8.0 release

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.8.0/docs/swift/ops/migrations/3185-prepare-fred-3-8-0.md)

Release preparation adds no action beyond the team-description migration and optional Gateway activation documented in their source notes. Existing documents need no re-ingestion.

See the source note for applicability, validation and rollback.
