# Migration guide — v3.3.0

Upgrade from: `code/v3.2.0`
Operational impact: **minor** (minimum version: `3.3.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Retire the legacy Python GCU version enum

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/2995-remove-legacy-gcu-enum.md)

### Applicability

Running Fred v3.2.0 deployments, new installations and Python consumers of the user-store API. Earlier installations still need the original enum-to-text migration when upgrading through v3.2.0.

### Prerequisites

Check custom Python integrations for imports of `GcuVersionsType` or enum inputs to `update_gcu_version`.

### Configuration

No configuration changes are required; existing configured version strings remain valid.

### Upgrade

If an external Python consumer imports `GcuVersionsType`, remove that import and replace `GcuVersionsType.V1` with `"v1"` or the configured version string. Pass strings to `update_gcu_version`. Repository callers already do this.

- Running v3.2.0 pods are unaffected until their images are upgraded. For the retirement in this note, normal rolling deployment is sufficient: both versions read and write the same text column, so there is no additional drain, restart order or database revision.
- New installations use the normal migration chain and configure `app.gcu_version` as a string. Historical enum-to-text conversion remains in that chain and does not import the removed Python class.
- Upgrades from before v3.2.0 still follow the [original CGU conversion procedure](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/2972-configurable-gcu-versions.md), including stopping old enum-based readers during schema conversion. This retirement does not relax that earlier requirement.

This change does not require users to accept the terms again. Reacceptance remains tied to a change in the configured version string.

### Validation

Accept the configured terms and confirm `GET /user` reports the same version string in `cguValidated`. Confirm custom Python integrations import and record acceptance successfully.

### Rollback

Use the normal rollback procedure to v3.2.0. Its store also accepts string inputs, and the database representation is unchanged.

### Limitations

`GcuVersionsType` is no longer importable from the user model, `fred_core.users` or `fred_core`. Published v3.2.0 notes describe the compatibility available in that release; this note retires it for the next release. Earlier database upgrade and guarded-downgrade procedures still apply when crossing their original version boundary.

## Add content-free ReAct and Deep LLM stream diagnostics

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/llm-stream-diagnostics.md)

Existing storage and APIs remain compatible; telemetry is emitted through the existing logging and KPI pipeline after normal deployment.

See the source note for applicability, validation and rollback.

## Prepare the v3.3.0 release notes and operator guide

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/prepare-release-3.3.0.md)

This contribution prepares the user-facing notes and consolidated operator guide. All upgrade actions are declared by the included migration notes, with no additional action from release preparation itself.

See the source note for applicability, validation and rollback.

## Retire general-purpose personal, team-shared, and agent file areas

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/retire-mon-espace.md)

### Applicability

Deployments that use the former `Mon espace`, team-shared, or agent-files UI, or call the general-purpose Knowledge Flow `/fs` and SDK interfaces.

### Prerequisites

Export any files in the retired personal or team-shared areas that must remain accessible. Their stored bytes are not deleted or migrated. Inventory external/live ReAct definitions for the retired `artifacts.publish_text` and `resources.fetch_text` tool references and migrate any matches. The separate `fred-samples/apps/document-triage` sample still uses `teams/{team}/shared/triage`; migrate or decommission it before running it against this version.

### Configuration

Remove `enableAllResourceSpaces` from private control-plane and worker Helm overlays. The bundled chart and generated configuration schemas no longer accept it.

### Upgrade

Deploy the frontend, Knowledge Flow, SDK, runtime, and chart together. Team Resources now presents the corpus workspace only. Knowledge Flow rejects `/teams/{team}/users` and `/teams/{team}/shared` before storage access. Generic agent file reading, listing, text publishing, and sharing interfaces in the UI and SDK are retired. HTTP `/fs` read routes remain for the virtual corpus view and can still resolve technical agent paths; authenticated `/fs/upload`, `/fs/download`, and `/fs/delete` remain for PPT Filler configuration assets and outputs. The document APIs remain available.

### Validation

Confirm the Resources page has no personal, team-shared, or agent-files tabs; retired paths are rejected; `list_document_tree` works; and a saved PPT Filler template still produces a downloadable presentation. Check that the frontend bootstrap no longer exposes `enableAllResourceSpaces`.

### Rollback

Roll back the paired code and chart together to restore the former interfaces. No object-store migration or deletion is performed.

### Limitations

This change does not decide when to delete retained objects in retired areas. No deployed-environment inventory of external agent definitions or end-to-end ReAct PPT Filler run is included.

## Split document access into Attachments and Team documents

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/split-attachments-and-team-documents.md)

### Applicability

Existing Fred deployments upgrading to this release, and authors of out-of-tree capabilities that call or implement `DocumentSearchPort.search`.

### Prerequisites

After this PR merges, publish the new library versions before upgrading consumers: the four core Python libraries are `4.4.2`, document access is `0.1.2`, and the frontend packages are `0.1.1-alpha.0`. Every other publishable library under `libs/` also advances by one patch. Publication is a separate maintainer action. External capabilities must migrate the removed SDK keyword before deployment. These library patch increments are explicitly developer-approved despite the API break; this note records the required coordinated upgrade for the paired code/chart release.

### Configuration

No configuration changes are required.

### Upgrade

Deploy Fred normally. The `document_access` capability (shown as "Documents") now has two positive settings, `attachments` and `team_documents`, replacing `show_attach_files_control` and `search_attachments_only`. Stored agents keep their behavior through a compatibility read: paperclip off means team documents only; paperclip on with attachments-only search means attachments only; otherwise both. Each agent is rewritten to the new keys the next time it is saved. A configuration with both sources off is rejected on save; in the agent form, turning off the last source turns "Documents" off instead.

The Simple agent form replaces the "Team resources" pack and its "Search in attachments only" switch with two packs, "Attachments" and "Team documents". The per-turn "Documents only" mode searches whichever sources the agent enables, including session attachments; it is available for attachments-only agents too.

`DocumentSearchPort.search(attachments_only=...)` has been removed immediately.
Replace `attachments_only=True` with `include_attachments=True,
include_team_documents=False`; omit the removed argument for the former
`False` default. Preserve any tighter source ceilings chosen by the caller.
Old calls now raise `TypeError`; no warning or compatibility alias remains.
Out-of-tree implementers must accept the two new keywords. Upgrade SDK and
runtime to `4.4.2` or later together with `fred-capability-document-access>=0.1.2`;
its SDK dependency now requires `fred-sdk[agents]>=4.4.2`. Deploy pods only after
these versions are published.

Behavior changes: a legacy agent with its paperclip off no longer searches
session attachments. "Documents only" (`corpus_only`) now includes attachments
when enabled, bounded by the agent and explicit turn scope. ReAct and Deep agents
receive a document-evidence-only instruction with no general-knowledge fallback;
custom Graph agents must enforce their own answer policy.

### Validation

Open an agent that used "Search in attachments only" and confirm the "Attachments" pack reads on and "Team documents" reads off. In a conversation with that agent, confirm the paperclip is present and "Documents only" is offered and searches attachments without reaching team documents. Check that SDK callers no longer pass `attachments_only`.

### Rollback

Roll back SDK, runtime, capability packages and migrated caller code together; there is no data migration. Agents not re-saved since the upgrade keep working unchanged. An agent re-saved after the upgrade stores only the new keys, which the previous version ignores: it falls back to the defaults (paperclip on, team documents and attachments searched) until it is configured and saved again.

### Limitations

Summarize, verbatim reading and extraction are not bounded by the agent's sources; that ceiling remains an open question in the capability scope RFC.

## Correction: enableAllResourceSpaces is no longer a supported frontend flag

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/correct-2910-frontend-flags.md)

Nothing to do beyond retire-mon-espace, which already tells operators to remove enableAllResourceSpaces from their overlays.

See the source note for applicability, validation and rollback.

## Retire the corpus manager API and unused corpus and filesystem MCP servers

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/retire-corpus-filesystem-mcp.md)

### Applicability

Fred deployments that expose the Knowledge Flow corpus or filesystem MCP server, call the `/corpus/*` maintenance API, or set `mcp.filesystem_enabled` in a custom values/configuration overlay.

### Prerequisites

Check custom agent definitions for `mcp-knowledge-flow-corpus` and `mcp-knowledge-flow-fs`. Replace document discovery with the `document_access` capability and its `list_document_tree` tool. Review any other use of the retired MCPs before upgrade.

Identify scripts or dashboards calling `/corpus/*`, including revectorization and vector-metadata repair. Complete any already-started revectorization or repair Temporal workflows before deploying workers without those workflow and activity registrations.

### Configuration

Remove `mcp.filesystem_enabled` from custom Knowledge Flow configuration and Helm values overlays. The remaining filesystem read limits still configure retained HTTP `/fs` reads, including the virtual corpus view.

### Upgrade

Complete the prerequisites and configuration cleanup in this note, the [file-area retirement](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/retire-mon-espace.md), and the [document-source SDK migration](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/split-attachments-and-team-documents.md) before one coordinated rollout. These procedures are not independent deployments. Deploy the updated agent pod catalog, Knowledge Flow API and Temporal workers, frontend and paired chart together. The retired MCP endpoints and SDK constants and all `/corpus/*` maintenance routes are unavailable after upgrade. The retained virtual-corpus reads and technical PPT binary upload/download/delete routes under `/fs`, `/documents/tree`, and ordinary ingestion routes remain available. See the [file-area migration](https://github.com/ThalesGroup/fred/blob/code/v3.3.0/docs/swift/ops/migrations/retire-mon-espace.md) for the other retired `/fs` operations.

Historical vector-metadata repair tasks remain in task storage. Their dedicated result counters remain in the stored task record, but the current task API omits them and Task Activity no longer displays the repair report. Export those task records before upgrade if the counters are needed operationally.

### Validation

Confirm the agent tool picker has no corpus or filesystem MCP entry; `/knowledge-flow/v1/mcp-corpus`, `/knowledge-flow/v1/mcp-fs`, and `/knowledge-flow/v1/corpus/*` are absent. Confirm `list_document_tree` still lists indexed documents and a PPT Filler template can still produce a downloadable presentation.

### Rollback

Roll back the agent pod catalog, Knowledge Flow API and workers, and frontend together. No stored files or corpus data are migrated or deleted by this change.

### Limitations

Saved agent selections naming a retired MCP must be updated before those agents can use their configured tools. The retired maintenance operations have no replacement endpoint in this change. Direct HTTP `/fs` retains virtual-corpus reads and technical agent-path reads plus the PPT binary transport after the general-purpose file-area retirement; it no longer serves the retired personal or team-shared paths.
