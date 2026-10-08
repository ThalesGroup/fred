## 1. Chart contract and template

- [x] 1.1 Define optional per-application autoscaling values and validate fields, bounds, metrics and behavior in the chart JSON schema.
- [x] 1.2 Add an `autoscaling/v2` HPA template targeting the matching enabled application Deployment; fail rendering on an enabled HPA with a disabled Deployment.
- [x] 1.3 Exercise focused chart renders for disabled defaults, a configured HPA, correct application targeting, and invalid deployment state.

## 2. Deployment policy examples and documentation

- [x] 2.1 Add disabled CPU HPA policy examples for every chart-managed Deployment, preserve the supplied four Knowledge Flow worker policies, and document the CPU requests prerequisite.
- [x] 2.2 Document the values shape, opt-in behavior, metrics-server prerequisite, CPU request requirement and Deployment replica ownership in the chart guide.
- [x] 2.3 Verify all Deployment policy examples and ensure no application gets an HPA by default.

## 3. Review and verification

- [x] 3.1 Run the targeted Helm render/schema checks and review the full change against its target branch, including deployment consumers and documentation.

## Verification evidence

- `helm template fred deploy/charts/fred --namespace hpa-check` renders successfully with no HPA by default.
- A targeted `helm template` with autoscaling enabled renders an `autoscaling/v2` HPA for `control-plane-backend`; its Deployment omits `spec.replicas`.
- Enabling autoscaling while the Knowledge Flow worker Deployment is disabled fails rendering with an actionable error.
- Helm schema validation rejects an empty metrics list and a stabilization window of 3601 seconds.
- The default render succeeds with nine per-Deployment policy examples and no HPA resources; enabling the frontend renders an HPA for that Deployment.
- Enabling Fred Agents autoscaling with the default local filesystem is rejected because the configured HPA maximum exceeds one replica.
- `git diff --check` passes.
- Independent read-only review covered the cumulative chart change against `origin/swift` at `044475267c9b84df7e8d142280a7cddf05de6324`, including the committed HPA implementation and the expanded working-tree diff. It found no actionable issues across all nine Deployment examples, worker policies, templates, schema, documentation, or OpenSpec. The `fred-agents` storage guard includes enabled HPA maxReplicas.
- Automated test suites were not run; the focused checks above use Helm rendering directly.
