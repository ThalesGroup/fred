## 1. Tracking

- [x] 1.1 Create the GitHub issue for this change on an active milestone
  (`swift ga` or `CVSSI remediation`), link it in `proposal.md` under Tracking,
  and verify `gh issue view <n>` shows the link back to this change

## 2. Capability: declare and honour the team setting

- [x] 2.1 Add a typed `TeamSettingsModel` with `allow_javascript: bool = False`
  and the matching `team_settings_fields` entry to the `html_artifact`
  manifest, bump `CapabilityManifest.version` (D7), and verify the capability's
  registry test still passes and the catalog entry advertises the new field
- [x] 2.2 Split the prompt fragment into a permissive and a restricted variant
  selected from `ctx.team_settings` (D5), and verify a unit test asserts the
  restricted variant never offers JavaScript and the permissive one keeps the
  existing constraints
- [x] 2.3 Make `render_html_artifact` refuse a page containing script when the
  team is not opted in, returning a recoverable error result (D3), and verify
  a tool test covers script element, inline event handler and `javascript:`
  URL, plus a clean page passing through unchanged
- [x] 2.4 Verify the setting actually arrives as `ctx.team_settings` by testing
  the assembly hop with a populated `team_capability_settings` mapping — this
  is the first capability to use the path and it has never run

## 3. Control-plane: expose the team's own setting

- [x] 3.1 Add a read path returning the effective capability settings for a
  team the caller belongs to (D4), scoped to the caller's membership and not
  requiring an administrative role, and verify an API test covers a member, a
  non-member (denied) and a team with no stored row (defaults)
- [x] 3.2 Add a read path the admin surface can use to load a team's stored
  settings for an already-enabled capability, and verify an API test covers a
  stored row and an absent one
- [x] 3.3 Regenerate the frontend control-plane client
  (`cd apps/frontend && make update-control-plane-api`) and verify the
  regenerated `controlPlaneOpenApi.ts` is committed alongside the backend
  change with no hand edits

## 4. Viewer: branch the loading path on the current right

- [x] 4.1 Split the sandbox token constant into the shell token and the
  artifact token so the artifact frame can carry none while the shell keeps
  `allow-scripts`, and verify the existing sandbox test still forbids
  `allow-same-origin` on every path
- [x] 4.2 Add the restricted loading path — the composed document loaded
  directly with an empty sandbox, no shell and no `blob:` URL (D2) — and verify
  a test asserts the document still carries its CSP meta and its defused link
  elements
- [x] 4.3 Resolve the session team's current right when the artifact pane
  mounts and select the loading path from it (D4), and verify a test covers
  both modes plus the refetch-on-mount behaviour
- [x] 4.4 Show the notice when an artifact carries script the current right
  does not allow to run (D6), with translations in `en` and `fr`, and verify a
  test asserts the notice appears only in that case
- [x] 4.5 Verify the download and new-tab paths follow the same branch as the
  preview, so a restricted artifact cannot be opened outside the viewer with
  script enabled

## 5. Admin: set and change the option

- [x] 5.1 Verify the enable-with-settings form now appears for this capability
  in the Features drawer and writes `allow_javascript`, with help text saying
  that turning it off also stops earlier artifacts from running (D6 risk)
- [x] 5.2 Add the affordance to edit an already-enabled team's settings,
  seeding the form from the stored values through the existing `existing`
  argument, and verify a test covers opening, changing and saving without
  disabling the capability first
- [x] 5.3 Verify a disable followed by a re-enable restores the prior value,
  since the store keeps the row on disable

## 6. Documentation and close-out

- [x] 6.1 Update the capability's README and the Help Center capability pages
  (`en` and `fr`) to state that JavaScript is granted per team, and verify no
  page still describes it as always available
- [x] 6.2 Trim `HTML-ARTIFACT-CAPABILITY-RFC.md` to what is still an open
  question, folding the settled policy into the capability spec, and verify the
  RFC no longer presents unconditional JavaScript as current
- [x] 6.3 Run `make code-quality` and `make test` from the monorepo root and
  verify both pass
- [x] 6.4 Run `/code-review` on the diff and resolve findings before reporting
  done, then record the verification evidence on the change and archive it
