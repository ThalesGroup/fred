## 1. Pull request scan

- [x] 1.1 Load each pre-merge matrix build under a local Docker tag and verify the reusable workflow still selects the same five images and preserves publication settings.
- [x] 1.2 Run Trivy against each local image, emit a warning and summary for critical findings, and retain the JSON report; verify clean results and scanner failures have distinct outcomes.

## 2. Delivery

- [x] 2.1 Add the required no-impact migration note and run the targeted migration and workflow validation checks.
- [ ] 2.2 Push a dedicated branch, open a draft PR linked to the issue, and inspect the PR Docker matrix and migration checks on GitHub.
