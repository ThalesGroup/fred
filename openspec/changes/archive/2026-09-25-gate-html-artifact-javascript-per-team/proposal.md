## Why

The `html_artifact` capability now lets an agent ship JavaScript in the page it
renders, contained by browser-enforced mechanisms (a sandboxed frame without
`allow-same-origin`, a CSP refusing every subresource fetch, and a `frame-src
blob:` shell that stops the artifact navigating itself). That containment is
sound, but it is unconditional: every team that can generate an HTML page can
also make it execute script. Executing model-authored code is a posture
decision an operator must be able to take team by team, not one the product
takes for the whole platform.

## What Changes

- `html_artifact` declares its first per-team setting, `allow_javascript`
  (boolean, default `false`), through the existing `team_settings_fields` /
  `TeamSettingsModel` mechanism. Every team keeps HTML/CSS generation; only
  teams an admin has explicitly opted in may run script.
- **BREAKING (behavioral, unreleased)**: JavaScript stops being available by
  default. A team that has not been granted `allow_javascript` gets the
  restricted mode described below. This only breaks behavior introduced on the
  current unreleased branch; no shipped behavior regresses.
- The restricted mode is **not** a return to the retired DOMPurify
  sanitization. The artifact loads with an empty sandbox (no `allow-scripts`),
  so no script executes at all — inline `<script>`, inline event handlers and
  `javascript:` URLs are inert by browser guarantee rather than by content
  filtering. The shell + `blob:` + `frame-src` machinery is unnecessary in this
  mode, because navigating a frame from inside requires script.
- The CSP (`default-src 'none'`, `webrtc 'block'`) stays active in **both**
  modes: markup alone (for example `<img src="https://host/?d=…">`) is still an
  egress channel, and the restricted mode must not be weaker than the
  permissive one on that axis.
- The model is told which mode it is in, so it does not author interactive
  pages that silently do nothing.
- `render_html_artifact` rejects a page containing script when the team is not
  allowed, returning an error result so the model re-renders without it. Script
  the team may not run is never persisted.
- The viewer resolves the team's **current** right at display time. Revoking
  `allow_javascript` immediately renders previously generated interactive
  artifacts inert, including those already in conversation history.
- Control-plane exposes a team's effective capability settings for reading.
  Today `team_capability_settings` descends only to the runtime pod, never to
  the browser, and no endpoint reads the store back.
- The admin can edit a team's settings after enabling the capability, not only
  at the moment of enabling.

## Capabilities

### New Capabilities
- `html-artifact-javascript-policy`: who may run model-authored JavaScript in a
  rendered artifact, how the restricted and permissive modes differ, how the
  decision reaches the model and the viewer, and when a revocation takes
  effect.

### Modified Capabilities
<!-- None: no existing spec under openspec/specs/ covers capability team
     settings or the html_artifact capability. -->

## Impact

- `libs/capabilities/fred-capability-html-artifact` — manifest gains
  `team_settings_fields` and a typed `TeamSettingsModel`; the middleware reads
  `ctx.team_settings` to select the prompt fragment; the render tool gains the
  write-time rejection. Manifest `version` bumps (it is the stored-config
  schema version).
- `apps/control-plane-backend` — a read path for a team's stored capability
  settings, and the session-time signal the browser needs. `team_capability_settings`
  already exists on `ExecutionPreparation` (`product/schemas.py`) and the store
  already has `get`/`list` (`capabilities/settings_store.py`); neither is
  exposed to the frontend.
- `apps/frontend` — the artifact viewer branches its loading path and sandbox
  tokens on the team's current right; the Features admin drawer
  (`CapabilityTeamMatrixDrawer`) renders the new switch and gains an edit
  affordance for an already-enabled team. The generated control-plane client is
  regenerated if any control-plane route or model changes.
- No database migration: `team_capability_settings` already exists.
- First consumer of `team_settings_fields`. The mechanism is wired end to end
  (manifest → catalog → admin form → store → `ExecutionPreparation` →
  `CapabilityContext.team_settings`) but no capability has used it, so the path
  is unproven in production.

### Deferred (explicitly out of scope)
- A per-agent `allow_javascript` option in the agent-creation advanced view.
- Team-aware filtering of `config_fields` in the aggregated capability catalog,
  which that per-agent option would require.

### Tracking
GitHub issue: ThalesGroup/fred#2798 (milestone `swift ga`).
