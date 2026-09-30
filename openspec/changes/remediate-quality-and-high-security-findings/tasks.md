## 1. Establish the Finding Inventory

- [x] 1.1 Export current GitHub Code Quality Standard findings with number, rule, category, severity, location, and state; verify the baseline reproduces 1 reliability error, 7 reliability notes, and 153 maintainability notes.
- [ ] 1.2 Obtain the complete GitLab High report, reconcile every entry with the screenshots and a code or package location, and verify the inventory has a disposition slot for every High finding.

## 2. Protect Runtime Execution URLs

- [x] 2.1 Validate canonical root-relative `ingress_prefix` values in control-plane configuration and test accepted and rejected forms, including network-path, traversal, encoded separators, query, and fragment cases.
- [ ] 2.2 Regenerate control-plane and chart configuration schemas, update the runtime configuration migration note, and verify the generated schemas and documented examples agree with the validator.
- [x] 2.3 Add a shared frontend preparation-URL guard at all bearer-authenticated runtime fetch sites, update contract fixtures, and run the focused pipeline and chat SSE tests with malicious URL cases.

## 3. Secure Tabular SQL

- [ ] 3.1 Extend DuckDB AST validation to reject unsupported functions and expressions, including configuration and credential inspection, and verify focused validator tests cover nesting, CTEs, aliases, and bypass attempts.
- [ ] 3.2 Restrict each agent-query DuckDB connection to exact selected Parquet paths while retaining local and signed-URL reads; verify authorized views work and unrelated file or network sources fail.
- [ ] 3.3 Exercise the reported generated SQL sites in tabular processing, service, and migration code with quoted identifiers and hostile input values; fix any unsafe construction and run the targeted tests.
- [ ] 3.4 Run tabular service tests for authorized analytics, multi-dataset joins, error redaction, capacity, timeout, and cancellation; verify the security restrictions preserve the supported behavior.

## 4. Resolve High Findings

- [ ] 4.1 Verify the resolved frontend package identity for the `canvas` CVE against package metadata and the complete lock graph; update a genuinely vulnerable dependency or record evidence for false-positive triage.
- [ ] 4.2 Trace every frontend SSRF finding from input to browser request, fix any bearer or origin exposure beyond the runtime URL path, and verify affected focused tests and written dispositions.
- [ ] 4.3 Trace every tabular SQL and migration finding from input to execution, fix any remaining unsafe path, and verify focused regression tests and written dispositions.
- [ ] 4.4 Reconcile the full GitLab High inventory with fixed commits or justified scanner triage and verify no High finding lacks a disposition in the PR.

## 5. Improve GitHub Code Quality

- [ ] 5.1 Resolve the reliability error and seven notes, preserving intentional lifecycle and cancellation behavior; verify affected focused tests and finding-specific triage evidence.
- [ ] 5.2 Review maintainability findings for ineffectual statements and unused imports, fix actionable code without removing awaited work or registration side effects, and verify affected focused checks and per-finding dispositions.
- [ ] 5.3 Review maintainability findings for unused globals, duplicate imports, unnecessary lambdas, and unused locals, preserve migration and registration contracts, and verify affected focused checks and per-finding dispositions.
- [ ] 5.4 Triage remaining intentional Code Quality findings in GitHub with specific reasons, then verify no unreviewed Standard finding remains in the inventory.

## 6. Integrate and Verify

- [ ] 6.1 Run the affected targeted suites, then `make code-quality` once from the repository root, and record results and any environment limitations in the PR.
- [ ] 6.2 Reconcile these specs and tasks with implementation, validate and sync/archive the OpenSpec change, and verify the final artifact status.
- [ ] 6.3 Push the dedicated branch and open one draft PR linked to #2871; verify its title, finding inventory, before/after counts, and migration notes.
- [ ] 6.4 After the default-branch scans, verify the reliability and maintainability ratings and all GitLab High dispositions, then record any external scanner blocker in the same issue and PR.
