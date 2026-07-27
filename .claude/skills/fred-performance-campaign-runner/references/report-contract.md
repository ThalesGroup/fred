# Campaign report contract

## Evidence bundle

Each run directory must contain:

- `campaign.json`: version, repository state, immutable campaign parameters,
  stage outcomes, stop reason, and artifact paths;
- `report.md`: concise operator-readable table and verdict;
- `<stage>.json`: benchmark machine summary;
- `<stage>.stdout.log`: redacted benchmark output;
- `<stage>.mock.before.json` and `.after.json`;
- `<stage>.runtime.metrics` and `<stage>.control-plane.metrics`;
- `mock.stdout.log` only when the runner owns the mock process.

The token and prompt must not appear in any artifact. Do not copy environment
dumps, authorization headers, browser storage, or unredacted request bodies.

## Required comparisons

Use the 1x10 baseline p50 and p95 as the reference. For every stage report:

- total, success, error rate, requests/second;
- p50, p95, p99, max;
- p50/baseline-p50 and p95/baseline-p95;
- mock started/completed/error deltas;
- whether host guards remained healthy;
- event-loop lag, runtime stage, ReBAC, persistence, LLM, and total-turn
  evidence when present.

Do not call a single sample a trend. Treat a dramatic first campaign as a
finding to repeat under the same setup before proposing architectural work.

## Finding template

```markdown
# PERF-XXX — <specific symptom>

- Status: observed | confirmed | resolved
- Run: <artifact path>
- Commit / worktree:
- First affected stage:
- User-visible impact:

## Evidence

Observed facts and exact values.

## Interpretation

Derived values, followed separately by hypotheses.

## Proposed change

Smallest plausible intervention. Leave blank when more evidence is needed.

## Validation

Controlled rerun and explicit acceptance threshold.
```

## Default acceptance envelope

- no terminal execution errors in preflight or baseline;
- stage error rate at or below 1%;
- p50 no more than 3x baseline at every consolidation stage;
- no sustained event-loop lag above 100 ms when that metric is available;
- mock reports the expected model and zero errors;
- recovery 1x3 succeeds after an opt-in overload stage.

These are regression-discovery guards, not production SLOs. Change them only
with an explicit reason recorded in `campaign.json`.
