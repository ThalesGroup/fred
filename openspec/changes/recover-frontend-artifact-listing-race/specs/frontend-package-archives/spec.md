## ADDED Requirements

### Requirement: Retained publication history tolerates unrelated artifact churn

Before classifying a selected coordinate as absent or invoking any publication command, the publisher SHALL obtain a bounded, complete repository artifact snapshot whose reported count and unique artifact-ID set are stable across consecutive full enumerations from page one. If an enumeration observes count drift, duplicate IDs, missing pages, a set change, or any other inconsistency, the publisher MUST discard the entire partial result, including collected attempt IDs and visible-run state, before retrying. It MUST fail closed when the bounded retry allowance is exhausted. Only after a stable snapshot is established MAY retained attempt archives be downloaded and checked against the candidate, coordinate-history boundary, manual references, and workflow run history.

#### Scenario: An unrelated artifact is added during enumeration

- **WHEN** the repository-wide artifact count or ID set changes while a retained-attempt scan is paging
- **THEN** the publisher discards that scan, restarts at page one, accepts a later stable complete snapshot without omitting or duplicating retained attempts, and invokes no npm command during the retry

#### Scenario: Artifact churn does not settle within the bound

- **WHEN** no two consecutive complete enumerations produce the same valid count and unique artifact-ID set within the reviewed retry allowance
- **THEN** publication stops with an actionable incomplete-history failure and no npm command is invoked

#### Scenario: Stable history is still incomplete or unsafe

- **WHEN** a stable artifact snapshot omits a supplied attempt, contains an unreferenced attempt for the candidate, exposes an expired or unavailable attempt, or reveals a selected coordinate attempted by another retained candidate
- **THEN** the existing fail-closed history checks reject publication rather than treating snapshot stability as evidence that the coordinate is safe to publish

### Requirement: The known missing terminal is accepted only by exact pre-command proof

The missing terminal for run `39955383905`, attempt `1`, SHALL establish that no selected package command was invoked only when a source-reviewed incident record and live GitHub evidence all match: source commit `319ae36a37669c850db1029e234db3b9e89bc7dc`; publish job `120419935080`; retained attempt artifact `12502631030`; ZIP SHA-256 `dfb5e71bd9be564de3ef66e69bd160c1ba16bc984d39f72931241d73ea0fa5b2`; record digest `sha256-SVRSPip7pDX8iyOMnb4Xw33eSlMokbThVIKhsQ5yuJw=`; the exact candidate and selected-member bindings; successful attempt upload and identity-binding steps; and the failed sole publication step whose retained log proves `assertCompleteCandidateAttemptHistory` aborted before `executeOrdinaryPublication`. The completed run, job, step sequence, and log evidence MUST be obtained independently from GitHub. Unavailable, omitted, forged, or mismatched evidence MUST fail closed. No other missing terminal SHALL establish non-execution by analogy, a registry 404, or absence alone.

#### Scenario: Exact incident proof reconciles the untouched selection

- **WHEN** all source-reviewed fields and independently retrieved run, job, step, log, candidate, and retained-attempt evidence match the exact `39955383905/1` incident
- **THEN** reconciliation may classify every member selected by that attempt as never invoked by that execution while preserving the attempt in complete history

#### Scenario: The incident proof is incomplete or altered

- **WHEN** any artifact identity, digest, source commit, run, attempt, job, step outcome, log signature, candidate binding, selected member, or ordering fact differs or cannot be retrieved
- **THEN** reconciliation rejects the exception, invokes no npm command, and continues to treat the missing terminal as ambiguous

#### Scenario: Another attempt has no terminal

- **WHEN** any attempt other than the exact reviewed `39955383905/1` incident lacks a verified terminal or equivalent separately reviewed proof
- **THEN** absent registry metadata does not establish non-execution and continuation stops before publication

### Requirement: Future pre-command failures retain explicit non-invocation evidence

After the current publishing attempt has been durably uploaded and independently read back, any failure before the first selected package crosses its command boundary SHALL create an aborted terminal bound to that exact candidate, attempt digest, execution, and selected order, with an empty passed-boundary prefix, an empty possibly-invoked set, and every selected member in the never-invoked suffix. The sole workflow publication step MUST fail after writing that record, and the later failure-only terminal upload step MUST be the only path that retains it. A failure before the attempt itself can be trusted MUST NOT fabricate terminal evidence.

#### Scenario: History validation fails before the first package command

- **WHEN** retained-attempt enumeration, prior-terminal verification, registry preflight, or another checked prerequisite fails after current-attempt readback and before any package command boundary
- **THEN** the failed run writes and uploads a bound terminal marking every selected member never invoked, and no npm publication command runs

#### Scenario: Pre-command terminal retention does not complete

- **WHEN** the terminal cannot be written, uploaded, or independently verified after a future pre-command failure
- **THEN** a later continuation remains blocked and MUST NOT infer non-execution from the failed run or missing terminal

#### Scenario: The current attempt is not independently trusted

- **WHEN** current-attempt upload, API identity, ZIP digest, record digest, candidate binding, or execution binding fails validation
- **THEN** publication stops without an npm command and without creating a terminal that could falsely authenticate that untrusted attempt
