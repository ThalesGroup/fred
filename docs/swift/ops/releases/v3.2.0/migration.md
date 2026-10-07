# Migration guide — v3.2.0

Upgrade from: `code/v3.1.1`
Operational impact: **minor** (minimum version: `3.2.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Shared UI components and retirement of the built-in evaluator

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2887-hosted-ui-components.md)

### Applicability

Fred deployments using built-in evaluations before upgrading to v3.2.0, including
the evaluator removal tracked by #2904. Deployments not using evaluations need
no evaluator setup.

### Prerequisites

For deployments using evaluations, this migration is blocked until the standalone evaluator enforces team membership and application grants on every API operation, including direct access through the legacy `/evaluation/` proxy. In addition, preserve the operation-specific ReBAC checks in the [product contract](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md): `CAN_READ` to view evaluations, `CAN_UPDATE_AGENTS` to create or cancel them, and `CAN_READ_CONVERSATIONS` to evaluate real conversations. Team membership and the application grant do not replace those permissions. Apps admission and the application gateway do not provide this API authorization. Do not treat the currently documented authentication-only evaluator as meeting this prerequisite. Verify the deployed evaluator implementation before rollout.

After that prerequisite is met, deploy and register the standalone fred-agent-evaluator application before upgrading Fred. Follow the existing [application deployment contract](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/platform/FORKING_GUIDE.md); grant the intended teams access through the existing application permissions. Preserve the evaluator service and its database.

### Configuration

No new configuration fields are introduced. Existing application registration and ingress/proxy settings must expose the evaluator UI and API. Deployments already using the evaluator through Apps need no further configuration. Deployments not using evaluations can upgrade normally.

### Upgrade

Only after the authorization prerequisite is verified, validate that an authorized team can open the evaluator through Apps, then deploy Fred. The built-in Evaluations settings entry, screens and direct evaluator task polling are removed. Use Apps to inspect evaluation runs and progress; the old settings URL falls back to Members.

### Validation

Confirm Apps opens the evaluator for an authorized team. Independently verify that direct API requests from authenticated users without the target team membership or application grant are denied, through both the application gateway and legacy `/evaluation/` path. For a member of a granted team, also verify denial of viewing without `CAN_READ`, creation/cancellation without `CAN_UPDATE_AGENTS`, and real-conversation evaluation without `CAN_READ_CONVERSATIONS`, through both paths; verify permitted operations succeed for appropriately authorized users. An Apps admission check alone is insufficient; failed or missing API authorization blocks rollout. Verify Members and Activity still work and Fred no longer calls `/evaluation/v1` directly. The shared UI package must pass archive/consumer validation; StatusBadge and other reusable exports remain available.

In the evaluation application, click a run row to open its preview, close the case drawer using its localized close action, and inspect outcome KPI values in both themes.

### Rollback

Restore the previous Fred frontend image to recover the built-in screens. Keep the evaluator service, application registration and data; this change introduces no data migration or deletion.

### Limitations

Publishing the frontend npm packages is a separate operation; the final
candidates in this release are aligned on alpha.4. The UI package's hosted surface is limited to what hosted applications use: `DataTable` without row selection, a single overlay `InlineDrawer`, and `ToastProvider`/`useToast`; `TablePagination` and the direct `Toast` are not exported. The removal does not publish packages, deploy the external evaluator, change evaluation permissions or delete historical evaluations.

## Explicitly continue unfinished Graph work

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2892-resume-interrupted-graph-execution.md)

No schema or data migration: continuation uses existing checkpoints and PostgreSQL or local file-backed SQLite locks. Keep one active execution per conversation; an interrupted step may repeat an external effect, so agent authors must ensure idempotency as described in the source note.

See the source note for applicability, validation and rollback.

## Align frontend npm package candidates on alpha.4

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2894-frontend-packages-alpha4-alignment.md)

Fred deployments consume the canonical frontend sources, not these npm archives; aligning an unpublished token version does not change deployed behavior.

See the source note for applicability, validation and rollback.

## Remove unused task tray and retired frontend flags

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2910-remove-unused-task-tray.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

Review private control-plane backend and worker values overlays for `platform.frontend.feature_flags` before installing the new chart.

### Configuration

Keep only `enableApplications` and `enableInformationSystems` under `platform.frontend.feature_flags`. Remove any other keys from both application overlays. The bundled Helm values already contain the supported default-off flags.

### Upgrade

Apply the overlay cleanup and validate the values against the new chart schema before the [coordinated release upgrade](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md). This flag cleanup adds no data migration of its own.

### Validation

Confirm chart values validation passes. Check that `/control-plane/v1/frontend/bootstrap` exposes the two supported flags and that the admin Tasks and migration task pages still show task rows, statuses, and acknowledgements.

### Rollback

Restore the previous paired chart and code using the normal rollback procedure. Pruned overlay keys do not need to be restored.

### Limitations

Any private overlay that still sets an unsupported frontend flag fails strict chart validation until the key is removed.

## Prioritize Other text in HITL answers

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2924-hitl-other-answer-priority.md)

Normal frontend deployment is sufficient; existing HITL requests, responses, and APIs remain compatible.

See the source note for applicability, validation and rollback.

## Upgrade urllib3, PyJWT, virtualenv and DOMPurify to patched versions

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2956-remaining-dependabot-alerts.md)

These are patch-level dependency upgrades already used by the other backends; data, APIs and deployment order are unchanged.

See the source note for applicability, validation and rollback.

## Deploy local k3d Fred with Helmfile

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2957-local-k3d-helmfile.md)

### Applicability

Developers using fred-deployment-factory to build and deploy Fred on local k3d.
Other deployments use their normal procedure.

### Prerequisites

Use matching Fred and deployment-factory checkouts with the Helmfile workflow.
Install Helmfile from its official release with checksum verification; the tested
versions are Helmfile 1.8.1 and Helm 3.21.2. Keep the existing k3d cluster and volumes.

### Configuration

Fred's k3d installation now lives in this repository, in `deploy/k3d/`:
`helmfile.yaml.gotmpl` (the `fred-app` release), `values.yaml` (moved from the factory's
`k3d-apps/fred/values.yaml`, unchanged), and the `build`, `prepare` and `finish` hooks the
factory runs. The chart comes from this checkout; the former `FRED_CHART`,
`FRED_CHART_VERSION`, `FRED_VALUES` and `FRED_DIR` options are gone. Extra values files go
in the factory's `VALUES`. Model credentials remain outside Git in the existing secret.

### Upgrade

In the factory, replace `make k3d-fred FRED_DIR=/path/to/fred` with
`make k3d-app DIR=/path/to/fred`, and `make k3d-evaluator` with
`make k3d-app DIR=/path/to/fred-agent-evaluator`. `make k3d-app-validate DIR=...` checks
without building or changing the cluster. A local edit to the factory's
`k3d-apps/fred/values.yaml` moves to `deploy/k3d/values.yaml` here. The existing release
is upgraded; no cluster recreation or data migration is required. Initial bootstrap
guidance now prints a token-retrieval command instead of the token.

### Validation

Confirm validation succeeds, then all six Fred deployments become ready. Verify
each worker uses its backend's image, Fred opens at the configured local URL and
Grafana has Fred's dashboards. Rerunning the deploy must preserve data and keep
unchanged image content on the same tags.

### Rollback

Restore the previous Fred and factory code together. If application rollback is
needed, use the previous known deployed Fred Helm revision. Do not uninstall the
infrastructure or delete persistent volumes.

### Limitations

This change covers Fred on local k3d only. It does not migrate Maxwell, evaluator,
infrastructure lifecycle or other environments. Existing-cluster testing does not
establish installation on an empty cluster.

## Run PR image scans after builds with Trivy v0.75.0

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2961-trivy-post-build.md)

PR scans run in dedicated jobs; deployed images, APIs and data are unchanged.

See the source note for applicability, validation and rollback.

## Keep pending administrator contacts visible on marketplace team cards

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2968-marketplace-pending-admin-contacts.md)

Existing pending relations and user summaries are reused; normal deployment enables the display fix without data migration or client changes.

See the source note for applicability, validation and rollback.

## Keep literal comparisons in the writable-document rich-text editor

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2979-writable-document-markdown-import.md)

Existing documents, APIs and exports are unchanged; Markdown preparation takes effect with normal frontend deployment.

See the source note for applicability, validation and rollback.

## Control plane endpoints to copy an agent to other teams or the personal space

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/agent-copy-endpoints.md)

Agent-copy endpoints are additive, use the existing agent table and call the matching pods' copy-config operation; the frontend copy action ships in this release.

See the source note for applicability, validation and rollback.

## Copy an agent to other teams or the personal space from the agent card

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/agent-copy-ui.md)

The feature uses the control plane and agent pod operations shipped with it; existing agents are unchanged and Duplicate now goes through the same server copy.

See the source note for applicability, validation and rollback.

## Refresh agent lists after a capability is enabled or disabled

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/agent-list-refresh-after-capability-toggle.md)

The admin capabilities page now refreshes the affected agent lists by itself.

See the source note for applicability, validation and rollback.

## Remember the agents page sort in the browser

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/agent-sort-remembered.md)

The chosen sort is stored per browser; no server, database or configuration change.

See the source note for applicability, validation and rollback.

## Capabilities classify their settings by scope and can prepare a copy of their configuration

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/capability-config-copy.md)

The copy-config endpoint is additive and is used by agent copying in this release; normal deployment keeps existing agent configurations valid. Custom catalogs should mark team-private library fields before cross-team copies.

See the source note for applicability, validation and rollback.

## Build only the Docker images a pull request affects

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/ci-affected-docker-images.md)

Only pull-request CI selection changes; images, releases and deployments are unchanged.

See the source note for applicability, validation and rollback.

## Keep team membership when the final elevated role is revoked

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/demote-sole-team-role-to-member.md)

Existing team data and API request shapes remain valid; the new behavior takes effect with the normal control-plane deployment.

See the source note for applicability, validation and rollback.

## Prepare new library release versions

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/library-patch-releases.md)

Version preparation does not publish packages or change runtime behavior; existing deployments use the normal upgrade procedure.

See the source note for applicability, validation and rollback.

## Combine resource capabilities and enable tabular conversation attachments

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/merge-attachments-resource-pack.md)

Existing agent selections remain unchanged; new Excel attachments use the existing processors automatically. Older Excel attachments stay text-backed; reattach a file only if its new tabular tools are wanted.

See the source note for applicability, validation and rollback.

## Rework the neutral palette, surfaces, text and outlines of the frontend themes

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/neutral-surface-scale.md)

The new colors ship with the frontend image; no operator or user step is needed.

See the source note for applicability, validation and rollback.

## Specify the organizations and projects target model (RFC only)

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/organizations-and-projects-specification.md)

A design document only; nothing deployed reads it, so a normal deployment is unaffected.

See the source note for applicability, validation and rollback.

## Follow task progress with batched reads instead of one stream per task

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/poll-task-progress-in-batches.md)

The API change is additive, no data or schema changes, and the frontend switches transport on a normal deployment.

See the source note for applicability, validation and rollback.

## Scan pull request Docker images with Trivy

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/pr-image-trivy-scan.md)

The scan runs in CI on pull requests and does not change released images, application data, or runtime behavior.

See the source note for applicability, validation and rollback.

## Reduce critical CVEs in production Python images

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/production-image-critical-cve-remediation.md)

Updated images deploy through the normal release process; data and APIs are unchanged.

See the source note for applicability, validation and rollback.

## Name the prompt marketplace action "Import into…"

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/prompt-marketplace-import-wording.md)

Only the labels of the prompt marketplace import action change.

See the source note for applicability, validation and rollback.

## Preload OCR models without ONNX Runtime build warnings

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/quiet-ocr-model-preload.md)

The image contains the same OCR model packages and recognition dictionary, so normal deployment is sufficient.

See the source note for applicability, validation and rollback.

## Center the user avatar at the bottom of the navigation rail

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/rail-avatar-alignment.md)

The fix ships with the frontend image; no operator or user step is needed.

See the source note for applicability, validation and rollback.

## Plan team and project corpus authorization

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/rebac-target-planning.md)

This PR implements no model, API or data changes; no operator action is needed.

See the source note for applicability, validation and rollback.

## Prepare v3.2.0 release documents and audit dependency updates

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/release-v3.2.0-preparation.md)

Release preparation adds no runtime change. Reviewed npm and Python dependency updates require no data migration, re-ingestion or additional configuration; release-wide operations are declared in their respective source notes.

See the source note for applicability, validation and rollback.

## Sidebar rail and nav panel, denser agents, prompts and resources pages

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/sidebar-rail-and-page-density.md)

The new layout ships with the frontend image; no operator or user step is needed.

See the source note for applicability, validation and rollback.

## Apply the UI theme before the first paint and make every theme self-contained

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/ui-themes-as-peers.md)

The theme boot script ships with the frontend image and preserves stored choices. Custom proxies must permit /theme-boot.js; external token consumers follow the separate neutral-palette migration guidance.

See the source note for applicability, validation and rollback.

## Package MCP catalogs and retire legacy local MCP tools

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/extract-mcp-agent-instructions.md)

### Applicability

Fred agent pods, the control-plane and deployments using the Fred Helm chart.
Custom catalogs/templates using local MCP providers also need updating.

### Prerequisites

Back up `agent_instance` data before migration and quiesce control-plane agent
writes until the migration and pod deployment are complete. Use matching images
and chart values containing this change.

### Configuration

The installed `fred-capability-mcp` package contains one `mcp_catalog.yaml`
with Fred / Knowledge Flow servers only. The pod discovers it through
`fred.mcp_catalogs`. The Fred chart mounts `mcp_catalog_external.yaml` to add
deployment-owned MCP servers; its default `servers: []` leaves the packaged
servers unchanged. Move third-party entries from the old
`applications.fred-agents.mcp_catalog` value to
`applications.fred-agents.mcp_catalog_external`. The old Helm key is no longer
accepted. Mark custom `chat_options.bound_library_ids` fields with
`scope_private: true` before cross-team agent copies, as explained in the
[configuration-copy note](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/capability-config-copy.md). Duplicate IDs across
installed and external servers fail startup.
The production image includes a default `models_catalog.yaml`; the Fred chart
mounts its configured catalog from `applications.fred-agents.models_catalog` at
the same path. Deployments without this chart can use the image default, mount
another file at `/app/config/models_catalog.yaml`, or set
`FRED_MODELS_CATALOG_FILE` to its path.
`FRED_MCP_CATALOG_FILE` still overrides an existing `./config/mcp_catalog.yaml`,
and either replaces the entire packaged list. `servers: []` disables all MCPs;
an explicitly selected missing file retains the previous no-MCP behavior.
`FRED_MCP_EXTERNAL_CATALOG_FILE` selects the additive file; an explicitly
selected missing file fails startup.

Internal HTTP entries use `service: knowledge_flow` and an API-relative `path`.
The existing `ai.knowledge_flow_url` supplies the scheme, host, port and API prefix.
`service: control_plane` uses `platform.control_plane_url`. A concrete `url`
remains supported, but cannot be combined with `service`.

The optional `prompt_file` reads UTF-8 from `pkg://package/path.md`, an absolute
path or a path relative to the catalog. It cannot accompany non-null inline
`agent_instructions`; unreadable files fail startup. The package includes
`prompts/tabular.md`; it is active with the packaged catalog. Custom
files must be mounted or packaged and are read at startup.

`transport: inprocess` is no longer accepted. Remove local-provider entries from
custom catalogs and implement local tools as native capabilities. Remove custom
references to `MCP_SERVER_KNOWLEDGE_FLOW_TEXT`; it is no longer exported by the SDK.
The default RAG and GitHub MCP entries have been removed, together with the unused
`prompts/document-search.md` resource. The GitHub entry had no implementation.

Canonical Python imports are `fred_sdk.contracts.capability.mcp` and
`fred_sdk.resources.mcp`; runtime imports remain compatibility re-exports.
Catalog entry points receive `fred_sdk.contracts.services.ServiceEndpointsPort`.
Live remote transport remains in `fred-runtime`.

### Upgrade

1. Back up agent data and pause agent writes. Move third-party entries from the
   old Helm `mcp_catalog` value to `mcp_catalog_external`; remove obsolete local
   MCP entries and prompt references from custom files before updating pods.
2. Check the control-plane database revision with `alembic current`. If it is
   before `ba2c3c7fd0c1`, use the single coordinated upgrade in the
   [CGU note](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md); do not migrate with old readers
   still running.
   Revision `ba2c3c7fd0c1` removes `mcp-knowledge-flow-mcp-text` and
   `mcp-web-github-readonly`, including both historical `mcp:`-prefixed forms,
   from `selected_capability_ids` and `capability_config`. Unrelated tuning,
   ordering, grants, enabled/suspension flags and audit fields are preserved.
   No replacement capability is added. If `alembic current` shows exactly
   `ba2c3c7fd0c1` as the sole applied head from before the GitHub cleanup,
   `upgrade head` alone will not replay it. With agent writes paused and a
   backup available, use the same code/image version that originally applied
   this revision to run `alembic downgrade -1`. Its downgrade is a no-op for
   agent tuning and returns to that version's actual predecessor. Then switch
   to the updated code/image and run the coordinated upgrade with old readers
   stopped as described in the CGU note. The revision now
   follows `a7e9c2d41063`; older feature builds followed `c4d7e2a91b30`
   or `21e235382895`. Using
   the original version for the downgrade ensures the intervening migrations
   are applied by the subsequent upgrade. Do not use this replay procedure if
   the database is at a later or divergent revision: it would also downgrade
   other migrations.
3. Deploy the updated pods and chart in the coordinated upgrade, then resume traffic
   and agent writes after validation. ReAct RAG, Mindmap and
   Comparison keep their IDs but default to `document_access`. Stored selections
   that are null/absent still inherit defaults; explicit empty lists remain empty.
4. Where desired, explicitly select and authorize `document_access` for agents
   whose old explicit RAG selection was removed. An explicit selection containing
   only retired MCPs becomes `[]`. Review suspended instances through normal
   administration; the migration does not unsuspend them.

### Validation

Confirm the control-plane is at migration head and inspect migration diagnostics
for skipped non-object or malformed JSON rows. Repair those rows through normal
administration before relying on the cleanup. A concurrent tuning edit aborts the
migration; pause writes and retry. Running the revision again makes no further changes.

Render the Helm chart and load the packaged MCP catalog in the new image. Neither retired
server should appear; `document_access` should be available under the normal team
policy. Test document search on an authorized agent and a remaining remote MCP.

### Rollback

For a full rollback to v3.1.1, follow the
[coordinated rollback](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md), including the CGU
downgrade guard, before restarting old readers. Roll back images and chart
together and restore affected tuning from the backup if needed. Alembic
downgrade does not reconstruct removed selections/configuration.
Restore literal URLs and inline instructions before using symbolic/file-reference
catalogs with an older runtime. Do not overwrite newer agent edits during restoration.

### Limitations

The migration cannot repair malformed tuning, grant replacement capabilities or
remove historical OpenFGA tuples. Native document search and its shared Knowledge
Flow client remain supported. MCP `sse`/`websocket` identifiers retain their existing
configuration support; this change does not implement those connection paths.

## Retire the legacy corpus and general-purpose filesystem surfaces

Impact: **major** · [MCP and corpus migration](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/retire-corpus-filesystem-mcp.md) · [file-area migration](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/retire-mon-espace.md)

Before upgrading, export needed personal or team-shared files, remove the retired
corpus/filesystem MCP selections and `mcp.filesystem_enabled`, and migrate
external callers of `/corpus/*`, `artifacts.publish_text`, and
`resources.fetch_text`. Remove `enableAllResourceSpaces` from private overlays.
Let in-flight revectorization and vector-repair workflows finish. The separate
`fred-samples` document-triage sample still targets the retired shared area;
migrate or decommission it before use with this release.

The Resources page now shows only the corpus. PPT Filler's technical template
and generated-file transport, `list_document_tree`, corpus and attachment APIs,
Deep conversation files, Wiki, and writable documents remain available. No
stored objects are deleted by this cleanup. Follow both source notes for
validation and coordinated rollback.

## Store the latest configurable CGU acceptance in users

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md)

### Applicability

Deployments upgrading control-plane and the backends sharing the Fred users
table, whether or not CGU gating is currently enabled.

### Prerequisites

Back up the shared database, agent tuning and chart values. Complete the
[frontend flag cleanup](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2910-remove-unused-task-tray.md) and
[MCP catalog preparation](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/extract-mcp-agent-instructions.md) before deployment.
Deploy backend versions together: the old ORM expects an enum, while the new
version reads text.

### Configuration

No configuration changes are required. Existing `v1` stays valid. Use a new,
case-sensitive `app.gcu_version` identifier only when publishing new terms.
Configure the same active CGU version in all enforcing backends.

### Upgrade

1. Pause new traffic and agent edits, drain in-flight work, then stop old
   control-plane, knowledge-flow and agent backends and their workers that read
   the shared users table. Do not mix old and new readers during this migration.
2. For databases already at the retired-MCP revision from a prerelease build,
   first follow the conditional replay procedure in the
   [MCP note](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/extract-mcp-agent-instructions.md), using its original image for
   the no-op downgrade. Ordinary upgrades from `code/v3.1.1` skip this replay.
3. Run the normal control-plane `alembic upgrade head` once with the new release,
   while old readers remain stopped. The linear chain applies prompt favorites,
   UI settings, local identity snapshots, CGU conversion, retired-MCP cleanup
   and profile pictures, ending at `aac66348e27b`. Revision `a7e9c2d41063`, after
   `b4e8d2a9c613`, converts `users.gcuVersionAccepted` from enum `V1` to text `v1`.
   It creates no tables or columns itself. The other backend migration trees
   have no new revisions in this release.
4. Start matching updated backends, workers and frontend with the paired chart,
   validate the database head and services, then resume traffic and agent edits.
   Do not re-ingest documents or conversation attachments for this upgrade.

### Validation

Confirm legacy accepted versions read as `v1` and acceptance dates and storage
counters are preserved. On isolated validation data, configure an unaccepted
`v2`: protected human requests return 403 until `POST /gcu` succeeds, then
`GET /user` returns `cguValidated: "v2"`. Return configuration to `v1` and
confirm access requires acceptance again because the stored version is `v2`.
Default-team enrollment must not repeat. Confirm no acceptance-history table
was created and the identity snapshot fields remain intact.

### Rollback

Stop updated readers before any database downgrade. For a full rollback to
v3.1.1, apply the normal reverse migration chain with the new image, including
the CGU guard below, before restarting the old readers. New favorites, theme
settings and avatar references are lost if their tables or columns are dropped;
stored avatar objects remain. Removed legacy MCP selections require restoring
agent tuning from the backup and are not recreated by downgrade.

Downgrading `a7e9c2d41063` restores the
old enum only when every current stored acceptance is `v1` or null; it refuses
other versions before changing schema or data. If a current newer acceptance
must be retained, restore a coordinated pre-upgrade backup or make a separate,
explicit data decision. Do not delete consent records to bypass the guard.

### Limitations

Historical timestamps missing in legacy data remain null; they are not invented.
Only the latest CGU version and timestamp are retained, matching the original
GCU policy. External consumers of `UserRow.gcuVersionAccepted`
must now read a string rather than `.value`. `GcuVersionsType.V1` remains accepted
as legacy input to the user store. The existing user-store interface is retained.

The administrator charter already has per-version acceptance. Its team-scoped
gate and startup reconciliation remain unchanged; changing a charter version
requires control-plane restart and refreshed team data.

## Configure OIDC identity providers and a local user directory

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2862-configurable-oidc-providers.md)

### Applicability

Existing Fred deployments retain their Keycloak provider and directory by default. These steps also apply to operators choosing another OIDC issuer and Fred's local user directory.

### Prerequisites

Back up the Fred database and current chart values. For optional OIDC activation, register a browser client and separate confidential workload clients with the provider, grant the required API scopes and roles, and store workload credentials in deployment secrets. Confirm that the issuer's discovery document and token endpoints are reachable from Fred. For local-directory deployments, select an OpenFGA model supporting `suspended: [user]` on `organization:fred` before starting the services, even when delegation is disabled.

### Configuration

For an ordinary Keycloak upgrade, keep the existing provider and directory settings. To activate another issuer, set `security.user.provider` and `security.m2m.provider` to `oidc`, their `realm_url` values to the issuer URL, and `security.user_directory` to `local` consistently across the backends. Configure the API audience, browser scope, workload scope, identity and role claim paths, delegation settings and permitted origins for the provider. Use the [identity-provider guide](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/platform/IDENTITY-PROVIDERS.md) for the Entra recipe, its local configuration generator, the factory-provisioned ZITADEL profile and generic OIDC checks. Keep confidential client secrets outside chart values.

### Upgrade

Follow the [coordinated database upgrade](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md), which includes the nullable identity snapshot columns, before enabling the local directory. Deploy the matching application and chart versions together. Existing Keycloak deployments can retain their configuration. For optional OIDC activation, update the provider configuration on all backends together, then restart the affected workloads and begin with a fresh browser session. Keep the issuer and identity claim stable after activation because they determine Fred user IDs.

### Validation

With the existing Keycloak configuration, sign in as platform administrator and run the platform self-test. For Entra, provide tenant and public client IDs to the local generator and set workload secrets and the 6000-second token lifetime in the environment. For ZITADEL, use the factory provisioner to generate client IDs, credentials and complete local configurations. For each optional provider, verify issuer discovery and backend startup, sign in as administrator, confirm the displayed identity and local-directory search, run the platform self-test, then check token refresh, agent document access through delegation and logout. Delete a disposable local-directory person with delegation disabled and verify that their existing bearer is refused on the next request while an active bystander retains access. Provider accounts and memberships remain stored. Disabled suspension returns 403 `account_suspension_disabled`; unavailable account-status checks return 503 `account_status_unavailable`. For username-based imports, check that referenced local usernames resolve uniquely. A known collision fails preflight with `ambiguous_username` before bundle SQL/OpenFGA writes; update the conflicting profiles against the provider before retrying. Unrelated collisions do not block the bundle. Record the result before production rollout.

For both Keycloak and generic OIDC, verify that a definitive renewal refusal (such as `invalid_grant`) clears the live credentials and stored OIDC user; reload must require sign-in. During a transient provider outage or timeout, an unexpired bearer remains available and renewal can be retried. No late response may replace a newer accepted session. Storage cleanup failure revokes the current in-memory session; it cannot guarantee persistent removal while browser storage is unavailable.

### Rollback

A provider-only rollback can restore the prior Keycloak configuration while keeping the v3.2.0 application and chart. For a full rollback to v3.1.1, follow the [coordinated rollback](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md), including its CGU downgrade guard, before restarting old readers. Nullable identity snapshot columns can remain only if the selected database rollback target retains them; a full reverse migration chain drops them. Switching an activated deployment back to a previous issuer may produce different Fred user IDs and will not automatically transfer personal spaces or authorization state.

### Limitations

The local directory contains people who have signed in; it cannot create or delete accounts at the identity provider. Fred suspends a deleted local-directory user. Snapshots can become stale after a rename; collision rejection does not verify current ownership of a username that appears unique. Provider-specific refresh behavior needs validation, and changing the issuer or identity claim changes UUIDv5-derived user IDs. Manual provider walkthroughs remain required before production activation.

## Let platform admins set the default UI theme and hide themes

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/platform-ui-theme-settings.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

The [coordinated database upgrade](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md) creates
`platform_ui_settings` before the new control plane serves traffic. No separate
migration run is needed. The table holds no row until an administrator saves
the settings.

The public `GET /control-plane/v1/frontend/config` gains an optional
`ui_themes` field (theme ids only). Proxies that filter that response must let
it through.

### Validation

As a platform admin, open **Administration** → **User interface**, set Cobalt as
the default theme and save. In a private window, sign in as a user who never
chose a theme: the application opens directly in Cobalt.

### Rollback

Use the normal rollback procedure. The previous version ignores the
`platform_ui_settings` table; users fall back to their own theme choice.

### Limitations

A settings change applies to each user at their next load of the application,
not to sessions already open.

## Users can mark library prompts as favorites

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/prompt-favorites.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

The [coordinated database upgrade](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md) includes
revision `d7822fba0d40`, which creates the empty `prompt_favorite` table, with
a foreign key to `prompt` and an index on `prompt_id`. It does not rewrite
existing prompt rows. No separate migration run is needed.

The table holds personal data (which prompts a user starred). Rows are deleted
with their prompt, when the user leaves or is removed from the prompt's team,
and when the user's account is deleted through `DELETE /users/{user_id}`.

New API surface, additive only: `PUT` and `DELETE
/control-plane/v1/teams/{team_id}/prompts/{prompt_id}/favorite`, and an
`is_favorite` field on prompt listings.

### Validation

After the full release upgrade, `alembic_version_control_plane` holds
`aac66348e27b`; `d7822fba0d40` is an intermediate revision, not the final head. In the
UI, star a prompt on the Prompts page: the star stays filled after a reload, and
the Favorites filter lists it.

### Rollback

Use the normal rollback procedure. The Alembic downgrade drops the
`prompt_favorite` table and with it every user's favorites; an older release
ignores the table if it is left in place.

### Limitations

No additional migration limitations identified for this change.

## People can set their own profile picture

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/user-profile-picture.md)

### Applicability

All Fred deployments upgrading the control-plane backend and frontend.

### Prerequisites

Grant the control plane's content-bucket credentials permission to delete
objects, in addition to the read and write they already need:

- MinIO / SeaweedFS / S3: `s3:DeleteObject` on the content bucket.
- GCS: `storage.objects.delete` on the content bucket.

Without it, uploads and deletions still succeed, but each replaced or removed
picture stays in the bucket and the control plane logs a warning naming the
user id.

### Configuration

No configuration changes are required.

### Upgrade

The [coordinated database upgrade](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md) includes
`aac66348e27b`, which adds the nullable `users.avatar_object_storage_key`
column. No separate migration run or backfill is needed; everyone starts
without a picture. Check the delete permission above before enabling picture
replacement and deletion.

The crop editor now exports team avatars and profile pictures at 192x192
(WebP, quality 0.85) instead of 320x320. Existing team avatars are unchanged.

### Validation

Open **Profile → Settings**, import a picture and save the crop: it appears in
the navigation panel. Replace it, then delete it, and check in the content
bucket that no object remains under `users/<your user id>/`.

### Rollback

With traffic paused and updated readers stopped, downgrading to
`ba2c3c7fd0c1` drops only the picture column. A full rollback to v3.1.1 must
follow the [coordinated rollback](https://github.com/ThalesGroup/fred/blob/code/v3.2.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md), including
the CGU guard, before restarting the previous images. Pictures already uploaded stay in the content bucket
under `users/`, unreferenced; delete that prefix by hand if needed.

### Limitations

- Profile pictures are not part of the platform export/import: people are not
  exported, so after an import into a new platform everyone starts without a
  picture.
- The local filesystem content store serves no URLs, so pictures are stored but
  initials stay displayed, as for team avatars.
- When the Keycloak admin client is not configured, team administrator
  summaries carry no names and no pictures.
