---
name: weaver-check-fix-or-remove
description: Examine the relevance of Fred tests during the Weaver and ReBAC migration, then fix the code, adapt or remove the tests according to the contracts still valid. Use for test failures or a targeted request to triage migration tests, without triggering a general audit.
---

# Weaver: check relevance before repairing

The expected result is useful coverage of Fred's agreed behavior. A green test
is not enough: do not preserve an abandoned Swift mechanism, nor remove a
guarantee that is still needed because its test fails.

Read the active checkout's `AGENTS.md` and `fred-reconstruction-method`. Apply
production code reduction, reuse and removal of replaced paths, without
weakening guarantees or removing useful tests.

## Establish the contract

- Locate the requested checkout, read its applicable instructions and the skills
  they require. Use the active checkout's paths, without a fixed personal Fred
  path. Check the branch and the changes already present.
- Start from the failures provided and announce a bounded batch. Read the
  assertions, fixtures, mocks, producer and consumer contracts, and the path
  actually executed. Trace back to the first causal failure behind a generic
  HTTP error.
- State what each test protects, independently of its implementation.
  Distinguish the current observed behavior, the accepted Weaver target and the
  historical Swift behavior. Consult the repository's relevant decisions; neither
  the current code nor an old specification alone establishes the expected
  behavior. A written target is not an already integrated path.
- A migration gap is not obsolescence. If the expectation remains ambiguous,
  state the missing decision and proceed with the independent cases.

## Choose and apply

| Supported diagnosis | Action |
| --- | --- |
| Guarantee still required, code regressed | Fix the code and keep an assertion that detects the regression. |
| Useful guarantee, fixture or assertion tied to an old contract | Adapt the test to the real Weaver contract while preserving its scope. |
| Behavior explicitly abandoned, no residual guarantee | Remove the test and only the fixtures that became unused. |
| Truly redundant coverage | Merge or remove, naming the kept test and the cases it covers. |
| Failing environment or dependency | Fix the test configuration in the batch, or report the blocker without changing the business expectation. |
| Required function but incomplete migration | Make the gap explicit; do not declare the test obsolete nor implement the whole migration outside the batch. |

A "check and fix or remove" request asks for the justified fixes to be applied
in the batch, not just a report. A diagnosis-only request stays read-only.
Respect other authors' changes in progress.

Before a removal, search for the relevant static and dynamic usages
(registration, configuration, routes, identifiers). Identify the decision that
abandons the behavior or the coverage that replaces it. Preserve useful negative
cases and any security guarantee carried by an old test. The absence of a Weaver
implementation does not prove the guarantee has disappeared.

For ReBAC, preserve the guarantees at the agreed boundaries: reliable identity,
delegation, isolation, admission, resource access and lifecycle. Reread the
repository's current trade-offs on their timing; do not copy an old verification
strategy into the new model.

## Avoid false fixes

- Do not weaken a production validation or add a permissive default to accept an
  incomplete mocked response. Also check the real producer.
- Mock external dependencies at the right level. Do not short-circuit the
  mechanism the test claims to verify, notably admission or streaming.
- Do not recreate a Swift fallback, alias or parallel authorization path to save
  an inherited test.
- Do not replace a failure with `skip`, `xfail` or a weaker assertion to get
  green. Distinguish failures from expected `xfail`s; extend the examination to
  the latter only if they explain the problem or are part of the request. An
  upstream problem must have precise evidence and a re-examination condition.
- Reuse a shared fixture when it is accessible and suitable; do not add an
  abstraction or a cross-suite import just for one line.

## Verify and report

Apply the formatting and quality checks the repository requires. Respect its
test execution scope and the user's request: an authorized rerun starts with the
tests concerned and the affected neighbors, without an automatic general
campaign. If the tests are not run, say so explicitly.

Give a short report: test or group, protected guarantee, decision and evidence,
files changed, commands actually run and results. For a removal, state the
coverage kept or why it no longer applies. Separate static diagnosis, test
success and product validation. Do not recreate an RFC workflow or a parallel
journal. A commit or a PR requires the user's authorization.
