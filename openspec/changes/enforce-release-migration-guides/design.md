## Context

See proposal.md for motivation and issue #2809. The existing shared push-release
skill writes frontend release notes and recommends a patch by default. Paired
code/chart tags trigger separate publication workflows; chart version/appVersion
are injected at build time, so editing Chart.yaml on every PR is unnecessary.
The schema workflow already validates backend and chart configuration. PR #2808
added an operator note under docs/swift/ops/migrations, currently without structured
metadata. No existing specification covers operator release guides.

## Goals / Non-Goals

Goals: one maintained migration source per PR, reproducible release guides,
mandatory classification and publication checks, useful output without access to
customer deployment repositories.

Non-goals: execute customer migrations, publish a release during implementation,
change application behavior, replace existing schema validation, or infer that a
syntactically complete note is operationally correct. No changes to independently
published frontend npm package version policy.

## Decisions

### 1. Extend the existing migration-note home

Keep notes in `docs/swift/ops/migrations/<unique-slug>.md`, allowing the existing
2808 filename. Use YAML front matter with schema version, title and impact
(`none`, `minor`, `major`). Impact describes deployment work, not conventional
commit prefixes. Body sections: applicability/feature switches, prerequisites,
configuration, ordered upgrade steps, validation, rollback and known limitations.
Every section must contain substantive text, including explicit "not applicable"
with a reason where appropriate. Reject empty fields, unknown impact, duplicate
metadata keys and template placeholders. For `none`, require a concrete reason
why normal deployment is sufficient. Conditional activation counts as minor even
when an ordinary upgrade requires no action; substantial incompatibility is major.

A PR adds at least one new note, rather than merely editing an older note. An
unreleased note can be corrected, but not used as the sole declaration for a new
PR. Published notes cannot be deleted or rewritten; corrections ship as new notes.
Unreleased notes cannot be deleted/renamed either: doing so could silently discard
an earlier contribution's migration impact. Their content remains editable before
publication.
Keep filenames independent of PR numbers so authors can prepare a note before
opening a PR. PR links can be added once known. All repository content is English.

A template alone was rejected: it does not prevent missing notes. A label-only
classification was rejected: it does not travel with git tags or explain steps.

### 2. One helper for PR checks and release preparation

Reuse the existing fred-pod pyproject.toml and uv.lock (which already declare
PyYAML) through `uv run --project libs/fred-pod --locked --no-dev`.
No separate requirements file or Python project is added.
Add a focused Python helper and offline tests under scripts. Commands cover note
validation against a PR merge base, release planning, guide generation and
verification. Reuse the same parser/selection/version logic everywhere. CI fetches
full history and tags, uses explicit refs, treats filenames/ref inputs as data,
and never evaluates Markdown as commands. No customer secrets or external services
are required by the helper.

PR validation runs on every PR, including docs-only changes and forks, with a
stable `Migration notes` job name, read-only token, no secrets and no path filter.
Use pull_request rather than pull_request_target. Reconcile at the merge base so
base-branch changes cannot satisfy the PR's note requirement. Handle merge groups
if a merge queue is enabled. Existing config/schema checks remain authoritative
for generated schemas. New Alembic revision files require at least minor; declared
configuration changes require a chart values update or a specific, reviewable
explanation that production configuration is unaffected. A comment-only values
edit alone does not prove configuration compatibility.

Reviewers decide semantic correctness, configuration completeness, dependency
ordering and rollback safety. Do not claim path heuristics can prove these.

### 3. Release range and artifact

Determine the previous stable code release from the target branch ancestry, not
the greatest repository-wide version string. Allow an explicit ancestor baseline
for maintenance branches; fail on a missing/invalid baseline or ambiguous selection
rather than guessing. Validate stable SemVer and supported prerelease syntax.
For a release candidate, compare the core version to the preceding stable release;
promotion to stable reuses the same core version and regenerates its guide.

Select notes added since that baseline, including corrections and notes from merged
branches. Modified already-published notes fail. Preserve original source notes;
never delete fragments after aggregation. Deterministically generate
`docs/swift/ops/releases/vX.Y.Z/migration.md` with baseline, target version, maximum
impact, ordered operator instructions, conditional activation and rollback limits,
plus traceable source links. Keep no-operation declarations visible in a compact
section. Fix relative links when embedding note contents so the exported guide
remains usable outside the source directory. Human review must reconcile cross-PR
ordering/conflicts before approving a release; concatenation is not proof that
independent procedures compose safely.

Generation must support a release preparation working tree and verification from
the tagged commit without dependence on a self-referential commit SHA or current
time. Verify generated output byte-for-byte at publication, reusing the reviewed
baseline recorded in its header (and revalidating that tag and ancestry). Both GitHub code and
chart releases attach the same committed guide as `migration.md`; it remains out
of frontend public assets. Existing UI release notes stay concise and user-facing.

### 4. Version and publication gates

Maximum impact across the range sets the minimum increment: none -> patch,
minor -> minor with patch reset, major -> major with minor/patch reset. Reject
non-increasing or insufficient target versions. A deliberately larger increment
must be visible at release sign-off; the helper never silently downgrades a major
requirement. Code/chart tags use identical versions and point to the same commit.

Add a reusable validation job before image publication on code tags and before
chart publication on chart tags. Branch image builds keep their existing behavior.
Both tag workflows fail before pushing artifacts for an invalid/missing guide,
insufficient version or mismatched tag pair. Fetch/verify the tag pair with a bounded
retry to tolerate tag propagation; do not publish a partial pair silently.
Update push-release to use the helper, present both UI notes and operator guide,
and retain explicit approval before creating/pushing tags. Push named tags only.

### 5. Adoption and ownership

Convert PR #2808's existing note in place to the structured format, preserving
its conditional activation and rollback warning; classify it minor. The first
release under this policy also needs an explicit audit of all changes from the
previous release up to enforcement adoption. Earlier changes cannot be presumed
safe merely because they predate the note requirement. Represent that bounded
legacy audit as a migration note identifying the covered commit range and its
actual impact; fail initial release preparation while coverage is unacknowledged.
Do not claim this one feature note covers the whole unreleased branch.

Add an explicit policy activation boundary so checks can distinguish legacy
history from commits subject to the new rule. Release validation also detects
post-boundary direct/merge commits introducing changes without note coverage;
reject uncovered ranges rather than declaring an empty set a patch release.
Associate merge contributions with their aggregate diff; do not require one note
per development commit inside a PR.

Update CLAUDE.md, the PR template, configuration conventions, release strategy and
the shared skill. Developers maintain Fred values and schemas in the configuration
PR. DevOps reconcile privately owned customer overlays using published chart
versions and migration guides. Local configuration_prod.yaml files remain local.

After this implementation PR is merged and the new status is observed passing,
add the exact status to existing branch protection/rulesets without replacing
other settings. Verify effective enforcement. Do not claim the workflow alone
prevents merging until this external activation is done. Keep bypass behavior
explicit and unchanged; protecting this governance code with reviewer ownership
can be considered separately if needed.

## Risks / Trade-offs

- Incorrect `none` classifications -> meaningful rationale, deterministic high-risk
  checks and human review; no pretense of automatic semantic validation.
- Incomplete legacy coverage -> explicit first-release audit and blocking transition
  check; no blanket exemption inferred from old commits.
- Branch/tag ambiguity -> ancestry-based baseline, fixture tests with unrelated
  branches, explicit failure on insufficient history.
- Conflicting migration procedures -> ordered guide reviewed before tags, with
  environment-specific steps and limitations stated rather than guessed.
- Bootstrap lockout -> install/merge workflow first, require observed status second.
- Editing validation code in a PR -> read-only PR execution, normal code review and
  protected target branch; not an adversarially tamper-proof policy engine.

## Migration Plan

1. Implement and test the helper, workflows, note template and shared instructions;
   include the existing delegation note and this change's own declaration.
2. Open a draft implementation PR with dry-run evidence; no release tags or
   production migration. Merge after review and green CI.
3. Activate the mandatory GitHub check preserving existing protections.
4. Before the first real release, audit the legacy range, generate the guide,
   check the minimum version and obtain normal release sign-off.
5. Rollback of this tooling requires an explicit reviewed policy change; keep
   published guides and notes. Do not silently remove required checks to unblock
   a release. Runtime and customer data are unchanged by installation.
