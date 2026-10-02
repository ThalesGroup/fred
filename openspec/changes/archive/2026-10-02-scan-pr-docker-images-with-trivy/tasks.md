## 1. Pull request scan

- [x] 1.1 Load the four publishable pre-merge matrix builds under local Docker tags and verify all five images still build, including `ws-bench` with its explicit scan exception, while publication settings stay intact.
- [x] 1.2 Run Trivy against the four local images, emit a warning and summary for critical findings, and retain the JSON report; verify clean results and scanner failures have distinct outcomes.

## 2. Delivery

- [x] 2.1 Add the required no-impact migration note and run the targeted migration and workflow validation checks.
- [x] 2.2 Push a dedicated branch, open a draft PR linked to the issue, and inspect the PR Docker matrix and migration checks on GitHub.

## 3. Always-on pull request scanning

- [x] 3.1 Remove the changed-file filter so every pull request scans the four publishable final images after building all five images; keep release publication and the `ws-bench` exception unchanged.
- [x] 3.2 Report all severities and all detected packages, print every finding in the GitHub job logs, and emit warnings only for critical findings.
- [x] 3.3 Scan every tracked Python and npm lockfile with development dependencies included; verify that expected lockfiles appear in the report.

## 4. Visible Trivy checks

- [x] 4.1 Add one report job per scanned image and verify the resolved matrix excludes `ws-bench` and release runs.
- [x] 4.2 Verify on the draft PR that the Trivy jobs appear separately, annotate findings as warnings, and stay successful when CVEs are present.
- [x] 4.3 Validate workflow syntax, scan report parsing, full lockfile coverage, and the updated operator migration note; inspect the new PR CI run.
