## 1. Fred contract and tool

- [x] 1.1 Add typed sandbox request/result/error and optional `RuntimeServices` port; verify SDK type and unit checks.
- [x] 1.2 Add the admin-gated `code_sandbox` capability, register it in `fred-agents`, and verify boot validation and tool behavior with a fake port.
- [x] 1.3 Bind an HTTP sandbox adapter from agent runtime configuration without exposing broker settings in the tool signature; verify a focused adapter test.

## 2. Isolated broker

- [x] 2.1 Implement broker configuration, authenticated API, bounded admission, warm pool with single-use leases, source/output limits, and backend protocol; verify API, pool, and capacity tests.
- [x] 2.2 Implement Docker backend with explicit Kata/gVisor runtime verification, disabled network, hard resource limits, deadline, and forced cleanup; verify command construction and failure paths with a fake runner.
- [x] 2.3 Implement Kubernetes Job backend with RuntimeClass preflight, dedicated namespace policy check, hardened pod template, deadline, result collection, and cleanup; verify manifests and lifecycle paths with a fake runner.

## 3. Operations and review

- [x] 3.1 Add Docker and Kubernetes deployment examples, runtime/CNI preflight, and a ready-path latency benchmark; verify manifests parse and the benchmark script validates.
- [x] 3.2 Run targeted tests and root quality gate, review the full branch against `origin/swift`, obtain independent read-only review, and record any remaining production gaps.

## 4. SIG Agent Sandbox integration

- [x] 4.1 Add a selectable SandboxClaim backend with template, pool and isolation preflight, single-use claim lifecycle, expiry and cleanup tests.
- [x] 4.2 Add operator manifests and document upstream controller installation, pool sizing, and admission limitations.
- [ ] 4.3 Measure cold and ready request-to-result latency in the same k3d environment as the Job backend, review the diff, run the quality gate, and leave PR checks green.

## 5. Conversation retention and admin controls

- [x] 5.1 Bind calls to a private conversation identity and retain one workload for repeated Bash/Python executions; serialize same-conversation calls and expire after 20 minutes idle.
- [x] 5.2 Add SIG claim expiry renewal and bounded cleanup for Docker/Job workloads; verify no workload is shared across conversations or users.
- [x] 5.3 Persist idle, active-capacity and warm-capacity settings behind platform-admin authorization; apply changes in the broker without redeploy, constrained by operator limits.
- [x] 5.4 Add an admin surface showing the approved isolation profile and these three controls; verify the API and UI with focused tests and captures.
- [ ] 5.5 Re-run targeted tests, root quality gate, full branch review and CI; document deployment limits and observed session behavior.
