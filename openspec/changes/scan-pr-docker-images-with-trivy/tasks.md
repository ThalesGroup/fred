## 1. Pull request scan

- [x] 1.1 Load the four publishable pre-merge matrix builds under local Docker tags and verify all five images still build, including `ws-bench` with its explicit scan exception, while publication settings stay intact.
- [x] 1.2 Run Trivy against the four local images, emit a warning and summary for critical findings, and retain the JSON report; verify clean results and scanner failures have distinct outcomes.

## 2. Delivery

- [x] 2.1 Add the required no-impact migration note and run the targeted migration and workflow validation checks.
- [x] 2.2 Push a dedicated branch, open a draft PR linked to the issue, and inspect the PR Docker matrix and migration checks on GitHub.

## 3. Selective pull request scanning

- [x] 3.1 Detect dependency, production Dockerfile, build recipe, and image CI changes in the reusable workflow; keep the image build matrix active for every pull request and skip Trivy for unrelated changes.
- [x] 3.2 Verify the path filter locally for representative positive and negative paths, then inspect the draft PR's GitHub jobs and scan reports after pushing.

## 4. Visible Trivy checks

- [x] 4.1 Add one report job per scanned image and verify the resolved matrix excludes `ws-bench` and release runs.
- [ ] 4.2 Verify on the draft PR that the four Trivy jobs appear separately, annotate findings as warnings, and stay successful when CVEs are present.
