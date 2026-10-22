## Context

See proposal.md for the motivation. Current state that shapes the approach:

- **Analysis storage.** `cap_ppt_builder_analysis` (`builder/analysis_job.py`), the capability's own table, already stores the template bytes (`template_pptx`), the inventory, the patterns PDF, the labelling key and the lease fields, keyed by agent instance id plus a `team_id`. Re-runs and interrupted-job recovery read the stored bytes, with no user token. Its migrations live in the capability's own `ppt_builder_migrations` tree, applied by `python -m fred_runtime migrate`.
- **Agent template.** It is stored through the per-agent asset slot (`ctx.services.agent_assets`, fred-runtime `AgentConfigAssetsAdapter`), which only exists on the save path. Capability routes get no services.
- **Built-in template.** `builder/builtin.py` ships the deck and its stored rules inventory; the middleware builds on it when `template_sha256 is None`, with no I/O.
- **Authorisation.** Capability routes authorise through `CapabilityTeamAuthorizer.require_agent_editor(team_id)` (fred-runtime `RebacCapabilityTeamAuthorizer`). There is no organisation-level check. Admin > Features is gated by `OrganizationPermission.CAN_MANAGE_CAPABILITIES`, which `schema.fga` defines as `platform_admin or feature_manager`.
- **Vision model port.** `CapabilityModelPort` is only provided on the save path, bound to the agent's team. With no team, `RoutedCapabilityModelPort` applies no usable-models restriction and `profile_id=None` resolves to the pod's default chat profile.
- **Pattern ids** (`layout:{i}`, `slide:{id}`) are positional, so they collide across templates.

## Goals / Non-Goals

**Goals:**
- A steady-state turn makes no extra DB read: the platform default comes from a pod-local snapshot.
- A platform default never changes an agent's readiness.
- Reuse the analysis job, store, review dialog and template panel; no parallel pipeline.

**Non-Goals:**
- Per-team defaults.
- A platform default for the model that labels agent templates.
- The generic `platform_settings_fields` manifest renderer (#2987, part 2).
- Listing capability pod routes in the authz endpoint matrix, which covers control plane and knowledge flow only.

## Decisions

### D1. Capability-owned storage, under a reserved id

**Decision.** The platform template uses two reserved analysis rows, with `team_id = "__platform__"`. Instance ids are UUIDs, so no collision is possible.
- `__platform__` is the template in effect. It is only ever written as a succeeded analysis (an outdated refresh keeps it succeeded, as for agents).
- `__platform_next__` is the replacement: an upload or a re-run analyses it there, while `__platform__` stays in use. When its job succeeds, `finish` moves it onto `__platform__` in the same transaction (delete the current row, rename the candidate's key). A failed or interrupted replacement stays in `__platform_next__`, visible in the drawer, until a re-run, a new upload or a reset.
- The store, job, leases, re-run and recovery are reused unchanged; the promotion is one optional argument of `finish`.
- The admin's vision choice is the row's own labelling key: `vision:agent-default` (the platform's default model), `vision:<profile>`, or `rules`. No settings table.
- No `__platform__` row means the Fred template. "Reset" deletes both rows, so the Fred template cannot be removed.
- Additions: `AnalysisStore.delete`, `AnalysisStore.set_overrides`, and two nullable columns, `template_filename` (so the drawer and the agent form can name the file) and `overrides_json` (the manager's pattern edits, D7). One linear revision in the capability's own `ppt_builder_migrations`.
- The template bytes stay in Postgres, under the same 50 MB limit as an agent template (`MAX_TEMPLATE_UPLOAD_BYTES`).

**Alternative: control-plane ownership.** A new table and blob store, admin routes, an SDK port to fetch the bytes, and cross-service analysis triggers. The analysis must run in the capability pod anyway, so control plane would hold bytes it cannot use. AUTHORING.md also keeps capability state out of control plane. Rejected.

### D2. Routes on the capability router

| Method | Path | Purpose | Authz |
|---|---|---|---|
| GET | `/platform` | Analysis status, summary, inventory and `template_filename`; `analysis: null` while the Fred template is in effect | Authenticated |
| GET | `/platform/patterns.pdf` | Thumbnails; 404 when unset | Authenticated |
| PUT | `/platform/template` | Multipart upload as the replacement, with the vision choice | Capability manager |
| POST | `/platform/analysis` | Re-run, with the vision choice, as the replacement; 404 when unset | Capability manager |
| PUT | `/platform/overrides` | The manager's pattern edits, pruned against the template in effect; 404 without one | Capability manager |
| DELETE | `/platform/template` | Reset to the Fred template: both rows go | Capability manager |

- **`GET /platform`** returns the template in effect (`analysis`, `template_filename`, `overrides`) and the replacement (`replacement`, `replacement_filename`), each `null` when absent; the vision choice is the replacement's, else the current one's. It also restarts an interrupted replacement where this pod can label it, as an agent's readiness check does.
- **A re-run** of a failed or interrupted replacement re-runs it; otherwise it copies the template in effect into the replacement row, so the current analysis stays in use.

- **Reads stay open to any authenticated user**, as `/builtin` is today: the template is not team-scoped.
- **The existing `/analysis/{instance_id}` routes reject the reserved id with a 404.** Otherwise `require_agent_editor("__platform__")` passes when ReBAC is disabled.
- **Upload path.** It reuses the size gate, the readability check and the heavy-job slot of the agent save.

### D3. `require_capability_manager()` on `CapabilityTeamAuthorizer`

**Decision.** A non-abstract method whose default raises 403, so it is additive for existing implementers and fakes.
- `RebacCapabilityTeamAuthorizer` implements it as an organisation check of `CAN_MANAGE_CAPABILITIES` on `ORGANIZATION_ID`.
- It follows the same enforce/disabled rules as `require_agent_editor`.
- It is named after the permission, not after "platform admin", because feature managers pass too: the same gate as Admin > Features.
- The class is not renamed, to avoid churn.

### D4. Teamless model port for capability routes

**Decision.** fred-sdk adds a route dependency, `capability_platform_model(request) -> CapabilityModelPort` (503 when the pod bound none).
- fred-runtime binds it next to the authorizer: one pod-wide `RoutedCapabilityModelPort` with no team, no user token and the routing key `capability:platform`.
- With no team, no usable-models restriction applies. Only capability managers choose this model.
- `profile_id=None` resolves to the pod's default chat profile: the "platform's default model".
- **Known gap:** `platform_chat_model_binding` is not applied, the same as on the save path today.

### D5. The platform template's vision model

**Decision.**
- The upload and the re-run carry `use_vision` and `vision_profile_id`; their labelling key is stored on the platform row. The default is `vision:agent-default`, the platform's default model.
- The analysis requires vision, as for agents: a default model that cannot read images labels by rules.
- Routes remember the teamless port for the reserved id, so interrupted-job recovery and outdated refresh work on any pod that served a platform route.
- Agent labelling is unchanged.

### D6. Build-time resolution through a pod-local snapshot

**Decision.** `analysis_job` keeps one snapshot of the platform default: `(sha, inventory) | None`, with a 30 s TTL.
- A refresh is one primary-key read without the inventory; the inventory comes from the existing LRU (by id, sha and key), and the template bytes from the existing bytes LRU at build time.
- **Only the `__platform__` row is read**, and it is always a succeeded analysis: a replacement being analysed or failed never reaches agents, which keep the previous template on every replica.
- **The manager's pattern edits are applied once per read**, so the snapshot holds the effective inventory and a turn applies nothing.
- **The inventory is cached by the row's job id**, which changes on every analysis: a re-run with the same file and labelling replaces it on every pod.
- **Middleware, branch `template_sha256 is None`:**
  - fresh snapshot: build on it, or on the built-in template when unset, with no I/O;
  - expired snapshot: build on the expired value and refresh it in the background (single flight);
  - no snapshot yet on this pod: take the existing deferred-tool path and refresh in `_resolve`.
- **The writing pod clears its own snapshot at once;** other pods converge within the TTL plus one turn.
- The working rules name "the platform's default template" for every agent without its own, whichever template that is.

**Alternative: fall back to the Fred template while a replacement is analysed.** One row would do, but agents would switch look for the minutes of the analysis, or for good when it fails. The owner chose to keep the previous template (2026-10-22).

**Alternative: a pod-local memory of the previous template.** Replicas do not share it, and a restarted pod has none.

**Alternative: LISTEN/NOTIFY or a per-turn read.** The cost is not justified for an admin-rate change.

### D7. Pattern edits belong to the template they were made on

**Decision.**
- **Agent.** `validate_config` drops overrides when `template_sha256 is None`, instead of pruning them against the built-in inventory, and the middleware ignores any stored ones in that state. This also fixes the existing collision when an agent goes back to no template.
- **Platform.** The manager's edits are stored on the `__platform__` row (`overrides_json`) and apply to every agent that builds on it; agents without their own template have none of their own (owner, 2026-10-22).
- **Re-analysis.** A promotion keeps the current edits pruned against the new inventory when the file is the same (a re-run), and drops them for another file: positional ids would hit unrelated slides.

**Alternative: binding overrides to a template sha.** That means more code, and the agent form never allows editing in the no-template state.

### D8. Control plane exposes what the admin page needs

**Decision.** `CapabilityEnablementItem` gains two fields:
- `route_base_url`, from the catalogue entry;
- `vision_profile_ids`, from `entry.model_vision_profile_ids`, the mirror of `thinking_profile_ids`.

FeaturesPage dispatches the base URLs as `AgentFormBody` does, and builds the vision picker from the model rows. Dated entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md`, plus a regenerated client.

### D9. Frontend: a platform panel registry, not a manifest field

**Decision.**
- **Plugin field.** `CapabilityUiPlugin` gets an optional `platformPanel`, looked up through `platformPanelFor(id)`, which mirrors `configWidgetRegistry`.
- **FeaturesPage.** It shows a settings icon button in the row actions only when a panel exists, and mounts the panel in an `InlineDrawer`.
- **Drawer.** It reuses the template card, the vision selector fed from the admin catalogue, and `PatternReviewDialog` ("Review the slides"), editable for capability managers and saved through `PUT /platform/overrides`. The reset uses `ConfirmationDialog`.
- **Permission.** Writes are shown to capability managers only, from the bootstrap's platform roles.
- **Agent form.** `usePptBuilderAnalysis` queries `/platform` in its no-template branch and shows "Template set by the administrator" with the file name.
- **Upload.** The sanctioned raw multipart `fetch` with the generated response type.

**Why no manifest field.** #2987 part 2 can make a generic `platform_settings_fields` renderer the fallback of the same registry.

## Risks / Trade-offs

- **Up to 30 s of mixed defaults across replicas after a change** → The bound is documented in the drawer and Help Center. The writing pod updates at once.
- **A replacement that keeps failing leaves the previous template in use indefinitely** → The drawer shows the failure and that the previous template stays in use, with re-run and reset.
- **A new file drops the manager's pattern edits** → Positional ids cannot follow another file; the drawer review is where they are made again.
- **The teamless port ignores team model restrictions for the platform template** → Only capability managers choose that model.
- **`platform_chat_model_binding` is not applied to labelling** → This is the existing save-path gap, noted and not widened.
- **A large platform template is stored in Postgres** → The same size limit as agent templates applies, and there is only one row.
- **Dropping overrides with no own template changes behaviour for agents that kept stale overrides** → Those overrides were applied to positionally unrelated slides, so this is a fix. It is mentioned in the migration note.

## Migration Plan

- One Alembic revision in the capability's migrations, applied by `python -m fred_runtime migrate`, as for the other capability tables. It adds two nullable columns.
- **Rollback:** downgrade the revision. Agents fall back to the built-in template.
- **No activation needed:** with no platform default set, behaviour is unchanged except for D7.
- **Migration note:** the #2679 note (operations impact) gains the optional activation and the column.
- **Order:** both changes ship in the #2679 PR; `ppt-builder-capability` is archived before this one.
