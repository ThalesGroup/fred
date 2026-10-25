## 1. Coordination and admission

- [x] 1.1 Add one migration for restricted sandbox session, capacity and wait-ticket state; verify migration ancestry and database constraints.
- [x] 1.2 Add a broker coordinator interface and PostgreSQL implementation for session identity, global active/preparing caps, per-tenant bounded FIFO waiting and expiry; verify concurrent two-instance tests against PostgreSQL.
- [ ] 1.3 Route shared-profile requests and view creation through the coordinator without storing code; verify same-conversation serialization, capacity refusal and failed-database behavior.

## 2. Persistent lifecycle

- [x] 2.1 Add approved SIG workspace PVC configuration and strict admitted-pod validation for separate writable `/work` and bounded `/tmp`; verify template and backend tests.
- [x] 2.2 Implement SIG suspend, resume, revalidation and final workspace/view deletion while preserving the claim between active periods; verify files survive suspension and cannot cross conversations.
- [ ] 2.3 Reconcile stale preparation and broker restart without recover-all deletion; verify crash/restart tests and server-side expiry cleanup.

## 3. Deployment and pressure

- [x] 3.1 Wire shared-mode database Secret, replica count, queue/preparation limits and workspace StorageClass/quotas into the Fred chart; verify Helm rendering and rejection of unsafe combinations.
- [x] 3.2 Add sandbox node placement examples, RuntimeClass overhead and autoscaler guidance for both Kata and gVisor; verify operator commands and chart values.
- [ ] 3.3 Bound Kubernetes Job readiness polling and expose admission, lifecycle and API-pressure metrics; verify focused tests and metric output.

## 4. Verification and delivery

- [ ] 4.1 Run focused backend, chart and migration checks, then a full-mount k3d ramp with suspension and broker restart; record actual latency, resources, object counts and limits in the PR.
- [ ] 4.2 Audit the stacked diff against its parent, obtain independent security/concurrency review, reconcile OpenSpec artifacts, push a draft stacked PR and leave CI green.
