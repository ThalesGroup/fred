## 1. Application resource and configuration

- [x] 1.1 Define the dedicated app resource, permission types and authorization relations; verify the compiled model matches its source and non-app definitions are unchanged.
- [x] 1.2 Map application catalog entries to exact typed app references in discovery, SDK checks and administration; verify mapping, invalid-identifier and no-legacy-fallback tests.
- [x] 1.3 Register enabled applications from configuration without creating permission tuples; verify catalog projection, registration seeding and configuration validation.

## 2. Entitlement controls and security

- [x] 2.1 Require membership-first admission and exclude personal spaces while preserving agent independence; verify admission, personal-grant refusal and agent-store tripwire tests.
- [x] 2.2 Use existing enable, disable, reset and default-on controls with typed app writes; verify write targets, catalog-hidden revocation and no agent side effects.
- [x] 2.3 Use higher-consistency app admission and typed administration caches with monotonic and partial-write invalidation; verify consistency, cache isolation and cache-race tests.
- [x] 2.4 Bound exact-reference cleanup and expose incomplete cleanup through the public package; verify batching, completion refusal, consistency and public-export tests.
- [x] 2.5 Keep touched authorization, factory and handler log emissions identifier-free; verify synthetic leakage tests and document independent logging sinks outside their coverage.
- [x] 2.6 Isolate offline tests from external services and user storage; verify test-owned storage and realistic authorization doubles in the offline suites.

## 3. Documentation and local verification

- [x] 3.1 Align the proposal, requirements, design, verification map, product contract, RFC and guides with the feature and its lifecycle limitations; verify exact test references, local links and strict OpenSpec validation.
- [x] 3.2 Run touched-project quality, import-order, raw typing, secret scanning and offline tests; record actual results and known coverage limits in the verification map.
- [x] 3.3 Independently review app authorization and supporting security protections; verify actionable scoped findings are resolved and remaining gaps are explicit.

## 4. Outstanding integration and rollout verification

- [ ] 4.1 Run the real authorization-engine integration cases for explicit grants, inherited default-on, deny precedence, cross-team isolation and management permissions; record results against the app-aware model.
- [ ] 4.2 Verify discovery and first-party SDK entitlement parity against the same live authorization state, including revocation and personal-space exclusion; record both outcomes for each fixture.
- [ ] 4.3 Verify the deployment cutover: schema/model compatibility, writer fencing and draining, absence of semantic legacy grants, app-aware model publication, reader/writer pins and the final legacy-state recheck; record rollout and state-preserving rollback evidence.

## Deferred work

Shared resource lifecycle design and implementation are outside this checklist.
See [the design gap](design.md#deferred-gap--shared-resource-lifecycle).
Global Deactivate/Activate/Delete requires a separate cross-resource change.

## Verification

The [verification map](verification.md#execution-evidence) records current
offline execution, mutation checks, independent review and operational limits.
Live integration and deployment readiness remain unverified until the outstanding
checks have execution evidence. Operational execution requires separate authorization.
