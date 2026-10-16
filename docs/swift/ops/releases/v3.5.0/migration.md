# Migration guide — v3.5.0

Upgrade from: `code/v3.4.0`
Operational impact: **minor** (minimum version: `3.5.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Coordinated v3.5.0 upgrade and rollback

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/000-v3-5-0-release-preparation.md)

### Applicability

Upgrade from Fred v3.4.0 to v3.5.0 with paired code and chart releases. This
sequence combines the procedures below; it adds no migration of its own.

### Prerequisites

Back up the shared PostgreSQL database and keep the previous images, chart,
values, model catalog and OpenFGA model identifier. Rehearse the complete
upgrade and rollback with the deployment's overlays and custom agent pods.
If `global.whitelist` or `users.txt` restricts access, configure equivalent
Platform access rules or exceptions, preview them and enable filtering before
removing the file whitelist. Preserve a verified administrator recovery path.

### Configuration

Remove `global.whitelist` from Fred chart values and any separate `users.txt`
mount. No other setting must change for an ordinary upgrade. The production
reference is the Fred chart values; `configuration_prod.yaml` is for local
Docker Compose only. Custom agent pods need the SDK and runtime of this release.
If `fred-agent-evaluator` is deployed, use a version that forwards the selected
chat model as described in the model-picker section before relying on overrides.

### Upgrade

#### Required coordinated rollout

1. Quiesce affected writers, take the verified database backup and preserve the
   previous deployment inputs. Keep the equivalent Platform access policy on
   throughout rollout where it replaces a file whitelist.
2. Run the control-plane Alembic chain once, before updated control-plane or
   Knowledge Flow readers start. From the v3.4.0 head `93427a5fe874`, the chain
   is `9f6d3c2a1b08` -> `e5ff6d80cc9f` -> `a6c1d94e27b3` -> `e9026d8e4db6`
   -> `24c2f88374fe`. Use the deployment's migration job or equivalent command;
   the chart's migration hooks are disabled by default. Run the normal runtime
   and Knowledge Flow migration checks as part of the deployment; this release
   adds no revisions in those trees.
3. Deploy the matching Fred chart and updated control plane. Confirm its
   OpenFGA model is written and selected with the marketplace permissions, and
   confirm the Platform access policy still admits the intended users.
4. Deploy updated Knowledge Flow services and all agent runtime pods, including
   third-party pods rebuilt on this release's SDK/runtime. Upgrade runtime pods
   before the frontend so messages with several prompt commands retain their
   full display after reload. Upgrade the evaluator as noted above if used.
5. Deploy the frontend and verify the control-plane, runtime and frontend
   together. Resume traffic only after the validation below passes.

#### Optional activation and user data

- Marketplace publication stays off by default. After all pods are updated,
  platform administrators may enable it for eligible teams and set quotas.
- To use GPT-6 Astra through Azure APIM, add an authorized Responses API model
  profile to the deployment model catalog and restart affected pods if needed.
- To use custom theme CSS, labels or extra selectable themes, upload the new
  theme ZIP only after the frontend is upgraded, then restart frontend pods.
- No document re-ingestion is required for the upgrade. A user may upload an
  earlier failed Windows-1252 or BOM-prefixed text file again to benefit from
  the decoding fix; existing successful documents remain unchanged.

### Validation

Confirm the control-plane head is `24c2f88374fe`, the OpenFGA model is selected,
and access restrictions remain effective. Check sign-in, team invitation join
history, chat model choice and reasoning, multiple prompt commands after reload,
the patch-note history and a basic agent-marketplace browse. If publication is
enabled, test publishing and importing an agent with configuration files.
Validate custom pods and the evaluator where deployed. Exercise any activated
Astra profile or theme ZIP separately.

### Rollback

Stop new traffic and affected workers before changing images or schemas.
Disable optional marketplace publication and Astra selection, and restore the
previous theme ZIP if used. A code-only rollback is suitable only when the old
images were rehearsed against the current schema and data. Otherwise, use a
coordinated restore from the pre-upgrade backup. Any in-place downgrade must
be reviewed across the full chain and run with the new migration image while
readers and writers remain stopped. It can discard marketplace entries,
model settings, patch-note exposure and seen history, and Free-link join history;
the old per-template model overrides and earlier dismissal choices are not
reconstructed. Restore the previous OpenFGA model and file-whitelist settings
only with old application readers, and verify access before reopening traffic.

### Limitations

The chart does not order application Deployments, so enforce the staged rollout
in the deployment procedure. The release guide does not validate private
overlays, third-party pod builds, evaluator compatibility or production APIM
permissions. Patch-note history before this upgrade lacks historical content;
previously failed text uploads are not repaired automatically.

## Keep the model's answer after a failed tool round

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/2588-keep-model-answer-after-failed-tool-round.md)

No API, event, data or configuration change: agents simply show the model's own answer instead of a generic error after a failed tool round, once the new runtime is deployed.

See the source note for applicability, validation and rollback.

## Retire the file whitelist and record Free-link joiners

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3061-platform-admission-and-link-joiners.md)

### Applicability

All Fred deployments receive the admission and Free-link changes. Deployments
that configured `global.whitelist` or mounted `users.txt` require configuration
changes before upgrading.

### Prerequisites

Back up the shared control-plane database. Review any existing file whitelist and
prepare equivalent rules or individual/team exceptions in Platform access. Check
the intended policy with the administrator preview and enable filtering before
removing the file whitelist, so admission remains restricted throughout rollout.

### Configuration

Remove `global.whitelist` from chart values; the new values schema rejects it.
Remove any separate `users.txt` mount. Platform access in the administrator UI is
the sole admission whitelist. Saved rules, exceptions and Free-link settings
remain available while its filtering switch is off.

### Upgrade

1. Apply the control-plane Alembic head before deploying the new control plane
   and readers. This contribution's revision, `9f6d3c2a1b08`, adds per-link
   join history without changing existing links or admission state. The release
   also includes later control-plane revisions; run the chain once to its head.
2. After equivalent Platform access filtering is enabled where needed, remove
   retired whitelist values and mounts. Stage the chart and services using the
   consolidated v3.5.0 sequence; the file no longer limits admission.

If a disposable preview database already applied an earlier draft of this
unmerged revision, recreate it from the current migrations before testing.
Alembic does not rerun an applied revision when its contents change. For a
preview database that must retain data, back it up and explicitly add the
snapshot and deletion columns, remove the joiner's user foreign key, and
backfill the snapshots from `users` before starting the new control plane.
Existing production databases have not applied this new revision.

The detailed admission deployment sequence remains in
[the platform-access migration note](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/2965-platform-access-planning.md).

### Validation

Confirm that disabling filtering admits an authenticated, active person and
that re-enabling it restores the saved restrictions. Confirm that a current
platform administrator stays admitted. Use a new Free link to join a team and
check that its administrator view shows the joiner's username and names.

### Rollback

Reverting to an older chart requires restoring any old whitelist values and
mount deliberately, after reviewing the resulting admission policy. Back up
the database before downgrading: dropping `9f6d3c2a1b08` removes recorded join
history. Disabling the SQL filtering switch is an explicit way to widen
admission without deleting its saved configuration.

### Limitations

Earlier link openings or joins cannot be backfilled into the new history.
Recorded joins survive team departure, account deletion and link expiry or
revocation. After account deletion, they retain the last recorded names and
username with a deleted marker. Only explicit link-history deletion removes
them. A successful OpenFGA grant
and the SQL join record are separate operations; a failed SQL commit after the
grant can require operator reconciliation.

## Add a bilingual user patch-note drafting skill

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3068-write-patch-note-skill.md)

The skill produces text for authors to copy manually; it changes no deployed behavior, stored data or client contract.

See the source note for applicability, validation and rollback.

## ButtonGroup track uses design tokens only

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3070-button-group-surface-tokens.md)

A frontend-only styling change with no API, data or configuration effect; it applies after a normal deployment.

See the source note for applicability, validation and rollback.

## Section the chat composer command menu by source and allow several prompt commands in one message

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3073-composer-command-menu-sections.md)

### Applicability

All Fred deployments using managed chat, including agent pods built outside
this repository on `fred-runtime`.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure. No data
migration: the new field is stored inside the existing
`session_history.metadata_json` column.

### Configuration

No configuration changes are required.

### Upgrade

Follow this order:

1. Upgrade the runtime pods first: `fred-agents` and every other agent pod
   built on `fred-runtime`. A pod built outside this repository has to be
   rebuilt on the `fred-sdk`, `fred-core` and `fred-runtime` of this release.
2. Then upgrade the frontend.

The other order is safe for the agents and for stored data. Its only effect is
described under Limitations, for the messages sent while a runtime pod is
still on the previous release.

### Validation

In a team conversation, type `/` in the empty composer: the menu lists the
team's commands under a heading carrying the team name, then the user's own
commands under "Personal space", then the platform skills, whatever the agent.
Pick a command with Enter: it is added to the field as a small coloured
container and nothing is sent; press Enter again to send. A skill behaves the
same way, and both keep their container in the sent message. Click the
command's container in the field: a side panel shows the prompt's text.

Then send a message holding two commands, for example `/summary then /tone`:
the message shows one container per command, and clicking one opens that
prompt's own text. Reload the page: both containers are still there. If only
the first one is, the pod that ran the turn is still on the previous release.

### Rollback

Use the normal rollback procedure; this change introduces no data migration.

### Limitations

A message holding several commands and sent through a runtime pod that is not
upgraded yet is answered normally: the agent receives the text of every
prompt. After a page reload, such a message shows its first command as a
container and the following ones as the `/name` the user typed, and the side
panel shows the whole text that was sent. Messages stored that way keep that
display after the pod is upgraded.

A message holds at most 16 prompt commands.

Users now see their personal-space commands with every agent, not only some of
them; a command typed without picking a row still runs the team's one first.
Enter on a command in the menu no longer sends the message at once: it adds
the command, and a second Enter sends.

## Reserve Jira bug resolution for confirmed production deployment

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3078-jira-bug-resolution-after-deployment.md)

Ticket workflow guidance changes no running service, stored application data or upgrade procedure.

See the source note for applicability, validation and rollback.

## Friendlier access-denied and team invitation pages

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3085-platform-access-entry-pages.md)

No API, stored data, permission or chart value changes; the new pages take effect with a normal frontend deployment.

See the source note for applicability, validation and rollback.

## Platform access whitelist lists individual exceptions and adds people through a dialog

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3086-whitelist-lists-individual-exceptions.md)

The new query parameter is optional and defaults to the previous behaviour; no schema or stored data changes, and the control-plane backend and frontend follow the coordinated release rollout.

See the source note for applicability, validation and rollback.

## Condensed Platform access administration screens

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3087-condense-platform-access-admin.md)

No API, data or permission changes; the new presentation ships with the frontend image on normal deployment.

See the source note for applicability, validation and rollback.

## Reject PowerPoint templates without fields

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3093-reject-empty-ppt-templates.md)

Normal deployment enables validation for new uploads; existing saved templates and data require no migration.

See the source note for applicability, validation and rollback.

## Reduce PowerPoint validation memory and clarify transport failures

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3094-ppt-validation-memory.md)

The validation fix and translated transport messages apply during normal deployment; stored templates, agent configuration, and permissions remain compatible.

See the source note for applicability, validation and rollback.

## Support GPT-6 Astra tools through Azure APIM Responses API

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3097-azure-apim-astra-responses.md)

### Applicability

Fred deployments using the Azure APIM chat provider. Existing model profiles keep
their Chat Completions route unless they opt into the Responses API.

### Prerequisites

For optional Astra activation, confirm that the selected APIM product allows
the full `/ai-models/openai/v1/responses` route and authorizes the Astra model
and function tools. Use credentials issued for that product.

### Configuration

No configuration changes are required for a normal upgrade. To activate Astra,
add a chat profile in the deployment model catalog with `provider: azure-apim`,
the authorized Astra deployment name, `use_responses_api: true`,
`reasoning: {effort: low}`, `temperature: null`, and
`azure_apim_resource_path: /ai-models/openai`. Set `azure_apim_base_url` and
the authentication settings for the same APIM product. The bundled
`/genai-aoai-inference/v2` example targets a different gateway route and must
not be reused for this Astra profile. Do not pass Chat Completions
`extra_body.reasoning_effort` to this profile.

### Upgrade

Deploy Fred normally. For optional activation, deploy the updated agent image
before selecting the Astra profile, apply the catalog change, and restart agent
pods if the catalog is mounted through a ConfigMap `subPath`.

### Validation

With synthetic data, run an Astra turn that calls a function tool and another
turn that consumes its result. Verify that an existing APIM profile still uses
Chat Completions.

### Rollback

Select a previously working profile and restore the prior catalog entry. Roll
back the Fred image if needed; no data migration is involved.

### Limitations

Astra is not activated by this change. APIM content guardrail rejections remain
independent of the model endpoint choice.

## Read theme CSS, branding properties and labels from the frontend ZIP

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/frontend-theme-zip-css-properties.md)

### Applicability

Frontend deployments using a theme ZIP through `FRONTEND_THEME_URL`.

### Prerequisites

The ZIP remains reachable by the frontend container. No database migration is required.

### Configuration

The existing SeaweedFS object may now include `theme-custom.css`, `theme-properties.json` and `theme-translations/en.json` or `fr.json`. Only branding labels and asset names are accepted in the properties JSON; see `apps/frontend/README.md`. No new environment variable is required.

The ZIP may also include `theme-catalog.json` to declare several additional selectable themes. Each entry has a unique `id`, display `label`, and `base` (`pebble`, `cobalt`, or `cloud`). For light and dark overrides, use `[data-ui-theme="<id>"][data-ui-base-theme="<base>"][data-theme="light"]` and its dark counterpart. The base attribute gives ZIP CSS priority over shipped CSS while letting admin previews match. An entry may also set `tabTitle`, `faviconName` and `faviconNameDark` (SVG basenames under `images/`) so the browser tab follows the active theme; omitted values keep the global branding. The new choices appear after frontend pods restart and browsers reload; existing platform defaults and hidden-theme settings can select them. Admin changes to the default or hidden themes now reach connected browsers after the save, on window focus or within a minute.

New ZIPs may keep `theme-catalog.json` at the root, place each theme's CSS and images in `themes/<id>/`, and put global properties, translations, legal Markdown and images in `shared/`. Image paths remain `/images/...` after installation, so image names must be unique across folders. Existing flat ZIPs remain supported. See the frontend README for the complete layout.

### Upgrade

Deploy the new frontend image. To activate overrides, upload a ZIP with the optional files to the object configured by `FRONTEND_THEME_URL`, then restart the frontend pods. Existing ZIPs containing only images and Markdown continue to work.

### Validation

Open the frontend in a fresh browser session and verify the browser tab name, selected image names, translated UI labels and light/dark theme CSS. Check that the theme CSS, properties and translation URLs serve the ZIP content. The frontend container logs `Theme installed from ...` when the ZIP is accepted.

Older frontends ignore `theme-catalog.json`, CSS, properties and translations, and refuse a ZIP using `themes/` or `shared/` (stock assets are served, or the pod stops when `FRONTEND_THEME_REQUIRED=true`): upgrade the frontend before uploading such a ZIP. Rolling back means reverting to a flat ZIP holding only `images/`, `contrib/` and Markdown.

### Rollback

Restore the previous ZIP and restart frontend pods, or remove the optional files from the ZIP. No data rollback is needed.

### Limitations

Replacing the SeaweedFS object does not update already running pods; they must restart. Connected browsers then reload to receive the new values.

## Fix HTML artifact PNG/PDF export in Chrome and Edge

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/html-artifact-export-chrome.md)

The fix is client-side rasterization only; existing data, APIs and artifacts are unchanged and it takes effect with normal deployment.

See the source note for applicability, validation and rollback.

## Route accepted Jira bug plans through the required CCB transition

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/jira-ccb-planning-transition.md)

The required Jira status transition does not alter Fred services, data or upgrade steps.

See the source note for applicability, validation and rollback.

## Deliver non-streamed final answers on the OpenAI-compatible endpoint

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/openai-compat-final-content.md)

The endpoint keeps its request and chunk shapes; clients now also receive answer text that was previously dropped, with normal deployment.

See the source note for applicability, validation and rollback.

## Decode Windows-1252 and BOM-prefixed plain-text and Markdown inputs

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/plain-text-encoding-fallback.md)

New ingestions and attachments are decoded correctly with normal deployment; previously failed uploads can simply be uploaded again, nothing has to be reprocessed for the upgrade.

See the source note for applicability, validation and rollback.

## Publish generic agent-pod and knowledge-base Helm charts

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/publish-pod-helm-charts.md)

The new charts are additive: nothing deployed uses them until an operator installs a pod from them, so existing releases upgrade normally.

See the source note for applicability, validation and rollback.

## Keep Resources folder listings stable during ingestion

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/resources-ingestion-list-stability.md)

Normal deployment supplies the updated frontend; no data, API, or configuration changes are required.

See the source note for applicability, validation and rollback.

## Serialize missing CSV and Excel result cells as JSON null

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/tabular-null-result-serialization.md)

Existing CSV and Excel artifacts remain usable. Missing cells are normalized when results are returned, without re-ingestion, data migration or client updates.

See the source note for applicability, validation and rollback.

## Announce patch notes as a package and show the history by exposure

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3080-browse-patch-note-history.md)

### Applicability

All Fred deployments upgrading the control-plane backend and frontend.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

Treat the control-plane backend and frontend as one coordinated rollout: run
the release's control-plane migration chain before starting the updated backend,
then update the frontend. These two revisions require no separate backfill or
manual step.

`e5ff6d80cc9f` (parent `9f6d3c2a1b08`):

- drops the index that allowed a single enabled patch note;
- adds `platform_announcement.position` and numbers the existing patch notes,
  most recently created first;
- drops `platform_announcement_dismissal` and creates
  `platform_announcement_seen` (one row per user).

`a6c1d94e27b3` (parent `e5ff6d80cc9f`):

- creates `platform_announcement_exposure` and converts the activation
  history into it, one line per exposure: each banner activation is paired
  with the deactivation that followed it;
- turns the patch note that was enabled into the first announced package;
- drops `platform_announcement_activation_event`.

What administrators and users see afterwards:

- users keep reading the patch note that was enabled, from **What's new**; no
  patch-note dialog opens for anyone until an administrator uses **Announce
  the update**;
- the Patch notes tab is a working area: its checkboxes choose what the next
  announcement includes, and nothing done there reaches users before that;
- earlier "Don't show again" choices are discarded: that option no longer
  exists;
- in the history, patch-note lines from before the upgrade show their dates
  but cannot be opened: their content of the time was not kept.

### Validation

As a platform admin, open **Administration → Announcements → Patch notes**,
turn on two patch notes and reload as another user: no dialog opens, and
**What's new** still shows the earlier patch note. Use **Announce the update**
and reload as that user: the dialog opens once, on the first of the two. Edit
one of them: users still read the announced text. In the history, the
announcement is one line that opens the package as users saw it.

### Rollback

Use the normal rollback procedure. Downgrading `a6c1d94e27b3` rebuilds the
activation events from the history lines and loses the announced packages and
who ended an exposure. Downgrading `e5ff6d80cc9f` keeps the topmost enabled
patch note enabled and disables the others, and drops what users have seen;
the earlier "Don't show again" choices are not restored.

### Limitations

An announced package cannot be edited: correcting a typo means editing the
patch note and announcing again, which shows the dialog to every user once
more. An announcement holds at most 10 patch notes. **Withdraw the current
announcement** leaves **What's new** empty until the next announcement.

## Members pick the chat model per conversation; teams curate their models and reasoning defaults

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/chat-model-and-reasoning-picker.md)

### Applicability

All Fred deployments upgrading the control-plane backend, the agent pods
(`fred-agents` and any custom pod built on `fred-runtime` / `fred-sdk`) and the
frontend. Also deployments running `fred-agent-evaluator`.

### Prerequisites

- Back up the control-plane database: the upgrade migrates data out of a
  column it then drops.
- Custom agent pods: `AgentDefinition.reasoning_enabled` and
  `reasoning_default_on` are now deprecated no-ops. A definition that sets them
  still loads, logs one deprecation warning per definition class, and its
  value has no effect: reasoning follows the model. Remove them before a later
  SDK minor drops them. `AgentTuning` no longer has them.
- `fred-agent-evaluator`: deploy a version that forwards
  `ExecutionPreparation.chat_profile_id` as `runtime_context.chat_profile_id`.
  An older evaluator still reads the removed `agent_profile_overrides` and
  silently loses its per-run model override. Tracked in #3032.

### Configuration

No configuration changes are required.

### Upgrade

1. Treat the control plane, agent pods and frontend as one coordinated rollout.
   Run the normal control-plane `alembic upgrade head` before starting updated
   services. Revision `e9026d8e4db6` (after `a6c1d94e27b3`):
   - adds `disabled_model_ids_json` and `reasoning_default_off_model_ids_json`
     to `team_routing_policy`, both empty;
   - copies each team's per-template model override into
     `recommended_chat_profile_id` of that team's agents created from that
     template, where none is set;
   - drops `agent_profile_overrides_json`.
   The migration logs how many agents it updated. Former per-agent reasoning
   keys in stored agent settings are ignored and dropped on the next save.
   Start the updated control plane, then updated agent pods and frontend in the
   coordinated release sequence.
2. Review reasoning, since the composer's reasoning row is now driven by the
   model, not the agent:
   - platform admins: check which models have reasoning enabled
     (admin **Features** page, **Models** filter). It is now offered with
     every agent, and a newly allowed model arrives with reasoning **on** by
     default for teams;
   - team admins: in team settings → **Models**, switch "Reasoning on by
     default" off for models where it should start off.
3. Tell team editors that only team admins (and a personal space's owner) can
   now change the team's models (default, enabled models, reasoning
   defaults). Editors keep a read-only view and set each agent's
   **Recommended model** in the agent form.

When the platform revokes a model that a team had set as its default, the
team's default is cleared and the pod default takes over, so conversations keep
working. The team admin can pick a new default in team settings → **Models**.

### Validation

- `alembic_version_control_plane` holds `e9026d8e4db6` (or a later head).
- An agent whose template had a team override shows that model as its
  **Recommended model** in the agent form.
- While one of the team's agent pods is unreachable, disabling a model in
  team settings → **Models** is refused (503) and can be retried once the pod
  is back.
- In a chat, the model button lists the team's enabled models; picking one
  answers with it (pod log `[V2][MODEL_ROUTING] … source=user_choice`), and a
  new conversation starts again on the recommended model.
- A team editor who is not team admin gets a read-only Models section; the
  `PATCH /teams/{team_id}/routing-policy` call returns 403 for them.

### Rollback

Downgrading `e9026d8e4db6` re-adds `agent_profile_overrides_json` **empty**
and drops the two new columns. It is lossy: per-template overrides are not
restored (re-enter them in the previous release's routing settings, or restore
the backup), and team-disabled models and reasoning defaults are lost. The
copied recommendations stay in `tuning_json` and the previous release ignores
them. Restore the previous `fred-agent-evaluator` with the previous release.

### Limitations

- The model choice lasts for one conversation in one browser tab; it is never
  stored server-side.
- After a team disables a model or the platform revokes it, members on it move
  to the agent's recommended model on their next page refresh; until then the pod
  ignores the stale choice and answers with the next model in line.
- The choice applies to the agent the user talks to; agents it calls through
  the agent registry keep their own model.
- Old export bundles carrying per-template overrides are mapped onto the
  imported agents the same way; the import report counts them.

## Agents marketplace: publication settings, browsing, likes and imports

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.5.0/docs/swift/ops/migrations/3044-agent-marketplace.md)

### Applicability

Existing Fred deployments upgrading to this release, including third-party agent
pods built on fred-runtime. Publication is off by default, with a quota of five
agents per team. A platform administrator may enable it after deployment.

### Prerequisites

Back up the shared PostgreSQL database. The OpenFGA store must accept the new
model written by the control plane at startup.

### Configuration

No configuration changes are required. The publication default and per-team
overrides are stored in the database.

### Upgrade

1. Apply the control-plane Alembic head before starting the new Knowledge Flow
   pods. Revision `24c2f88374fe` (after `e9026d8e4db6`) adds the publication
   settings table, two nullable `teammetadata` columns and the four marketplace
   entry, file, like and import tables. Knowledge Flow reads `teammetadata`
   through the shared model and requires the new columns.
2. Deploy the control plane. At startup it writes the OpenFGA model with
   `can_publish_marketplace_agents` for team editors and
   `can_unpublish_marketplace_agents` for team editors and team admins. Existing
   tuples are unchanged.
3. Deploy the frontend and agent pods. Pods gain
   `POST /agents/capabilities/{id}/export-config`, and `copy-config` accepts
   `asset_files`. Upgrade the pods before enabling publication: an older pod
   cannot publish an agent with capabilities and may omit files on import.

Optional activation: in **Administration > Marketplaces**, enable publication
by default or for selected public teams and set their quotas. Editors of those
teams can then publish agents.

### Validation

- `alembic heads` shows `24c2f88374fe` as the single control-plane head.
- The admin Marketplaces page shows every team following Default (off, quota 5).
  A team admin cannot change these settings.
- With publication enabled, an editor can publish an agent. Another user can
  browse, like and import it into an eligible team, including its configuration
  files. Disabling publication removes the team's entries from the listing.
- A conflicting "Copy to..." name uses `<name> (copy 1)` or
  `<name> (copie 1)` according to the interface language. Platform imports
  keep `<name> (2)`.
- A disabled document's Delete menu item explains its state in a tooltip; the
  team members table uses small role chips.

### Rollback

For a full release rollback, use the consolidated v3.5.0 rollback plan. If a
schema downgrade is required, stop affected readers and writers and use the
new migration image before starting old services. Downgrading to
`e9026d8e4db6` drops marketplace settings, entries, likes and import history;
all marketplace data and overrides are lost.

### Limitations

Deleting a team now deletes its agents. Platform exports do not carry
marketplace settings or published agents. An agent whose type later disappears
from its pod stays listed until it is suspended; imports then fail.
