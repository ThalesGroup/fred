# Verification

## Local evidence

- 22 offline tests pass against temporary Git repositories. Coverage includes PR
  merge-base isolation, mandatory declarations, configuration evidence, Alembic
  impact, note retention/immutability, merge contributions, explicit coverage,
  legacy audit, version/prerelease progression, deterministic generation, exported
  links, persisted baseline selection, stale guides and paired tag checks.
- Actionlint 1.7.7 passes on the four changed/new GitHub workflows.
- Ruff check and format pass on the helper and its tests; Python compilation passes.
- OpenSpec strict validation passes. The shared push-release skill passes the Codex
  skill validator; unsupported Claude-only metadata was removed without changing
  its default availability.
- Independent correctness/CI review found two issues: disappearing unreleased
  notes and loss of an explicit baseline at publication. Both were fixed with
  regression tests and independently rechecked without remaining findings.
- Independent read-only skill walkthrough correctly stopped before tags and
  identified the outstanding legacy audit. Branch preflight and full-publication
  completion wording were improved from that walkthrough.

Root `make code-quality` also passed across all modules, using existing local
dependency environments in the isolated worktree (`UV_NO_SYNC=1 UV_OFFLINE=1`,
`MAKE='make -o dev -o node_modules'`). Its migration-tests prerequisite ran the
22 new offline tests. The first setup attempt hit an uncached development wheel;
no dependency or lockfile changes were needed to complete verification.

## Real branch dry run

The draft helper selects code/v2.2.3 on the actual first-parent history. It includes
PR #2808's delegation procedure and this tooling's declaration, proposes at least
2.3.0, rejects 2.2.4, and blocks release generation pending a reviewed legacy audit
through 3dbb8c717dc13f7aec1a6be2f36d64682abe1b9f. This is an expected block, not a
completed audit or a final version decision. A major legacy finding would raise
the minimum. No release tags, publication or production changes were performed.

## Remaining external acceptance

Draft PR #2811 is open. The new `Migration notes` check passed on GitHub at
83b623c6737cf936972048058c2653d96bb1436e (run 36214806104). Other initial CI
checks were still running when this evidence was recorded. Mandatory GitHub protection
activation must follow merge and an observed successful run; the issue and change
remain open until effective enforcement is verified. Customer upgrade acceptance
and the first actual release audit remain separate operator/release tasks.
