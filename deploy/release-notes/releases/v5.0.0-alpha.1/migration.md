# Release report - v5.0.0-alpha.1

Report baseline: `f50b9a8ea8b88cac99205e7cffd2bd9eee8eef0b`
Operational impact: **major** (minimum version: `5.0.0`).

Fresh installation required. Upgrades from Swift or an earlier Weaver are not supported. Customer-specific values remain in private deployment repositories; the matching Fred chart is the configuration reference.

This initial report starts a new release history; it does not reconstruct the Swift-to-Weaver changes.

## Explicit reasoning effort and evaluation admission evidence

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/3689-inference-effort-evidence.md)

Normal deployment supplies the updated Control Plane and runtime contracts; existing boolean reasoning callers keep their behavior.

See the source note for applicability, validation and rollback.

## Ingest audio and video files with their transcript and scene descriptions

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/3717-video-ingestion.md)

Existing profiles keep working: the new suffixes and the `video` block have defaults, the Whisper model is already packaged in the worker image, and no database or upload limit changes.

See the source note for applicability, validation and rollback.

## Resources page: Corpus tree, stable table layout and copy name

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/resources-ui-update.md)

The tree reads the existing Control Plane folder entries API already used by the resources table; no new endpoint, permission or data migration is involved.

See the source note for applicability, validation and rollback.

## Every space role implies membership of its space

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/space-roles-imply-member.md)

### Applicability

Weaver deployments upgrading Control Plane and frontend. This is not a Swift
database migration.

### Prerequisites

Use the normal backup and schema-owner procedure.

### Configuration

No configuration changes are required.

### Upgrade

Run `control-plane init-schema` with the normal schema-owner identity to apply
SQLx migration `0060_space_roles_imply_member.sql`, then deploy matching Control
Plane and frontend versions. The migration adds `member` wherever a person held
owner, editor, analyst, organization admin or organization observer on a space
without it, and a deferred constraint refuses any later role holder without
membership. Platform roles are unchanged and imply no membership.

Visible effect: owners and organization admins who held no content role now
read their space's content (agents, resources, prompts) and see it in their
navigation. Granting any role also grants `member`. Revoking `member` alone
while other roles remain returns 409 `membership_removal_required`; removing a
person goes through `DELETE /control-plane/v1/spaces/{id}/members/{user}`,
which now also serves organizations and personal spaces. In member management,
`member` is no longer a role checkbox: people added without a role join as
members, and the row's Remove action takes them out of the space. Organization
owners now manage their organization's members and search the whole identity
directory for people to add.

### Validation

As a team Owner without any other role before the upgrade, open the team after
the upgrade: its agents, resources and prompts are listed. In the team's member
management, add a person without selecting a role and verify they appear with
no role chip selected; remove them with Remove and verify they leave the list.

### Rollback

Roll back Control Plane and frontend together. An older Control Plane binary
rejects the newer SQLx migration history; restore a matching pre-upgrade database
backup with the prior binaries. Do not remove migration receipts manually.

### Limitations

Owners can no longer govern a space without reading its content; organization
admins remain the role that governs an organization, now as members of it.

## Refresh the initial Weaver release report after integration

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-alpha-report-refresh.md)

The report now includes the integrated audio/video ingestion and Resources page notes; no additional deployment action is introduced.

See the source note for applicability, validation and rollback.

## Use GitHub and arc42 for Weaver delivery

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-github-arc42-workflow.md)

No runtime behavior, schema, permissions or operator procedure changes; deploy normally.

See the source note for applicability, validation and rollback.

## Weaver initial test and integration release

Impact: **major** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-initial-release.md)

### Applicability

Weaver 5.0.0-alpha.1 is an initial release for test and integration platforms.
It starts an independent release history with an intentional break from Swift.
No detailed Swift-to-Weaver change inventory or migration procedure is provided.

The core distribution comprises Control Plane, the frontend, Fred Agents and
Knowledge Flow's API and ingestion worker, including the optional PyMuPDF worker
image, plus the technical monitor. The Fred, Agent Pod and
Knowledge Base Helm charts are packaged by the existing chart workflow.

### Prerequisites

Use a new installation with empty application databases and dedicated storage.
Provide Kubernetes and Helm, PostgreSQL, OpenSearch, an identity provider,
Temporal, object storage and the credentials for the selected model providers.
See the matching [chart requirements](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#requirements).

### Configuration

Use the Weaver chart and platform-owned values and Secrets. Configure service
endpoints, identity clients, model sources and ingress for the target platform.
Do not reuse Swift application configuration or an existing Swift database.
See the [chart configuration](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#your-values-file).

### Upgrade

Install the versioned chart with its matching images on the new platform. Run
the chart's schema-initialization and migration hooks before starting services,
then complete platform bootstrap and provisioning. There is no in-place upgrade
from Swift or an older Weaver installation.

Version 5 branch pushes publish `v5-dev`; Swift continues using `swift-dev`. Paired
`code/v5.0.0-alpha.1` and `chart/v5.0.0-alpha.1` tags on the same commit publish
the initial release. Prereleases do not update `latest`; stable releases do.
See [image publication](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/README.md#image-publication).

### Validation

Before accepting a platform, confirm that all seven image publications and all
three chart packages succeeded. Check initialization Jobs and workload readiness,
then verify sign-in, an authorized assistant conversation, and document ingestion
and retrieval. These platform checks are operator acceptance steps; generating
this report does not execute or certify them.

### Rollback

Keep the existing Swift platform independent and available during evaluation.
Stop using the new Weaver platform if acceptance fails. Returning to Swift does
not transfer Weaver data; no cross-version data rollback is supported.

### Limitations

This alpha release is intended for test and integration, not production approval.
Resources bulk ZIP download is not available on the Weaver path (#3367).
The platform-wide activity, corpus audit and platform-data migration pages show
pending-feature notices; their Swift preview does not provide Weaver operations.
Platform provisioning remains a separate supported setup path.

Publishing artifacts does not deploy a platform. Dev tags are mutable and a failed
image matrix can leave a partial publication; use a fully published version for
platform acceptance. Later release reports cover changes since the previous
Weaver release, while fresh installation remains the supported deployment path.

## Weaver project parameters, creation and team projects list

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-project-parameters.md)

### Applicability

Weaver deployments upgrading Control Plane and frontend. This is not a Swift
database migration.

### Prerequisites

Use the normal backup and schema-owner procedure.

### Configuration

No configuration changes are required.

### Upgrade

Run `control-plane init-schema` with the normal schema-owner identity to apply
SQLx migration `0059_project_parameters.sql`, then deploy matching Control Plane
and frontend versions. Existing projects keep no description, no avatar, the
inherited conversation retention, hidden visibility and invitation-only joining,
so nothing becomes visible until a project Owner changes it.

A project's direct Owner now finds Parameters first in the project's settings
(name, description, avatar, conversation retention, visibility and joining). For a
project, visibility and open joining address members of the parent team. A team's
Projects page lists its visible projects plus the person's own, with a Join action
on open ones. A team Owner without a content role also lists them and lands on
that page, but joining still requires a content role in the team. A project
without its own conversation retention follows its parent team's configured value,
then the lifecycle policy.

The team's direct Owner creates a project from the team's Projects page, setting
its parameters and its initial members (at least one Owner, each holding a
content role in the team) in one step. `POST /control-plane/v1/spaces` now takes
`members: [{user, roles}]` instead of `owner`, plus optional `description`
(required for a project), `visibility`, `joining_mode` and
`conversation_retention_seconds`. Clients calling it directly must send the new
body; an `owner` field is refused.

### Validation

As a project Owner, open the project's settings gear: it lands on Parameters. Make
the project visible with open joining. As another member of the parent team, open
the team's Projects page, join the project and verify it opens. As the team
Owner, create a project from that page with yourself as its Owner and verify its
card appears.

### Rollback

Roll back Control Plane and frontend together. An older Control Plane binary
rejects the newer SQLx migration history; restore a matching pre-upgrade database
backup with the prior binaries. Do not remove migration receipts manually.

### Limitations

A team's retention change applies only to future deletion requests in its
projects; accepted requests keep their deadline.

## Accept discovered model licenses in Agent Pod runtime resolution

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-runtime-model-license-contract.md)

Deploy the corrected Agent Pod image through the normal chart update; no credential, policy or data changes are required.

See the source note for applicability, validation and rollback.

## Weaver spreadsheet generation and Swift interface improvements

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-swift-20261126.md)

### Applicability

Fresh Weaver installations using the standard fred-agents image and frontend.
This integration preserves Weaver 5.x versions and its Control Plane authority.
It replaces the incoming Swift-only operator instructions for this merge.

### Prerequisites

Deploy matching Control Plane, agent and frontend components. The spreadsheet
package is included in fred-agents; third-party pods keep their own package set.
The frontend image uses `nginx/nginx-unprivileged:1.31.10-alpine`; installations
that mirror images must make that image available through their existing process.

### Configuration

Use existing organization and space capability governance to make spreadsheet
generation available, then enable the Excel pack on the agent. No new global
activation or database configuration is introduced. Optional daily theme schedules
use the existing theme configuration and the browser's local clock.

### Upgrade

Use the normal fresh-install deployment procedure. Upgrades from Swift or earlier
Weaver installations remain unsupported. No spreadsheet table or migration is
introduced: generated workbooks and their previews belong to the conversation's
existing file catalogue and deletion lifecycle.

### Validation

In a conversation with an enabled agent, create a workbook, preview and download
it, then request a targeted change in the next turn. Both versions must remain
downloadable. Reload the conversation and repeat a change; stale or conflicting
sources must produce an explicit refusal, not overwrite an existing version.
Verify conversation deletion revokes access to its files through the usual path.

Also check resource table resizing and range selection, the friendly router error
page, copying error details, unsaved wiki history, and queueing a message while a
dialog is open. Agent model calls receive the current UTC date. These are developer
reception scenarios, not a claim that a deployed browser or provider was tested.

### Rollback

Use matching previous Weaver components through the normal deployment process.
Previously generated files remain ordinary conversation deliverables; removing
the capability removes its creation/revision tool. No capability database state
needs repair or conversion.

### Limitations

Revision requests refer to an exact file snapshot, with identifiers supplied to
the model rather than entered by the user. Workbooks carry their bounded revision
specification; imported or modified files without a valid specification cannot be
revised by this tool. There is no hidden mutable "last workbook" record.

Existing spreadsheet engine limits and unsupported formulas remain documented in
the package README. Existing conversation file quotas still apply. JSON previews
are attached to their workbook and are not PDF previews for generic viewers.

Organization allowlisting remains deferred. The legacy Resources tree is absent
from active Weaver pages, so its new Swift persistence preference is not added to
the SQL model. Trace improvements retain existing observer and consent boundaries;
they do not grant new access to owner identity or contact details.

## Reconcile Swift release metadata and Python dependency locks

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-swift-v3-18-dependency-reconciliation.md)

The pyasn1 patch update is installed by the normal image build; no configuration or data migration is required.

See the source note for applicability, validation and rollback.

## Identify version 5 development images by their major version

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/v5-development-image-tag.md)

### Applicability

Development platforms following the images published from the `weaver` branch.
Versioned releases and Swift's `swift-dev` publication are unchanged.

### Prerequisites

Wait for all enabled `v5-dev` image publications to succeed before updating a platform.

### Configuration

In platform-owned values, replace `weaver-dev` with `v5-dev` wherever it is used
as `applications.<name>.image.tag`. Keep component repository names unchanged.
Versioned deployments retain their exact release tags and matching chart.

### Upgrade

Apply the updated values and arrange an image refresh and rollout. The old
`weaver-dev` alias is no longer published; its existing images remain in GHCR.
See the [publication conventions](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/README.md#image-publication).

### Validation

Check that the rendered workloads select `v5-dev` and that their image revisions
match the successful publication's source commit. A tag rename alone does not
restart existing workloads.

### Rollback

Restore the previously accepted image digests or an explicit release version.
No database change is introduced by this publication rename.

### Limitations

This change does not rename branches, namespaces, databases or platform URLs.
It does not deploy a platform. `v5-dev` remains mutable and is intended for
development; use exact release versions for preproduction and production.

## Install the v5 platform and monitor from the standard chart

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/v5-standard-chart-and-monitor.md)

### Applicability

Fresh v5 test and integration installations. No upgrade from Swift or an earlier
Weaver database is supported. Swift's branch and publication flow are unchanged.

### Prerequisites

Provision the external services, fresh SQL database/roles, buckets, trusted CAs,
identity clients and Secrets in the [chart requirements](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#requirements).
The optional PostgreSQL bootstrap hook needs administrator credentials; application
pods and monitor must use their own component credentials.

### Configuration

Use the standard `fred` chart with platform overrides only. It enables Fred Agents,
its preparation worker, document processing and monitor, and initializes Control
Plane and runtime/capability schemas in order. The retired `control-plane-worker`
entry is removed: lifecycle work runs in Control Plane's `serve` process.

Supply addresses, ingress/TLS, model sources and credentials, storage and sizing.
See the [external Secret contract](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#external-secret-contract).
Monitor uses `fred-secrets/POSTGRES_MONITOR_DATABASE_URL` for the dedicated
`fred_monitor` login, with `cp_read` search path; never use owner credentials.
The bootstrap token remains an explicit Control Plane Secret reference.

The runtime has no Kubernetes API permissions or kubeconfig mount by default.
Deployments needing Kubernetes tools must explicitly supply scoped access.
When selecting OpenSearch for Knowledge Flow, supply `type` and `index`; remove
obsolete `collection_name: null` entries from overlays. API and worker must select
the same corpus. Runtime object storage defaults to a shared private S3 bucket.

### Upgrade

Install on a fresh platform using a fully published chart version and its matching
images. Monitor now participates in the existing image publication workflow,
including `v5-dev`. Dev tags remain mutable; publication alone does not roll pods.

### Validation

Check ordered initialization Jobs, workload readiness and monitor image pulls.
Verify platform bootstrap, a conversation, document ingestion/search and capability
preparation. A platform administrator should see the monitor status; unauthorized
users must not obtain it. Rendering checks do not establish live acceptance.

### Rollback

Stop using the new platform if acceptance fails. Keep Swift separate; no transfer
or rollback of Weaver data into Swift is supported.

### Limitations

No infrastructure or platform deployment is performed by image/chart publication.
The first alpha must be published before it can be pinned by the deployment factory.
Operational acceptance belongs to the target platform's operator.

## Align v5 processing defaults with runtime transport validation

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/v5-processing-transport.md)

### Applicability

Fresh v5 platforms using the standard chart, including the first alpha.

### Prerequisites

A reachable TLS ingress or gateway for Control Plane, a trusted identity issuer
and object storage. The Control Plane HTTP Service itself does not terminate TLS.

### Configuration

Replace `https://your.host/control-plane/v1` and
`https://identity.example.test/realms/app` with your platform addresses. Keep the
issuer consistent across security settings and processing/preparation identities.
Both processing implementations retain their HTTPS validation. See
[processing transport](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#your-values-file) for the
explicit local HTTP overrides; the k3d factory owns that local-only posture.

### Upgrade

Use the corrected chart for a fresh installation. No runtime validation is relaxed
and no database change is introduced.

### Validation

Check that the rendered processing settings pass both application validators,
then verify ingestion on the target platform. Helm schema validation alone does
not execute application transport validators.

### Rollback

Restore a previously accepted values file with reachable, transport-compatible
addresses. Do not revert to HTTP without the deliberate local-only opt-in.

### Limitations

Placeholder URLs pass configuration validation but must be replaced with real,
reachable platform endpoints before deployment. No deployment is performed here.

## Publish coherent v5 development charts after successful image builds

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/v5-development-charts.md)

### Applicability

Fresh v5 test platforms consuming the standard Fred chart, including monitor.

### Prerequisites

A successful Weaver image-and-chart publication, existing platform Secrets and
instance values. The factory uses Helmfile 1.8.1 to resolve the latest OCI dev chart.

### Configuration

Development charts use version `5.0.0-dev.<run-id>.<attempt>` and supply
`applications.<name>.image.digest` for every built-in image. Digests override tags.
Keep these defaults; override platform settings only. To select an image variant,
override both repository and digest, or explicitly clear the digest to use a tag.
The archive's `files/image-digests.json` includes the optional PyMuPDF variant.
See [development publication](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/README.md#development-charts).

### Upgrade

Run the factory's existing `make k3d-app FRED=weaver APP=fred` to consume the latest
successful development build. Use `RELEASE=<exact-chart-version>` to select a
particular build. Publication does not deploy a cluster. No data upgrade from an
incompatible development installation is supported.

### Validation

Confirm the installed chart version and check that workloads, init containers and
SQL hooks reference its image digests, including monitor. Validate the application
journeys on the target platform; local packaging checks do not prove deployment.

### Rollback

Select a previously accepted exact chart version and compatible instance values.
This restores image selection only, not database state; prepare a fresh database
when development schemas are incompatible.

### Limitations

Development charts are not tagged releases and carry no attached operator report.
Paired `code/v*` and `chart/v*` releases retain their report validation. Mutable
`v5-dev` aliases remain available and can advance partially on a failed image build;
the dev chart is published only after the complete build succeeds.
