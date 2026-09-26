---
schema: 1
title: Required migration declarations and release guides
impact: minor
configuration: none
configuration_reason: Only development and release tooling changes; deployed application values and schemas are unchanged.
covers:
  - 54340e22a0039ce74bf6523a56430449607750c1
---
## Applicability

This change affects Fred contributors and release operators. Applications do not
need new runtime configuration. New release publications require a validated
migration guide and sufficient paired code/chart version numbers.

## Prerequisites

Release tooling needs Python 3.12, uv and full Git history and tags. It reuses
fred-pod's pyproject.toml and committed uv.lock for its existing PyYAML dependency. Repository administration is needed to activate the required
PR status after this workflow lands. Existing private customer repositories stay
under DevOps ownership.

## Configuration

No application values change. After merge and a successful run, add `Migration
notes` to the effective required GitHub checks without replacing existing checks
or changing bypass policy. See the migration workflow guide for rollout verification.

## Upgrade

1. Merge the validated tooling PR and verify its PR check is available on the base.
2. Activate the required status in GitHub and verify it is enforced.
3. Before the first release, audit the changes between the previous stable code
   tag and the policy activation boundary. Add a note with the exact legacy_range
   metadata; do not assume older unclassified changes need no operations.
4. Prepare a release note, generate the guide, review combined ordering and rollback,
   and approve a version meeting the maximum operational impact before tagging.

## Validation

Run the offline migration helper tests and the `check-pr` command. Dry-run `plan`
against the intended release baseline. An incomplete legacy audit must block
release generation, and a missing or stale guide must block publication.

## Rollback

Use a reviewed tooling change to revert enforcement if necessary, preserving
published guides and source notes. Do not silently disable checks to publish a
release. No runtime or customer database rollback is required for this tooling.

## Limitations

Structural checks cannot judge the correctness of migration instructions. Reviewers
must verify the classification, combined operations and rollback. GitHub protection
activation is a separate post-merge step and is not complete merely because this
workflow exists. No release or production migration is executed by this change.
