## 1. Resolve current alerts

- [x] 1.1 Upgrade PyJWT across current Python locks and verify every lock resolves at least 2.14.0.
- [x] 1.2 Upgrade Knowledge Flow's vulnerable direct and transitive packages, including a published torch/torchvision pair, and verify `uv lock --check` plus fixed version thresholds.
- [x] 1.3 Upgrade affected npm dependencies in both frontend projects and verify clean `npm ci` and fixed version thresholds.

## 2. Verify compatibility

- [x] 2.1 Run focused authentication tests for PyJWT consumers and record pass/fail results.
- [x] 2.2 Run Knowledge Flow import and ingestion checks after the ML upgrades and record pass/fail results.
- [x] 2.3 Run relevant frontend builds and package tests; verify no affected npm lock resolves a vulnerable release.

## 3. Close out

- [x] 3.1 Verify the 98 obsolete-path alerts against live replacement manifests; one alert has an auditable dismissal.
- [x] 3.2 Record the requester's decision to leave the 97 remaining obsolete-path alerts open for later triage.
- [x] 3.3 Add and validate the English migration note with accurate deployment and rollback guidance.
- [x] 3.4 Reconcile this change with the final diff, run repository checks and a cold diff review, then push a draft PR linked to issue #2854.
