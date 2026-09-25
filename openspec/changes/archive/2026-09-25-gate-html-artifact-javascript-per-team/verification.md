# Verification

GitHub issue: ThalesGroup/fred#2798 (milestone `swift ga`).

## Commands run

Both from the monorepo root, after the review fixes below:

- `make code-quality` — every module, 0 errors.
- `make test` — 0 failures:

| Suite | Result |
| --- | --- |
| fred-pod / fred-core / fred-sdk / fred-runtime | 52, 706, 470, 1191 passed |
| capabilities (writable-document, ppt-filler, platform-ops, html-artifact, team-wiki, documents, document-access) | 50, 150, 18, **71**, 53, 67, 39 passed |
| apps/fred-agents | 77 passed |
| apps/control-plane-backend | **1287** passed |
| apps/knowledge-flow-backend | 1352 passed |
| apps/frontend | **2864** passed, 9 skipped (248 files) |

## What is proven

- The setting reaches the capability typed, through the real assembly hop, and an
  absent row denies rather than defaults open.
- The tool refuses every execution vector for a restricted team (script element in
  three spellings, two inline-handler forms, `javascript:` URL quoted/unquoted/
  spaced, embedded frame, `javascript:` in CSS) and stores nothing; a retry
  without script succeeds; an opted-in team's script is stored verbatim.
- Prose that merely mentions JavaScript is NOT refused (regression from review
  finding 5), while `javascript:` in a value position still is.
- The prompt fragment and the tool schema both change with the posture, and the
  halves that must not drift are asserted identical in both variants.
- The inner artifact frame carries `allow-scripts` for an opted-in team and no
  token at all otherwise; the CSP holds in both modes.
- The viewer says so when it suppresses script, and stays silent for a static page
  and for an opted-in team.
- The read path returns declared defaults for a team with no row, the stored value
  otherwise, drops keys the manifest no longer declares, and does not mistake a
  stored `false` for absent. The member route is gated on team-agent access and a
  non-member never reaches the store; the admin route is gated on capability
  management.

## What is NOT proven here

- **No live end-to-end run.** Every check above is offline. The posture has not
  been exercised against a running stack with a real team and a real model.
- The two new routes are `pending_review` in `docs/swift/platform/authz-endpoint-matrix.yaml`
  — the repository's process expects a human to review their gate.
- Browser behaviour is asserted through the composed document and the rendered
  attributes, not by observing a real browser refuse to execute. The underlying
  mechanism (`sandbox` without `allow-scripts`) is a browser guarantee, but this
  change adds no measurement of its own the way the JavaScript commit did.

## Divergence from the plan

- **Task 3.1 was implemented more narrowly than written.** "Effective capability
  settings" returned wholesale would be readable by any team member; the route
  returns only keys the manifest declares, and the contract states that a
  capability must not declare a secret-bearing team setting.
- **Design decision D2 was corrected during implementation** — see the amendment
  in `design.md`. Restricted mode keeps the trusted shell rather than dropping it:
  a downloaded file opened from disk has nothing else to deny script.
- **Task 5.3 is covered by existing tests** (`test_capability_enablement_1980`
  already asserts the settings row survives a disable), so the new suite asserts
  the READ path instead of duplicating that.
- **A bug the spec caught:** the enable form seeded from declared defaults, so
  re-enabling a capability would have overwritten the settings the database keeps
  precisely so a re-enable can restore them. Both entry points now seed from the
  stored values.

## Independent review (`/code-review high`)

Six findings; three were mine and are fixed, one was adjacent and is fixed, two
are out of scope and left open:

| # | Finding | Outcome |
| --- | --- | --- |
| 1 | The chat card's download button never received the posture, and the prop defaulted to permissive — a restricted team could download a runnable file | **Fixed.** The card resolves the posture, and every default in this area now fails closed |
| 2 | The member route discarded the canonical `TeamId` from `require_team_access`, so the `personal` alias read the wrong key | **Fixed** |
| 5 | The `javascript:` marker matched the bare word in prose, refusing a legitimate static page about JavaScript and looping the model | **Fixed**, anchored to a value position, with regressions both ways |
| 3 | `<meta http-equiv="refresh">` navigates the export/fit-width measuring frames, which have no enclosing `frame-src`; opened when DOMPurify was retired on this branch | **Fixed** (author `<meta>` defused like `<link>`). Not caused by this change — worth its own commit if the branch is split |
| 4 | Personal spaces can never be granted `allow_javascript`: the personal-scope row has no settings form | **Open** — a product decision, not a defect. Personal spaces stay restricted |
| 6 | `_open_artifact_id` is re-derived from the transcript, so a history trim makes "revise" mint a second artifact | **Open** — pre-existing, unrelated to this change |
