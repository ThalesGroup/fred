## 1. Production dependency environment

- [x] 1.1 Reuse `make dev` from the production target, then run a locked runtime-only sync. Verify the final dependency set, pandoc shim, and dev stamp reset.
- [x] 1.2 Switch the three Python production Dockerfiles to the new target and verify their build commands use it.

## 2. OS package remediation

- [x] 2.1 Refresh final-stage OS packages in the three images and verify the apt commands are valid.
- [x] 2.2 Align both Knowledge Flow stages to Python 3.12.13 slim and verify their tags match.

## 3. Integration and delivery

- [x] 3.1 Add a migration note and verify deployment and rollback instructions are present.
- [x] 3.2 Run repository quality checks and verify the production dependency set and container builds. The targeted checks and all PR workflows passed; local root quality stopped on the existing uv bootstrap issue.
- [x] 3.3 Run the PR Trivy scanner, compare critical findings against the baseline JSON reports, and record residual risks in the draft PR.
