## Context

See proposal.md for the motivation and for the terms **scope**, **scope-private setting** and **public setting**. Current state, verified in the code:

- **Agent row.** An agent is an `agent_instance` row: template, name, description, `tuning_json`, with `selected_capability_ids` and one stored `capability_config` envelope per capability. Authorization is team-level: `CAN_UPDATE_AGENTS` is `team_editor`. The personal space is `personal-<uid>`, accepted as `"personal"`, and it skips ReBAC. Names are not unique: no DB constraint, no service check.
- **Create path.** `enroll_agent_instance` checks that the team can use the template (404 otherwise) and each explicit capability (`can_use`, 403 otherwise). It then validates every capability config on its pod (`POST /agents/capabilities/{id}/validate-config`, multipart, with `team_id` and `agent_instance_id`).
- **What the control plane sees of a capability's settings.** Only the catalog's `FieldSpec` list: top-level, visible fields. Some scope-private values are hidden or nested:
  - document-access `document_uids` is not a `FieldSpec`;
  - the ppt-filler `schema_slides[].keys[].folder_tag_id` is nested;
  - MCP server options are extra keys of an open model (`chat_options.bound_library_ids`, declared in `mcp_catalog.yaml`).
- **Configuration files.** They are stored by the pod through `AgentAssetPort` at `teams/{team}/agents/{instance}/config/{key}` in Knowledge Flow storage. They are never copied. Only ppt-filler overrides `validate_config`: on upload it parses the template and resolves image folders to tag ids in the saving team.
- **Duplicate.** The same-team "Duplicate" is rebuilt in the browser. It sends no files, so a duplicated ppt-filler agent passes validation but has no template.
- **Prompt picker.** The prompt copy picker is `ImportPromptDialog`, under the prompt marketplace. Eligibility is `team_editor`, the personal space is always listed, selection is multiple, and it shows one toast per team.

## Goals / Non-Goals

**Goals:**
- One rule, owned by each capability, that says which of its settings may leave its scope.
- A rule that stays valid when projects or organisations become scopes, without revisiting any capability.
- One server-side copy that serves both "Copy to…" and "Duplicate".
- No knowledge of any particular capability in the control plane.

**Non-Goals:**
- Defining projects, organisations or a common "workspace" model. That is to be discussed with the team.
- Copying between scopes that contain one another (for example a team and its organisation). Today scopes are disjoint.
- Agent marketplace and publishing.
- A provenance field on the agent.
- Cleaning up configuration files of deleted agents (existing gap, unchanged).
- Making agent names unique.

## Decisions

### 1. Settings are classified against the scope, not against the team

Every capability setting is either **scope-private** or **public**.
- **Scope-private:** the setting points to an item that exists only inside the scope the agent lives in: a library, a folder, a document, a file. Outside that scope the reference is meaningless, and it can expose the existence or content of another scope's items.
- **Public:** everything else. A tone, a limit, an option flag, a prompt text have the same meaning in any scope.

**Why "scope" and not "team":** the team is today's only shared scope, but not the last. Projects and organisations are expected, possibly as kinds of a common "workspace". The question a capability answers ("does this setting point to something owned by where the agent lives?") is the same for all of them. Naming it after the team would force every capability to be revisited when the next kind of scope arrives. Naming it after the scope makes the classification a durable part of the capability.

**What stays open, deliberately:** when scopes can contain one another, "different scope" may no longer mean "reset". For example, a folder of a team might stay valid in an organisation that contains that team. The classification does not change; only the copy's rule "is the destination the same scope?" would be refined into "can the destination see this item?". That belongs to the workspace discussion, not to this change.

### 2. The classification lives on the capability's own settings model

A capability classifies the fields of its `ConfigModel` with SDK markers. Fields without a marker are public.
- **Scope-private:** `library_tag_ids: ScopePrivate[list[str]] = []`. Pydantic field metadata; nested models are covered, because the marker sits on the nested model's field. A scope-private field must have a default.
- **Configuration file:** `template_key: Annotated[str, AssetKey("template")]`. The field holds the key of a file stored through `agent_assets`, and names the upload slot it came from. The runtime cannot guess this mapping (ppt-filler stores the `template` slot under the `template_key` value), so the capability declares it. A configuration file is scope-private by nature; it is recreated, not reset.
- **Explicit public:** `Public[...]`, for an identifier-like field that is safe to copy (for example the ppt-filler placeholder name `key`).
- **MCP servers:** they have no Python model per server. Their catalog field declares `scope_private: true` (or `false` for explicit public) in `mcp_catalog.yaml`, for `bound_library_ids`. This is a new optional `FieldSpec.scope_private`, applied only to keys that are not fields of a typed model.
- **Guard:** a test lists every identifier-like text field across installed capabilities and MCP catalogs (names ending in `id(s)`, `uid(s)`, `key(s)`, `folder(s)`, `library/libraries`, `tag(s)`, `path(s)`). Each must be classified, or the test fails and names the capability and the field. A capability author cannot forget the question.
- **Why here:** this is where the capability author already declares the setting, and it covers hidden and nested values.
- **Alternatives considered:**
  - A flag on `FieldSpec`: the control plane could read it, but it misses hidden and nested fields.
  - A per-capability "rebind" method: more code in each capability, and easy to forget.
  - A list kept in the control plane: goes stale with each new capability, and makes the central server know capability internals.

### 3. Each capability prepares its own copy; the control plane only orchestrates

A new runtime operation does the preparation.
- **Call:** `POST /agents/capabilities/{id}/copy-config`, JSON. It carries the stored config, the source scope and instance, and the destination scope and instance. Scopes are passed as team ids today.
- **Different scope:** the pod resets every scope-private field to its default, recursively. The capability stays enabled.
- **Same scope:** the pod keeps every field (the "Duplicate" case).
- **Configuration files:** they are scope-private by nature, so they are never shared: they are recreated. The pod reads each `AssetKey` file of the source instance through `AgentAssetPort`, in the source scope. It then runs the capability's normal save, `validate_config`, in the destination scope, with those files as uploads. ppt-filler therefore re-parses its template and resolves folders in the destination, exactly as if an editor had uploaded it there.
- **Result:** the pod returns the stored envelope with `notices`, or a typed rejection.
- **Items the destination lacks:** in another scope the capability's save gets `copied_from_another_scope`. It may then leave such a reference unset instead of rejecting, and add a notice saying what an editor must redo. ppt-filler does this for image folders missing in the destination (found during the manual check: rejecting dropped the whole capability).
- **Permissions:** the user's own token is forwarded. Reading the source files needs `CAN_ACCESS_FILES` on the source, which an editor has. Writing needs `CAN_UPDATE_RESOURCES` on the destination, which is also `team_editor`.
- **Alternative considered:** the control plane downloads the files from Knowledge Flow and resubmits them through `validate-config`. It would have to know asset paths and slot-to-file mapping, which are pod details today. It also needs a Knowledge Flow file client in the control plane.

### 4. Control-plane API

- **Preview:** `GET /control-plane/v1/teams/{team_id}/agent-instances/{agent_instance_id}/copy-targets`. For the personal space and each team where the user is `team_editor`, it returns:
  - `template_enabled`;
  - `missing_capabilities`, as id and display name.

  It reuses the existing `can_team_use_capability` and `can_use` checks, and needs `CAN_UPDATE_AGENTS` on the source.
- **Template visibility:** like enrollment, the source template is looked up with internal templates visible only to a platform admin; otherwise preview and copy answer 404. A source agent with no saved selection (`selected_capability_ids` null) copies the template defaults.
- **Copy:** `POST …/agent-instances/{agent_instance_id}/copy` with `{ target_team_ids: [...], display_name?: str }`.
  - `display_name` is allowed only for a single target equal to the source (the "Duplicate" case).
  - It returns `{ results: [{ team_id, agent?: ManagedAgentInstanceSummary, dropped_capabilities: [...], error? }] }`.
- **Per destination:**
  - Require `CAN_UPDATE_AGENTS` and use the canonical team id it returns. The existing prompt `promote` route stores the raw `"personal"`; this copy must not.
  - Generate the new instance id.
  - Run `copy-config` for every capability the destination can use. A rejection, or a pod without the operation (404), drops the capability and reports it.
  - Then create the row through the same store path as `enroll_agent_instance`.
- **Concurrency:** destinations run concurrently, bounded by a small semaphore, as the prompt import does with `gather`.
- **Errors:** a failed destination never prevents the others, including an unexpected error, which is logged and reported for that destination only.
- **Naming:** the API keeps the existing `teams/{team_id}` path family. When other kinds of scope exist, they get their own routes; the capability operation is already scope-neutral.

### 5. Name

- **Rule:** keep the name if no agent of the destination has it. Otherwise use the first free `<name>_imported-<n>`, with n from 1, checked against `list_by_team` (the prompt import rule).
- **Duplicate:** keeps the user's chosen name, unchanged.
- **Concurrent copies:** two copies at the same time can pick the same name. Names are not unique today, so this is accepted.

### 6. Duplicate uses the copy

`handleDuplicate` calls the copy endpoint with the source team and the chosen name. The browser-side rebuild (`buildAgentFormSubmitPayload` for duplicate) is deleted.

### 7. Frontend picker

- **Shared component:** `ImportPromptDialog` moves to `shared/organisms/CopyToTeamsDialog`. Its inputs:
  - a title;
  - an optional info tooltip;
  - optional per-team status: disabled reason, or a missing-capabilities list;
  - optional explanation text;
  - the submit callback.
- **Prompt marketplace:** passes no status and keeps its behaviour.
- **Agent card:** "Copy to…" opens it with the preview data.
- **Info tooltip:** reuses the label/value tooltip of the AgentCard info icon. It explains in plain words that public settings travel, scope-private ones are reset, and files are recreated.
- **Results:** reported with one toast per team, as for prompts. Dropped capabilities are named in the toast.

### 8. Audit

- **Event:** `agent.copied` is recorded through the existing audit facility. It carries the source agent and scope, the destination scope, the new agent and the user.
- **KPI:** `agent.created_total` stays emitted by the create path.
- **Provenance:** no provenance column.

### 9. Delivery in three PRs

Each PR is reviewable and mergeable on its own, in this order:
1. **Capability SDK and runtime:** markers, `copy-config`, classified fields, guard test, contract entry, authoring docs. Nothing calls it yet.
2. **Control plane:** preview, copy, audit, authz matrix, contract entry, regenerated OpenAPI.
3. **Frontend and Help Center:** shared picker, "Copy to…", Duplicate switch and deletion of its browser rebuild, strings, Help Center.

## Risks / Trade-offs

- **[A capability forgets to classify a setting]** → the guard test fails on any unclassified identifier-like field.
- **[A setting is classified public by mistake]** → the copy would carry a reference that is meaningless in the destination. The guard narrows this to fields an author explicitly declared public, which review sees.
- **[Pods built with an older SDK lack `copy-config`]** → the capability is dropped from the copy and reported as missing. The rest of the agent is copied.
- **[The workspace model changes the copy rule]** → only the "same scope?" check moves; capability classifications stay. See Decision 1.
- **[Files stored but the agent row not created]** → each capability's `copy-config` stores its files before the agent row exists, so a destination that fails later (another capability's error, a store failure) leaves orphan files under an instance id nothing references. Same as when an agent is deleted today: invisible to users, not cleaned up. Cleaning both needs a pod-side delete operation, a separate change (confirmed by the code review).
- **[Large configuration files]** → the pod streams them through the existing Knowledge Flow port. Files are only read once per destination.
- **[A destination changes between preview and copy]** → the copy re-checks every permission and capability. The preview is advisory.

## Migration Plan

- **Database:** no change.
- **Rollout:**
  - The runtime operation ships with the pods (PR 1).
  - The control-plane endpoints (PR 2) and the frontend (PR 3) ship with their images.
  - Older external capability pods keep working: their capabilities are reported as missing when copied.
- **Rollback:** image rollback. Copied agents stay valid.
- **Migration note:** one per PR, `impact: none`.

## Open Questions

- **Workspace model:** whether teams, projects and organisations become kinds of a common "workspace", and how copying behaves between scopes that contain one another. To discuss with the team and Dimitri. This change does not depend on the answer.
