## Context

See `proposal.md` — Why. Design-relevant current state only:

- Containment today is entirely browser-enforced and unconditional. The viewer
  loads a shell document (`sandbox="allow-scripts"`) whose own bootstrap script
  creates a `blob:` URL for the artifact and loads it into an inner frame that
  carries the same token. The shell's CSP adds `frame-src blob:`, which is what
  stops a script navigating its own frame to an external host.
- The composed artifact document already carries its own CSP meta
  (`default-src 'none'; … webrtc 'block'`) — it does not depend on the shell
  for it.
- `team_settings_fields` / `TeamSettingsModel` is wired end to end but has no
  consumer: manifest → catalog → the admin enable-with-settings form → the
  `team_capability_settings` table → `ExecutionPreparation` →
  `CapabilityContext.team_settings`. No database work is needed.
- Nothing carries a team's capability settings to the browser, and no endpoint
  reads the store back; the store itself already has `get` and `list`.
- The admin form opens only on the disabled → enabled transition. Its seeding
  helper already accepts an existing-values argument that no caller passes.

## Goals / Non-Goals

**Goals:**

- One capability, one chat-part kind, one viewer, one conversation history.
- The restricted mode is no weaker than the pre-JavaScript behavior on any
  axis, including network egress.
- The decision is enforced where it cannot be argued with, not merely where it
  is displayed.

**Non-Goals:**

- Real-time propagation of a revocation to an artifact already on screen.
  "Immediately" means at the next display of the artifact, not a push to an
  open pane.
- Defending against a user who tampers with their own browser (see Risks).
- Any per-agent granularity; see the proposal's deferred section.

## Decisions

### D1 — A per-team setting on the existing capability, not a second capability

A separate "HTML/CSS/JS" capability would make the per-team gating free, since
capabilities are already granted team by team through a built admin surface.
It was rejected: the registry refuses to boot a pod where two capabilities
declare the same chat-part kind, so the second capability would have to fork
the artifact's chat-part kind. That cascades into a second side panel, a second
frontend registration, two viewers to maintain, and a conversation history
permanently split across two part types. The difference between the two modes
is a few lines in the capability package and a branch in the viewer — the split
would sit an entire layer above where the difference actually is.

Also rejected: a platform-wide store (no per-team granularity, and it would be
a third configuration layer with one consumer) and a deployment feature flag
(not editable by an administrator at runtime).

### D2 — Restricted mode is an empty sandbox, not a content filter, and not the shell

Restricted mode loads the composed artifact document directly with a sandbox
carrying no tokens. Three consequences, all in the same direction:

- No script of any kind executes — element, inline handler, or `javascript:`
  URL. This is a browser guarantee rather than a filter that has to recognize
  what it removes, which is why DOMPurify is not reinstated.
- The shell, the `blob:` URL and `frame-src blob:` stop being *load-bearing*:
  they exist to stop a *script* navigating its own frame, and there is no
  script to do it.

  **Revised during implementation (2026-09-24).** This first read as "drop the
  shell in restricted mode". Reading `downloadHtmlArtifact` showed why that is
  wrong: a saved file opened by double-click is the top document on `file://`
  with no frame around it and nothing to deny script, so the shell is what
  carries the isolation on that path — and an artifact produced while the team
  *was* opted in still contains script after a revocation. The shell therefore
  stays on every path, in both modes, and the posture moves one level down: the
  shell's own frame keeps `allow-scripts` because its bootstrap is ours and must
  run, while the INNER frame holding the artifact carries `allow-scripts` or no
  token at all. One document shape, one parameter, and the download path keeps
  the protection it already had.
- The one residual the capability's RFC documents for link-element defusing —
  "author script can append a live one at runtime" — cannot occur in this mode.

The CSP travels inside the composed document itself, so dropping the shell does
not drop it. Keeping it matters: markup alone (`<img src="https://host/?d=…">`)
still reaches the network, and a model steered by injected content could encode
team data into such a URL. The empty sandbox also blocks form submission and
popups, which is intended.

### D3 — Two enforcement points, and only one of them is critical

- **Write time (server).** When the team is not opted in, the render tool
  refuses a page containing script and returns a recoverable error so the model
  re-renders without it. Nothing the team may not run is ever stored.
- **Display time (client).** The viewer selects the loading path and sandbox
  tokens from the team's current right.

The write-time check is what makes the client-side control non-critical: for a
team that was never opted in, the stored artifact contains no script for a
tampered client to run. The display-time control exists for the one case the
write-time check cannot cover — artifacts created while the team *was* opted
in, and then revoked.

### D4 — Resolve at display time through a caller-scoped read, not a stored flag

Recording the right on the artifact part at creation would need nothing new,
but it freezes the decision: revoking the option would leave every earlier
interactive artifact running. A security switch that does not apply to what it
has already permitted gives a false sense of control.

The viewer therefore reads the current right for the session's team. This needs
a read path scoped to the caller's own team — not the admin surface, which
answers a different question and requires an administrative role the ordinary
user does not hold.

Rejected: extending the frontend bootstrap payload. It is user-wide rather than
team-scoped, would have to carry every team the user belongs to, and is fetched
once per load — which is exactly the staleness the decision is meant to avoid.

### D5 — The model is told which mode applies

The prompt fragment is selected from the same team setting. Without this, a
restricted team receives pages whose tabs, accordions and canvases silently do
nothing, and the failure looks like a product bug rather than a policy.

### D6 — The viewer states when script was suppressed

When an artifact carries script that the current right does not allow to run,
the viewer shows a discreet notice. Silent inertness is the failure mode this
change is supposed to avoid, and it is the visible half of D5 for an artifact
produced before a revocation.

### D7 — Manifest version bump

`CapabilityManifest.version` is the stored-config schema version and half the
cache key for computed surfaces. Declaring the first team setting changes that
schema, so the version bumps.

## Risks / Trade-offs

- **A user can tamper with their own browser and restore script execution.** →
  The write-time check means a never-opted-in team's artifacts contain no
  script to restore. The residual case is a user re-enabling script in their
  own session on their own team's earlier content, which exposes only that
  user's session; the app origin stays protected by the sandbox's absent
  `allow-same-origin`, which the page itself cannot grant.
- **First consumer of `team_settings_fields`; the path has never run in
  production.** → Cover each hop with a test rather than only the ends: the
  manifest declaration, the admin form, the store round-trip, the value
  arriving as `ctx.team_settings`, and the viewer's branch.
- **Revocation breaks pages that used to work.** → Intended, and the reason for
  D6. Worth saying plainly in the admin form's help text so the administrator
  knows what turning the switch off does.
- **A cached read makes "current" approximate.** → Bound the cache lifetime and
  refetch on viewer mount. The specs are written as "reopens the artifact", not
  "while the artifact is open", so this stays within the contract.
- **The empty sandbox also disables forms and popups.** → Acceptable: a
  self-contained artifact has nowhere to submit a form, and the CSP already
  sets `form-action 'none'` in both modes.
- **Default `false` changes behavior on the current branch.** → Unreleased, so
  no deployed behavior regresses; the admin grants the option where it is
  wanted.

## Migration Plan

No database migration: `team_capability_settings` already exists, and an absent
row means the option is off, which is the intended default.

Rollout: the capability keeps its admin-gated scope. On deploy, every team that
already has the capability keeps HTML/CSS generation and loses JavaScript until
an administrator opts it in. Rollback is the change itself — there is no
persisted state whose shape changes, so reverting the code restores the prior
behavior without a data step.

## Open Questions

None that can be deferred without changing the specs or the task breakdown.
