## 1. Shared rule contracts and persistence

- [x] 1.1 Retain typed bounded all/any predicates and remove admission configuration/seed contracts; verify invalid/empty rules and unsupported operators, with no admission-specific deployment settings.
- [x] 1.2 Extend the PR's single admission migration and shared models for policy/revision, name-only claim catalog and selected fact evidence; verify one Alembic head, PostgreSQL/SQLite upgrade/check/downgrade on isolated databases, and preservation of unrelated identity/avatar/CGU data.
- [x] 1.3 Initialize absent SQL authority with no rule, revision zero and filtering inactive; always initialize authenticated readers and verify saved state survives restart and unavailable/incompatible authority produces 503.

## 2. Verified claims and live evaluation

- [x] 2.1 Capture bounded internal verified human facts and observed path/type metadata, excluded from serialization/repr/logs; verify nested paths, catalog limits, token cache behavior, workload exclusion and absence of persisted unrelated values.
- [x] 2.2 Evaluate explicit literal/regex conditions and all/any semantics using the current shared policy; verify punctuation is literal, case handling, arrays, missing negative claims, oversized values and one bounded regex deadline.
- [x] 2.3 Adapt selected observations and direct/delegated admission to live policies; verify changing claim/operator with the same cached token affects the next request on another instance, while new delegated paths require fresh compatible human evidence.
- [x] 2.4 Preserve existing independent sources and T0/Free behavior under composed rules; verify manual/T0/team/Free grants, revocation, suspension and CGU acceptance with the affected admission tests.

## 3. Administrator API and editor

- [x] 3.1 Extend admin state and add claim catalog, policy preview and versioned save operations under platform-management permission; verify unauthorized access, stale revision 409, atomic actor lockout and side-effect-free preview including with filtering inactive.
- [x] 3.2 Regenerate the control-plane client and wire localized claim selection/manual paths, operator/operand/case controls and all/any editing using shared components; verify add/remove conditions and preservation of the existing exception/team/filter controls with focused UI tests.
- [x] 3.3 Add Test/Save feedback and conflict handling; verify per-condition missing/type/match results, effective actor admission, invalid regex errors, preserved drafts and accessible labels/keyboard operation in tests and an available browser.
- [x] 3.4 Add bounded atomic selected-user bulk grants and UI selection across search/pages; verify platform-only authority, all-or-nothing unknown-user rejection, source preservation and live team-member revocation across readers.

## 4. Shared support and deployment contracts

- [x] 4.1 Remove duplicate backend/public/Helm `supportLink` and the frontend override, retaining `contactSupportLink`; verify refusal, Free and profile destinations agree before protected bootstrap, with no backend requirement for a support URL.
- [x] 4.2 Remove YAML/Helm/SDK admission settings, regenerate schemas and update shared reader consumers; verify no admission block is needed and Keycloak/local administration and activation retain suspension and legacy-gate safeguards.
- [x] 4.3 Update the existing operator guide, product/runtime/identity/security/UX contracts and tracking issue/PR to the final behavior; verify guidance covers draft schema recreation, rollout, persistence, missing delegated evidence and operator recovery without deployment-specific names or values.

## 5. Verification and close-out

- [x] 5.1 Exercise the integrated administrator/edit/deny/Free journeys with separate local identities and shared PostgreSQL; record observed behavior, cross-instance cached-token revocation and any unavailable browser/IdP/load environments in existing tasks/PR evidence.
- [x] 5.2 Run the root quality gate once the implementation batch is complete and audit the full branch against its actual `swift` base; obtain independent read-only authorization/frontend/performance review, disposition findings and verify corrective deltas.
- [x] 5.3 Reconcile and validate the OpenSpec artifacts, sync the changed capability and archive this completed follow-up; verify durable specs/contracts agree and push reviewable commits to the existing standalone draft PR.


## Verification and review evidence

- Core security: 608 tests passed, covering verified facts/cache isolation, workload exclusion, bounded predicates, policy changes, monotonic delegated evidence, metadata-only discovery, config-free readers and SDK initialization.
- Final control-plane selection: 88 tests passed with an isolated PostgreSQL fixture, including concurrent policy saves/T0, timeout recovery, bounded bulk grants, provenance, startup and registry safeguards. SQLite reflection emits three existing warnings. The actual membership-service selection passed 56 tests (8 PostgreSQL tests skipped in that separate run); both administrator removal and self-leave clear all five roles and deny the same direct/delegated subject through another reader. Registry correction: 36 passed.
- Frontend editor/support/OIDC/application/PDF selection: 63 passed. Independent corrective replay: four files, 43 passed, including bulk cap/retention, membership cache invalidation, initial/retry application denials and later PDF failures. Resource-specific errors and unavailable authority are not converted into admission denial.
- The root `make code-quality` passed across all modules. Five pre-existing runtime unreachable-code warnings remain. Regenerated chart schema matches its generator; Helm rendering and the migration-guide guard passed. The control-plane client was regenerated from the test application configuration rather than manually edited.
- The single migration remains `f9a2c7d81e40` on `aac66348e27b`. Earlier isolated PostgreSQL and temporary SQLite upgrade/check/downgrade verification preserved unrelated identity/avatar/CGU/storage fields; no further schema change followed. Local browser verification used the existing migrated developer database and temporary admission records, then restored filtering inactive, empty exceptions and team flags.
- Real Playwright journeys used existing accounts and actual Keycloak, OpenFGA and PostgreSQL, with no intercepted or mocked requests: persisted policy after API restart without admission YAML, AND/OR preview, matching-user admission, rejection, Free enrollment, removing Free, removing a Free member while Free remains enabled, whole-team authorization and removal, selected-user bulk grants and removal, explicit T0 completion. Screenshots under `docs/swift/ux/images/platform-access/` exclude credentials, capability URLs and the administrator identity; selection email text is masked at capture. Temporary support branding was restored.
- Independent authorization/frontend/performance reviews covered the earlier full branch and current responsibility changes. Current corrective review used `origin/swift` at `c0745848`, `fee57b6ed` plus the implementation tree now committed as `b4394aa99` and `afc32b160`. Findings corrected and replayed: higher-consistency administrator/deletion authority, last-source team-deletion preflight, actual full-membership revocation coverage, missing application/PDF refusal paths and membership cache invalidation. Earlier dispositions include stale evidence writes, own-human preview, object diagnostics, draft races/feedback, raw transport denials, team IDs, bounded SQL I/O and T0 lock/population bounds.
- Private IdP/Helm overlays, four-replica production load and production ingress capability masking remain operator verification. An active reusable Free link permits explicit re-enrollment after removal under the accepted link contract; removing membership itself revokes access immediately and never creates a permanent individual grant.

Full independent branch audit covered actual target `c074584822f3d1e785c54c253e642b34e86da164`, head `afc32b160afc0926e303704fc7f252224f0b5437`, merge base `c8e58a39ea5d3f5163847d5de3bdf45a1190a1e3` and all working implementation/docs/screenshots, including the late existing timeout setting. No new findings; strict membership BatchCheck and MCP corrections remain resolved. Independent exclusions: live browser replay, load campaigns, external SDK consumers and production deployment. The author reviewed the same full responsibility set and supplied the actual browser/test/quality evidence above. The current base's unrelated dead-enum retirement has not been merged; no admission consumer regression was found from that divergence.
