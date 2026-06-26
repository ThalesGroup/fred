# Quality Review Protocol

Use this protocol when asking a human reviewer, Claude, or Codex to perform a
deep review of the Fred platform. It turns a vague quality audit into a scoped,
evidence-based review with repeatable outputs.

This is a review protocol, not a development plan. A reviewer must not edit code
or docs unless the request explicitly asks for fixes.

## Goals

- Find real defects, rule violations, architectural drift, duplicate logic, and
  missing validation.
- Separate what is proven by tests from what remains unproven.
- Make review scope explicit enough that skipped areas are visible.
- Produce findings that can become backlog items or direct fixes.

## Non-goals

- Do not replace unit, integration, or live-stack tests.
- Do not treat a green test campaign as proof that every related path is correct.
- Do not perform a full repository audit when a PR-scoped review is enough.
- Do not rewrite RFCs, contracts, or backlogs during review unless explicitly
  asked to make documentation changes.

## Review Modes

Choose one mode before starting. If the request is vague, use the smallest mode
that answers the actual question and state the choice.

| Mode                | Use when                                                         | Main output                                                |
| ------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------- |
| PR review           | A branch or PR changed specific files                            | Findings against the diff, missing tests, regression risks |
| Release readiness   | A branch is believed shippable                                   | Evidence matrix, blocking risks, remaining confidence gaps |
| Architecture drift  | Recent work may have duplicated or bypassed shared abstractions  | Shared-library use, duplicate logic, ownership violations  |
| Governance and docs | Documentation, RFCs, headers, backlog, or PMO state may be stale | Documentation drift and tracking inconsistencies           |
| Full audit          | The goal is broad health assessment                              | Combined report with explicit timebox and skipped scope    |

## Prompt Recipes

Use these as copy/paste prompts for Claude, Codex, or a human reviewer. Replace
the target and focus areas before running the review.

### PR Review

```text
Follow docs/swift/platform/QUALITY_REVIEW_PROTOCOL.md.
Mode: PR review.
Target: current branch vs <base-ref>.
Do not edit files.
Focus especially on: generated clients, shared-library reuse, duplicate logic,
auth/scoping, error handling, cleanup, and stale docs.
Run scripts/quality/quick_review_signals.sh <base-ref> if available.
Report findings first with file/line evidence, then commands run and skipped scope.
```

### Release Readiness

```text
Follow docs/swift/platform/QUALITY_REVIEW_PROTOCOL.md.
Mode: release readiness.
Target: current branch at HEAD.
Do not edit files.
Confirm branch/commit, working tree state, required local checks, live validation
evidence, generated-file consistency, and remaining confidence gaps.
Report blockers first, then the evidence matrix and residual risks.
```

### Architecture Drift

```text
Follow docs/swift/platform/QUALITY_REVIEW_PROTOCOL.md.
Mode: architecture drift.
Target: current branch vs <base-ref>, plus any recently shipped related code.
Do not edit files.
Focus on duplicated logic, bypassed shared libraries, parallel request models,
service ownership violations, generated-client drift, and contract divergence.
Treat green tests as evidence only for the paths they actually execute.
```

### Governance and Docs

```text
Follow docs/swift/platform/QUALITY_REVIEW_PROTOCOL.md.
Mode: governance and docs.
Target: docs, RFCs, backlogs, id registry, PMO board, and durable README links.
Do not edit files.
Check that RFCs are concise decision records, not implementation diaries; that
tracking files agree; that Apache-2.0 headers are present where required; and that
stale intermediate claims have been removed or amended.
Run scripts/quality/quick_review_signals.sh <base-ref> if available.
```

### Self-Test Confidence Review

```text
Follow docs/swift/platform/QUALITY_REVIEW_PROTOCOL.md.
Mode: release readiness with live validation focus.
Target: latest admin UI self-test campaign and the code paths it exercises.
Do not edit files.
Explain what the campaign proves, what it does not prove, whether any false-green
case remains plausible, and which next scenario would increase confidence most.
Use the self-test report as evidence, not as a substitute for code review.
```

## Standard Workflow

### 1. Intake and Scope

Record:

- Review mode.
- Target branch and commit.
- Base reference when reviewing a PR or branch diff.
- Whether fixes are allowed or the task is review-only.
- Areas deliberately excluded from scope.

If the target is ambiguous, inspect the local branch and ask only when a safe
assumption would change the review result.

### 2. Rule and Context Load

Read the required local rules before reviewing:

- Root `CLAUDE.md`.
- Root `AGENTS.md`.
- Any nested instruction file that applies to touched paths.
- `docs/swift/platform/DEVELOPER_CONTRACT.md`.
- `docs/swift/platform/PLATFORM_RUNTIME_MAP.md` when service ownership matters.
- `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` when touching
  `apps/frontend/src/rework/`.
- `docs/swift/platform/REBAC.md` when touching team access or authorization.
- The relevant design contract for API, runtime, session, or admin surfaces.

### 3. Repository State

Capture the review target:

```bash
git status --short --untracked-files=all
git branch --show-current
git rev-parse HEAD
git diff --stat <base>...HEAD
git diff --name-only <base>...HEAD
```

For a no-diff audit, replace the diff commands with the current tree scope being
reviewed.

### 4. Mechanical Checks

Run or inspect the checks relevant to the scope:

```bash
git diff --check <base>...HEAD
```

Also verify:

- Apache-2.0 headers are present where policy requires them, with explicit
  exemptions for generated files and files whose format cannot hold comments.
- Generated clients and OpenAPI files were regenerated, not hand-edited.
- Configuration changes are mirrored across model, schema, defaults, Helm values,
  and documentation.
- Markdown files touched by the review target are Prettier-formatted. Formatter-only
  table alignment churn is acceptable when it is produced by Prettier and called out.
- No new generated artifacts, build outputs, caches, or local secrets are tracked.
- New files are placed under the service or package that owns the behavior.

### 5. Validation Commands

Prefer repository Make targets from the touched project root:

```bash
make code-quality
make test
```

If only documentation changed, `git diff --check` is usually enough. State that
tests were skipped because the change is docs-only.

For Python typing, use the configured baseline path unless the task explicitly
requires raw type-check output.

### 6. Semantic Review

Challenge the change as if green checks can still hide bugs.

Review:

- Authorization and tenancy: team membership, admin gates, `include_non_public`,
  managed versus direct runtime paths, and cross-scope leakage.
- Lifecycle correctness: create, update, index, search, delete, cleanup, retries,
  idempotency, and partial failure behavior.
- Shared-library use: existing SDK clients, service helpers, schema models,
  contracts, generated types, and UI design-system components.
- Duplicate logic: copied request construction, ad hoc polling, parallel data
  models, repeated error handling, and repeated feature flags.
- Error surfaces: user-facing messages, logs, correlation IDs, exception masking,
  and cleanup after failure.
- Async and resource behavior: timeouts, cancellation, streaming, backpressure,
  large payloads, and dangling sessions or fixtures.
- Test meaning: whether tests exercise the real path, whether mocks hide the
  risky part, and which production paths remain untested.
- Documentation drift: design contracts, RFCs, backlogs, PMO board, README index,
  and operational guides.

### 7. Evidence Matrix

Summarize confidence by area:

| Area                         | Confidence          | Evidence                            | Gaps                                         |
| ---------------------------- | ------------------- | ----------------------------------- | -------------------------------------------- |
| Example: ingestion lifecycle | High / Medium / Low | Test name, command, file, UI report | Uncovered provider, race, or permission case |

Use "High" only when the review has direct evidence, not because the code looks
plausible.

## Findings Format

Lead with findings, ordered by severity.

```text
P1/P2/P3 - Short title
Evidence: file:line, command output, or test report
Impact: what can break or what rule is violated
Suggested fix: smallest safe correction
```

Severity guide:

- `P1`: likely production breakage, security issue, data loss, or release blocker.
- `P2`: real bug, missing required validation, architectural violation, or
  meaningful maintainability risk.
- `P3`: low-risk rule drift, documentation mismatch, or cleanup that should not
  block shipping.

If no issues are found, say that clearly and still list residual risks.

## Required Report Shape

Every deep review should include:

- Findings.
- Non-blocking risks.
- Evidence matrix.
- Commands run.
- Skipped scope.
- Suggested follow-up or backlog candidates.

Keep the report concise. Prefer concrete evidence over broad confidence claims.

## Swift-Specific Checklist

Generated API and clients:

- Backend OpenAPI source and generated clients stay in sync.
- `openapi.json` and generated TypeScript clients are regenerated by command, not
  hand-edited.
- Runtime, control-plane, knowledge-flow, and evaluation clients use the shared
  generated layers where available.

Configuration and deployment:

- Configuration model, defaults, `configuration.schema.json`, Helm values, Helm
  schema, and deployment docs agree.
- Production configuration files do not introduce secrets or local-only values.

Contracts and ownership:

- Runtime execution behavior matches the runtime execution contract.
- Product, admin, prompt, session, and self-test behavior match the control-plane
  product contract.
- Service responsibilities match the platform runtime map.

Frontend:

- Rework UI uses design-system atoms and CSS variables.
- No hardcoded CSS colors, uncontrolled visual fallbacks, or duplicate API client
  logic.
- Loading, error, empty, permission, and narrow viewport states are covered when
  user-facing behavior changes.

Authorization and scoping:

- Admin-only actions are server-enforced.
- Team scope and folder or library scope are tested for both positive and
  negative access.
- Search and research paths prove absence across scope boundaries, not just
  presence in the happy path.

Documentation and governance:

- RFCs are concise records of decisions, alternatives, and contract impact.
- Backlogs and `docs/swift/data/id-legend.yaml` agree when tracked work changes.
- PMO board mirrors PMO-visible tracking changes.
- README index points to new durable documentation.

Live validation:

- UI self-test reports are strong evidence for end-to-end wiring on the tested
  path.
- A passing self-test does not prove ranking quality, all providers, all roles,
  concurrency, failure recovery, or long-running data retention behavior.

## Reviewer Discipline

- Do not edit files during a review-only request.
- Do not run destructive commands.
- Do not invent new architecture or new required process from one review.
- Do not report "all good" unless commands, files, and skipped areas are stated.
- Do not convert every observation into a blocker.
- Do not ask for a full audit when a narrow PR review will answer the question.
