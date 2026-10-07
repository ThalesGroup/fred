## 1. Chart contract and template

- [x] 1.1 Define optional per-application autoscaling values and validate fields, bounds, metrics and behavior in the chart JSON schema.
- [x] 1.2 Add an `autoscaling/v2` HPA template targeting the matching enabled application Deployment; fail rendering on an enabled HPA with a disabled Deployment.
- [x] 1.3 Exercise focused chart renders for disabled defaults, a configured HPA, correct application targeting, and invalid deployment state.

## 2. GCP worker configuration and documentation

- [x] 2.1 Add the supplied four Knowledge Flow worker HPA policies as disabled chart value examples and confirm CPU requests are inherited by each worker.
- [x] 2.2 Document the values shape, opt-in behavior, metrics-server prerequisite and Deployment replica ownership in the chart guide.
- [x] 2.3 Verify the four worker HPA values match the supplied policies and no unrelated application gets an HPA.

## 3. Review and verification

- [x] 3.1 Run the targeted Helm render/schema checks and review the full change against its target branch, including deployment consumers and documentation.

## Verification evidence

- `helm template fred deploy/charts/fred --namespace hpa-check` renders successfully with no HPA by default.
- A targeted `helm template` with autoscaling enabled renders an `autoscaling/v2` HPA for `control-plane-backend`; its Deployment omits `spec.replicas`.
- Enabling autoscaling while the Knowledge Flow worker Deployment is disabled fails rendering with an actionable error.
- Helm schema validation rejects an empty metrics list and a stabilization window of 3601 seconds.
- `git diff --check` passes.
- Independent read-only review covered the working-tree change against `origin/swift` at `044475267c9b84df7e8d142280a7cddf05de6324`. Findings on Deployment replica ownership, empty metrics, HPA bounds, and the delta spec scope were corrected. No chart-code findings remain.
- Automated test suites were not run; the focused checks above use Helm rendering directly.
