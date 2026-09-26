# PR migration notes and release guides

Every PR adds an English note under `docs/swift/ops/migrations/<unique-slug>.md`.
Copy [the template](MIGRATION-NOTE-TEMPLATE.md), including for documentation-only
changes, and replace every placeholder. The `Migration notes` check validates the
PR contribution, not changes made by someone else on the base branch.

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
values are unaffected. Source-path heuristics catch common cases but cannot infer
all configuration changes: the developer and reviewer remain responsible.

Required body sections are Applicability, Prerequisites, Configuration, Upgrade,
Validation, Rollback and Limitations. Write specific steps or a reason the section
does not apply. For example, state default values, behavior when omitted, affected
pods, drain/restart order, observable success criteria and rollback security/data
limits. Do not commit customer secrets or private deployment values.

Optional `after: [other-note-slug]` orders dependent procedures. Cycles or unknown
identities fail. Optional `covers: [full-commit-SHA]` explicitly acknowledges a
previous uncovered direct/development contribution after reviewing its actual
impact; it is not a blanket exemption. First-parent merge contributions need one
note for the aggregate PR, not one per internal commit. Rebase/direct sequences
without per-contribution notes need explicit coverage in a subsequent note.

Published notes are immutable. Add a correction note; never delete or rename
existing fragments, including unreleased notes. An unreleased note can be corrected, but that does not replace the new
PR's own declaration. Keep related procedures ordered and avoid contradictory
instructions. CI checks structure and known risk signals, not operational truth.

## Local checks

From the repository root, install the helper's pinned dependency in your selected
Python environment, then run:

```bash
python -m pip install -r scripts/migration-requirements.txt
python scripts/migration_guides.py check-pr --base origin/swift --worktree
make migration-tests
```

`--worktree` includes tracked and untracked note edits for preparation. CI instead
reads the exact commit. Use a full checkout with tags; missing history is an error.

## Preparing a release

Run the shared `push-release` skill (`.agents/skills/push-release` also serves
Codex). Its version calculation is driven by migration impact:

```bash
python scripts/migration_guides.py plan
```

The helper chooses a stable code tag on this branch's first-parent ancestry, not
the largest tag from another branch. An explicit `--base code/vX.Y.Z` must resolve
to a stable ancestor tag. When used during generation, the reviewed baseline is
recorded in the guide and reused by publication verification. Candidates compare against the preceding stable release;
promotion from an RC to stable keeps the same eligible core version.

Inspect every commit since the baseline, including changes not suitable for UI
release notes. Resolve the reported coverage blockers. Add a new note for the
release-preparation contribution itself (normally `none`). For a chosen version:

```bash
python scripts/migration_guides.py generate --worktree --version X.Y.Z
python scripts/migration_guides.py verify --worktree --version X.Y.Z
```

The result is `docs/swift/ops/releases/vX.Y.Z/migration.md`. It combines source notes
in dependency order, links them to their release tag and lists no-operation notes
compactly. Review the complete procedure for interactions, duplicate actions and
ordering before sign-off. Fix source notes and regenerate rather than editing the
generated guide. Keep `apps/frontend/public/release.md` focused on user changes;
operator procedures are outside the UI.

Commit the guide, source notes and UI release notes before placing tags. Verify
again against the committed tree before tagging. Both annotated tags must point
to that commit. The two publication workflows validate the guide and version and
wait a bounded time for the matching tag before pushing images/charts. Each GitHub
release attaches the same `migration.md`. Chart.yaml's release version is injected
at build time; never bump its placeholder manually for each PR.

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
