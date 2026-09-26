# PR migration notes and release guides

## For every PR: a two-minute check

Ask yourself: **can an existing deployment upgrade normally, without anyone
having to do anything extra?** Check these three points:

- Configuration, permissions or secrets to change?
- Existing data to migrate, re-ingest or rebuild, even just to enable the improvement?
- Clients to adapt, or a special deployment/restart order to follow?

**All no? Use `impact: none`.** A UI improvement, bug fix or documentation change
can have no migration impact. You do not need to invent a migration procedure.
The note records: "I checked, and normal deployment is enough", with a short
reason specific to your change.

1. Copy [the template](MIGRATION-NOTE-TEMPLATE.md) to
   `docs/swift/ops/migrations/<unique-slug>.md` (one English note per PR).
2. Replace its four `TODO` lines. Keep the short default sections if they are true
   for your change; otherwise adapt them. For example:

   ```yaml
   title: "Fix truncated document titles in the UI"
   configuration_reason: "Only UI rendering changes; no configuration keys or defaults change."
   no_action_reason: "Existing data and APIs are unchanged; the UI fix takes effect with normal deployment."
   ```

   For Validation: "Open a document with a long title and check that it is readable."
3. Link the note and declare its impact in section 8 of the PR description.
4. Run the check from the repository root:

   ```bash
   make migration-check
   ```

**One yes?** Use the classification below and replace the relevant template
sections with the actual actions, validation and rollback. For example,
re-ingesting existing Excel/CSV files to gain new metadata is `minor`, even if
users can continue using the old files without it. Keep optional actions clearly
separate from required upgrade steps. Remove `no_action_reason` when impact is
`minor` or `major`.

For an ordinary PR, you are done here. Release preparation is covered later in
this guide; you do not need to generate a release guide or bump versions yourself.

The `Migration notes` check validates structure and known risk signals. The author
and reviewer check whether the declaration is true. Even docs-only PRs need a note.

## Classification

| Impact | Minimum release increment | Meaning |
| --- | --- | --- |
| `none` | patch | Normal deployment suffices; explain why in `no_action_reason` |
| `minor` | minor | Operators need configuration, IAM, migration, restart ordering or other extra operations, including conditional feature activation |
| `major` | major | Substantial incompatible change, such as replacing a storage technology |

The maximum impact in the release wins. A feature behind a default-off switch is
still minor if enabling it requires operator actions. The guide must distinguish
ordinary upgrade from optional activation. A larger increment can be explicitly
approved; a smaller one fails publication validation. This operational version
policy applies to the paired Fred code/chart release, not independent npm packages.

Every note has `schema: 1`, a single-line title, impact, `configuration` and
`configuration_reason`. Configuration is `production`, `local` or `none`. Explain
the actual change; a generic claim does not replace review. Production changes
require a substantive chart values update. Existing schema CI checks regenerated
backend/chart schemas. Local-only changes need an explicit reason why production
values are unaffected. If the check flags a file under `config/` whose edits only
change bundled tool instructions, use `local` and name the file and why production
values are unaffected. This does not itself imply an operational `minor` impact.
Source-path heuristics catch common cases but cannot infer
all configuration changes: the developer and reviewer remain responsible.

Required body sections are Applicability, Prerequisites, Configuration, Upgrade,
Validation, Rollback and Limitations. Write specific steps or a reason the section
does not apply. For example, state default values, behavior when omitted, affected
pods, drain/restart order, observable success criteria and rollback security/data
limits. Do not commit customer secrets or private deployment values.

Optional `after: [other-note-slug]` orders dependent procedures. Cycles or unknown
identities fail. Optional `covers: [full-commit-SHA]` explicitly acknowledges a
previous uncovered contribution already on the release branch after reviewing its
actual impact; it is not a blanket exemption. Do not reference internal PR commit
SHAs: squash and rebase can remove them from the release ancestry. Merge and squash
contributions need one note for the aggregate PR, not one per internal commit. Rebase/direct sequences
without per-contribution notes need explicit coverage in a subsequent note.

Published notes are immutable. Add a correction note; never delete or rename
existing fragments, including unreleased notes. An unreleased note can be corrected, but that does not replace the new
PR's own declaration. Keep related procedures ordered and avoid contradictory
instructions. CI checks structure and known risk signals, not operational truth.

## Preparing a release: use the guided skill

In Codex, ask:

> Use $push-release to prepare the next Fred release. Propose the version and
> consolidated DevOps guide, and wait for my approval before creating tags.

The repository's [push-release skill](../../../.agents/skills/push-release/SKILL.md)
is shared with Claude Code. It runs the tooling for you and asks only for missing
release choices or operational details that cannot be established from the notes.

1. **Collect:** inspect every change since the previous stable release on this
   branch, including changes omitted from user-facing release notes. Identify
   missing declarations and propose the minimum version from the maximum impact.
2. **Consolidate:** generate one guide from all PR notes. Review dependencies,
   duplicate actions and contradictions; fix source notes and regenerate. Separate
   required upgrade actions from optional activation. Group no-action notes compactly.
3. **Present:** show the proposed version, user-facing notes and the complete
   DevOps guide, including validation, rollback and remaining limitations.
4. **Approve, then publish:** after your explicit approval, commit the documents,
   verify the committed guide, create the paired code/chart tags and push. Confirm
   both publication workflows succeed and attach the same guide.

**Developer: one short note per PR. Integrator: one reviewed guide before tagging.
DevOps: one document to follow.** The common note format makes collection automatic;
resolving how the procedures interact remains part of the integrator's review,
assisted by the skill. An all-`none` release should clearly say that normal
deployment suffices, with no additional action.

The delivered file is `docs/swift/ops/releases/vX.Y.Z/migration.md`, also attached
to each GitHub release. Fix the source notes and regenerate; do not hand-edit the
generated guide. Keep operator procedures out of `apps/frontend/public/release.md`.

### Without an assistant

From the repository root:

| Command | Result |
| --- | --- |
| `make migration-check` | Validate the PR note, including uncommitted edits. |
| `make release-plan` | Report the baseline, migration impact, minimum version and coverage blockers. |
| `make release-guide RELEASE_VERSION=X.Y.Z` | Generate and validate the consolidated guide for your chosen version. |

These commands neither create tags nor publish a release. Review the guide and
follow the [release strategy](../RELEASE-STRATEGY.md) before tagging. Release
preparation itself also needs a note (normally `none`).

Use a full checkout with tags. The baseline is a stable code tag on this branch's
first-parent ancestry, not the largest repository-wide tag. Candidates compare
against the preceding stable release; promotion keeps the eligible core version.
The selected baseline is recorded in the guide and reused during verification.
Both annotated tags must point to the commit containing the final documents.
Publication checks enforce the guide, version and matching tag pair. Do not bump
Chart.yaml's placeholder version; it is injected at build time.

For a different PR base, use `make migration-check MIGRATION_BASE=origin/<branch>`.
Run `make migration-tests` only when changing policy tooling, not for each note.

## First release after adoption

`.github/migration-policy.json` identifies the reviewed activation boundary. If
the previous release predates it, preparation stops until a migration note contains
an explicit audit of that entire legacy range, using the exact reported values:

```yaml
legacy_range:
  base: code/vX.Y.Z
  through: <full activation boundary SHA printed by plan>
```

That note must describe the reviewed legacy changes and their real impact. PR
#2808's delegation note is included when in range; it does not by itself certify
other unreleased work. Do not move the boundary or invent a no-operation audit to
make a release pass. No private customer repository is needed for this audit.

## Enabling mandatory enforcement

After the workflow PR merges and its status has been observed passing, add the
exact `Migration notes` status to the effective required checks on the release
branch. Preserve existing checks, review requirements and bypass settings. Inspect
both branch protection and active rulesets before and after the change. Verify the
status is required on a new PR; a missing-note PR must be blocked for ordinary
contributors. Existing administrator bypasses remain visible limitations.

A workflow committed in a PR is not yet merge enforcement. Keep the tracking issue
open until this post-merge activation is verified. Do not disable other checks or
publish a test release to demonstrate enforcement.
