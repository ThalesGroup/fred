## Context

See `proposal.md` for the incident and motivation. The current `assertCompleteCandidateAttemptHistory` mixes repository pagination with attempt ZIP validation and mutates `found`, `visibleRuns`, and cross-candidate state as each page arrives. It captures `total_count` from the first page and fails immediately if a later page reports another count. Run `39955383905` encountered exactly that condition (`9937 !== 9936`) after its current attempt had been retained and bound, but before `executeOrdinaryPublication` was called.

The current terminal model can already represent a completely untouched selection with empty `passedBoundaries` and `possiblyInvoked` arrays. However, it is written only inside `executeOrdinaryPublication`; failures in history and prior-terminal validation occur earlier and therefore skip the workflow's conditional terminal upload. Existing recovery rules correctly refuse to infer non-execution from that absence.

This change composes with the active `add-frontend-independent-releases` delta and modifies the same durable `frontend-package-archives` capability. It does not reopen the broader packaging RFC or relax candidate, attempt, registry, provenance, or workflow-history verification.

## Goals / Non-Goals

**Goals:**

- Produce a stable, duplicate-free artifact metadata snapshot despite unrelated concurrent artifact creation, with a small reviewed request bound and no partial-scan state reuse.
- Establish one auditable substitute for the missing terminal from `39955383905/1` using exact retained evidence plus independently retrieved GitHub execution evidence.
- Route every future trusted-attempt failure before the first package command through the existing terminal model and workflow upload path.
- Preserve the original candidate, all four attempts, the original three terminals, and the rule that npm publication commands are never automatically retried.

**Non-Goals:**

- Generalizing a missing terminal into proof of non-execution, accepting a log message without exact identity bindings, or weakening any fail-closed history condition.
- Dispatching or rerunning the workflow, publishing any package, creating a candidate, changing package versions, or changing npm/GitHub settings.
- Replacing the repository artifact and workflow-history APIs, increasing the existing 100-page safety ceiling, or solving artifact-retention policy generally.
- Synchronizing or archiving `add-frontend-independent-releases`; that change retains its existing external-execution tasks.

## Decisions

### 1. Separate stable metadata capture from artifact validation

Introduce a metadata-only snapshot phase in `release-artifact.mjs`. One full scan starts at page one, records the first `total_count`, requires every page to keep that count, requires full intermediate pages, rejects duplicate IDs, and requires the final unique ID count to equal the reported total. It returns no attempt-history facts unless complete.

Require two consecutive complete snapshots with the same count and exact artifact-ID set. Permit at most three full scan attempts for one history check. A drifted or structurally invalid scan is discarded wholesale; a later attempt starts with new local collections. Only the second matching snapshot is filtered by name and reviewed time boundary, and only then are matching attempt ZIPs downloaded and validated to build `found`, `visibleRuns`, and cross-candidate facts.

Three attempts cover the observed pattern - one scan disrupted by an unrelated addition followed by two stable scans - while bounding the worst case. Snapshot passes do not download ZIPs, so the added calls are metadata reads. The existing 100-page ceiling and all post-snapshot checks remain unchanged.

Alternative: ignore `total_count` drift and deduplicate IDs while continuing. Rejected because insertion ahead of the current page can still shift an unseen attempt across a page boundary. Alternative: use only workflow-run artifact listings. Rejected for this correction because it changes the reviewed completeness model and requires a broader proof across every run/attempt; it can be considered separately if the repository approaches the page ceiling.

### 2. Represent the incident as reviewed evidence, not a synthetic terminal artifact

Add a small schema-validated release evidence file for reviewed pre-command aborts, separate from the candidate policy digest and known-published ledger. The release contract cannot absorb this record because changing its digest would invalidate the retained candidate. The implementation accepts only the single #3278 entry and returns a distinct verified pre-command-abort boundary; it does not create or claim that GitHub retained a terminal artifact.

The entry binds:

- candidate artifact `12495715568`, ZIP SHA-256 `5b7e15824ebacedf4e80548d278401eaa4c8a6b99edeefbf0b58b4d1222c56c1`, record digest `sha256-ZDwbpqpg+29dNEvA06OjLuPjohLw4YvOZ/UQT3oqGBk=`, run `39937958215/1`, and source `a43ca854d946c6f8fd83a97d5144208f0d6710ba`;
- attempt artifact `12502631030`, ZIP SHA-256 `dfb5e71bd9be564de3ef66e69bd160c1ba16bc984d39f72931241d73ea0fa5b2`, record digest `sha256-SVRSPip7pDX8iyOMnb4Xw33eSlMokbThVIKhsQ5yuJw=`, run `39955383905/1`, and source `319ae36a37669c850db1029e234db3b9e89bc7dc`;
- publish job `120419935080`; successful attempt-upload and identity-binding steps; failed step 12, `Read back attempt and publish demonstrably absent archives`; skipped terminal-upload step; the exact count-drift assertion and historical stack locations from the retained job log; and all selected members as never invoked.

Verification reuses the already validated candidate and attempt records, fetches the exact attempt-specific jobs response and job log from GitHub, and compares every reviewed identity and step/log fact. It also requires the historical source commit and exact sole publication path named by the reviewed proof. Any unavailable or differing fact rejects the boundary. Tests demonstrate that the verified boundary participates in absence reconciliation without invoking the injected npm command.

The retained continuation inputs stay unchanged except for adding the fourth attempt reference:

| Evidence | Retained references |
| --- | --- |
| Candidate | `12495715568` |
| Attempts | `12496548593`, `12498651170`, `12499615655`, `12502631030` |
| Terminals | `12497865564`, `12497674336`, `12499571016` |

Alternative: infer the boundary from the failed step and missing terminal. Rejected because the step can fail after an npm command. Alternative: hand-create and upload a terminal for the old run. Rejected because it would not be an artifact retained by that historical execution.

### 3. Use the existing terminal model for every future trusted-attempt pre-command abort

Create one terminal writer around the existing `publishingTerminalModel` and use it in two disjoint phases:

1. After current-attempt readback and before entering ordinary publication, catch failures from prior-attempt history, prior-terminal checks, incident-proof checks, and other pre-command prerequisites. Write a terminal with no passed or possibly invoked members, then rethrow.
2. Inside `executeOrdinaryPublication`, extend the existing guarded region to include every validation and registry-reconciliation operation that occurs before or between commands. Its current prefix tracking remains authoritative after any command boundary.

The phases must not overlap. Once ordinary publication begins, only its tracked boundary state may create the terminal; an outer catch must never replace a failed or ambiguous post-command terminal with an all-never-invoked record. Failure before the current attempt has been independently verified remains terminal-ineligible.

The workflow keeps one `release-publisher.mjs execute` step and its existing later `failure()` terminal upload. `ci-selection.test.mjs` continues to assert ordering and the absence of a second publication path.

Alternative: add a separate preflight workflow step that writes a terminal. Rejected because splitting the checks from the sole publisher process would introduce another handoff and a gap between preflight success and command execution.

### 4. Keep recovery evidence and operational action separate

Implementation updates `libs/frontend/RELEASE.md` with the exact #3278 evidence and the future failure behavior, and adds an `impact: none` migration note. It does not embed a dispatch command with mutable reconstructed inputs in code or tests. After merge, a maintainer may separately dispatch a new protected publication using the original candidate, all four attempt refs, and the original three terminal refs; that external action requires explicit authorization and is not part of this change.

## Risks / Trade-offs

- [Two stable repository scans add GitHub API calls and latency] -> Scan metadata only, retain the existing page ceiling, allow at most three complete attempts, and download ZIPs only after stability.
- [Continuous unrelated churn can prevent two matching snapshots] -> Fail closed with an actionable retry-exhausted error; release safety takes precedence over availability.
- [GitHub logs or exact incident metadata can become unavailable] -> Reject the incident exception. The proof is intentionally non-portable and does not degrade to missing-terminal inference.
- [A broad exception ledger could become a routine escape hatch] -> Schema-check exact identities, ship only the single #3278 entry, require live evidence, and require a new reviewed spec/code change for any future exception. Future code produces ordinary terminals instead.
- [Incorrect catch placement could label a possibly invoked member as untouched] -> Keep pre-command and ordinary-publication catch domains disjoint, use the existing serialized prefix model once publication begins, and test failures on both sides of the first command boundary with an invocation counter.
- [The repository reaches the existing 100-page bound] -> Continue to fail closed. A different enumeration design is out of scope and must receive its own completeness review.

## Migration Plan

1. Merge the code, controlled tests, release runbook update, and `impact: none` migration note through the normal PR process. No deployment configuration or npm setting changes.
2. Do not rerun job `120419935080`. After the fix reaches `swift`, separately review the exact retained refs and authorize a new protected publish dispatch only if the candidate, all four attempts, original three terminals, and incident proof still verify.
3. Validate the resulting registry state and retained terminal/outcome evidence through the normal release workflow. A failed proof or exhausted stable scan leaves publication blocked.
4. Roll back repository code normally if needed. Already published npm versions remain immutable and are not rolled back or republished.
