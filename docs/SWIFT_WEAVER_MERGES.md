# Integrating Swift into Weaver

Use this procedure for a bounded Swift integration. GitHub issues and PRs own
scope, decisions and acceptance; [arc42](architecture/README.md) owns current
architecture. Follow [AGENTS.md](../AGENTS.md). The old porting journal is frozen
historical evidence and must not be extended or treated as current instructions.

## Establish the scope

Fetch the current references and inspect the working tree. Pin the Weaver base,
the last integrated Swift commit verified from merge parents, and the incoming
Swift target in the issue/PR. Do not infer integration from a branch name or move
the boundary after a cherry-pick. Report divergent history before choosing a range.

Keep two inventories in the existing issue: newly arrived Swift behavior and
previously deferred work still relevant to Weaver. Git ancestry does not prove
that a feature was retained; merging again cannot replay an excluded ancestor.
Check existing domain epics and delivery evidence before reopening old work.

## Integrate through current owners

Describe the user outcome, then classify each change as direct reuse, Weaver
adaptation, already covered, deferred or excluded with a specific reason. Do not
discard a useful behavior merely because Swift implements it in a retired owner.

Preserve Control Plane authority, direct space permissions, trusted runtime
admission and current document ownership. Do not restore Python Control Plane,
OpenFGA, retired ingestion paths or Swift migrations. Use current arc42 references
and executable contracts rather than copied historical rules.

Reuse a suitable checkout and existing primitives. When a merge is authorized,
review the result against both parents, including reused conflict resolutions.
Never resolve the whole integration with ours/theirs or rewrite shared history.
Generate public clients from the merged owning contracts; do not hand-edit them.

## Reconcile dependencies separately

Keep Weaver's Fred package/chart release line and dependency bounds, while
comparing third-party manifest requirements and resolved lock versions. Include
updates already in Git ancestry and moved consumers in their current owner.

A clean merge or `uv lock --check` does not prove that an upstream update survived.
Plain `uv lock` preserves compatible locked versions. Recover an omitted update
with `uv lock --project <owner> --upgrade-package <package>==<reviewed-version>`;
inspect the generated diff and check consistency. Do not replace Weaver locks
wholesale or upgrade unrelated dependencies.

## Record acceptance and close the increment

Run affected quality checks and only the functional checks agreed for the scope.
Record actual results and limits in the PR. Source, compilation and mock checks
are distinct from operator acceptance on a deployed platform. Keep required
remaining reception in its issue with an owner; do not append a repository report.

Use the existing [operator-note workflow](../deploy/release-notes/README.md).
Update arc42's existing explanation only within its validation boundary. Keep
Weaver release history distinct from Swift release metadata. Record the final
merge and deferred issue links so the next integration can recover its boundary.

Commits, pushes and deployments follow the authorization rules in AGENTS.md.
Before removing a branch or checkout, verify integration, recoverability and the
absence of other active work. Git history preserves historical integration notes;
no parallel archive or tracking file is needed.
