## 1. Shared rule contracts and persistence

- [ ] 1.1 Add typed bounded all/any predicates and optional legacy seed conversion; verify invalid/partial configuration, empty rules, unsupported operators and case-sensitive legacy conversion with targeted security tests.
- [ ] 1.2 Extend the PR's single admission migration and shared models for policy/revision, name-only claim catalog and selected fact evidence; verify one Alembic head, PostgreSQL/SQLite upgrade/check/downgrade on isolated databases, and preservation of unrelated identity/avatar/CGU data.
- [ ] 1.3 Initialize the shared policy only once and make readers load authoritative state; verify seed changes/restarts cannot overwrite saved rules and unavailable or incompatible authority produces 503.

## 2. Verified claims and live evaluation

- [ ] 2.1 Capture bounded internal verified human facts and observed path/type metadata, excluded from serialization/repr/logs; verify nested paths, catalog limits, token cache behavior, workload exclusion and absence of persisted unrelated values.
- [ ] 2.2 Evaluate explicit literal/regex conditions and all/any semantics using the current shared policy; verify punctuation is literal, case handling, arrays, missing negative claims, oversized values and one bounded regex deadline.
- [ ] 2.3 Adapt selected observations and direct/delegated admission to live policies; verify changing claim/operator with the same cached token affects the next request on another instance, while new delegated paths require fresh compatible human evidence.
- [ ] 2.4 Preserve existing independent sources and T0/Free behavior under composed rules; verify manual/T0/team/Free grants, revocation, suspension and CGU acceptance with the affected admission tests.

## 3. Administrator API and editor

- [ ] 3.1 Extend admin state and add claim catalog, policy preview and versioned save operations under platform-management permission; verify unauthorized access, stale revision 409, atomic actor lockout and side-effect-free preview including with filtering inactive.
- [ ] 3.2 Regenerate the control-plane client and wire localized claim selection/manual paths, operator/operand/case controls and all/any editing using shared components; verify add/remove conditions and preservation of the existing exception/team/filter controls with focused UI tests.
- [ ] 3.3 Add Test/Save feedback and conflict handling; verify per-condition missing/type/match results, effective actor admission, invalid regex errors, preserved drafts and accessible labels/keyboard operation in tests and an available browser.

## 4. Shared support and deployment contracts

- [ ] 4.1 Remove duplicate backend/public/Helm `supportLink` and the frontend override, retaining `contactSupportLink`; verify refusal, Free and profile destinations agree before protected bootstrap, with no backend requirement for a support URL.
- [ ] 4.2 Update YAML/Helm/SDK configuration and regenerate schemas; verify enabled mode without a seed, optional legacy seeding, default-disabled mode, rendered policy consistency and removal of stale generated fields.
- [ ] 4.3 Update the existing operator guide, product/runtime/identity/security/UX contracts and tracking issue/PR to the final behavior; verify guidance covers draft schema recreation, rollout, persistence, missing delegated evidence and operator recovery without deployment-specific names or values.

## 5. Verification and close-out

- [ ] 5.1 Exercise the integrated administrator/edit/deny/Free journeys with separate local identities and shared PostgreSQL; record observed behavior, cross-instance cached-token revocation and any unavailable browser/IdP/load environments in existing tasks/PR evidence.
- [ ] 5.2 Run the root quality gate once the implementation batch is complete and audit the full branch against its actual `swift` base; obtain independent read-only authorization/frontend/performance review, disposition findings and verify corrective deltas.
- [ ] 5.3 Reconcile and validate the OpenSpec artifacts, sync the changed capability and archive this completed follow-up; verify durable specs/contracts agree and push reviewable commits to the existing standalone draft PR.
