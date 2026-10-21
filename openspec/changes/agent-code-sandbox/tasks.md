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
- [ ] 3.2 Run targeted tests and root quality gate, review the full branch against `origin/swift`, obtain independent read-only review, and record any remaining production gaps.
