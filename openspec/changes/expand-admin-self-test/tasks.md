Frontend paths are under `apps/frontend/src/rework/`.

## 1. Families

- [x] 1.1 Generic run hook that returns a promise, family registry, one generic section, Run all and the combined report.
- [x] 1.2 Split `selfTestScenario` into the knowledge, agents and prompts families and delete it.

## 2. Checks

- [x] 2.1 Platform: service health, account status, issuer, clocks, runtimes, harness agent, models, capability and settings reads.
- [x] 2.2 Authorization: unauthenticated sweep, admin-route sweep and foreign-team sweep.
- [x] 2.3 Knowledge: search policies, document formats, tabular query, library link and unlink, retrievability, document tree, deletion without residue, corpus audit.
- [x] 2.4 Agents: tuning update, disable and enable, copy targets, duplicate and name conflict, concurrent turns.
- [x] 2.5 Prompts: prompt update, categories, favorites, commands, marketplace, deletion.
- [x] 2.6 Conversations: listing, rename, persistence, attachments, bulk deletion.
- [x] 2.7 Teams: charter gate, creation, roles, team resources, wiki, join link, routing, copy to the personal space, role revocation, deletion without residue.
- [x] 2.8 Security and observability: response headers, uploaded HTML served safely, KPI presets, search and metrics backends.

## 3. Close-out

- [x] 3.1 Unit tests per family with fake deps; `make code-quality` and `make test` in `apps/frontend`.
- [x] 3.2 Migration note, testing guide and verification evidence.

## 4. Live-run follow-ups

- [x] 4.1 Skip the unlink assertion when linking was not proven.
- [x] 4.2 Skip the retrievable-on assertion when retrievable-off failed.
- [x] 4.3 Check for searchable chunks after deletion and state the exact guarantee of the audit.
- [x] 4.4 Record the pgvector run and the remaining backend defects in verification evidence.
- [x] 4.5 Reject authentication and server errors as authorization or deletion proof; verify the authorization probe's temporary prompt is gone and cover these cases with fake-backed tests.

## 5. Second-account isolation

- [x] 5.1 Keep Keycloak account/password login and add a temporary access-token input for OIDC deployments.
- [x] 5.2 Validate both identities through bootstrap, reject the same user, and check personal team, prompt, session and agent routes in both directions.
- [x] 5.3 Cover provider-specific UI, identity failures, token handling and cross-account responses with local tests; record exact verification.

## 6. Authorization presentation

- [x] 6.1 Put authorization last in the page, Run all and combined report.
- [x] 6.2 Explain the family's purpose and the separate second-account and session-expiry checks in a visible notice, with French and English copy.

## 7. Deeper two-account isolation

- [x] 7.1 Check personal-team discovery and additional personal catalog routes in both directions.
- [x] 7.2 Check exact prompt access with one temporary prompt per account and verified cleanup after failures.
- [x] 7.3 Add fake-backed positive and negative cases, then record exact local evidence and remaining live limits.

## 8. Expected user roles (manual inputs superseded by section 10)

- [x] 8.1 Correct delegated platform-role gates in the existing authorization probe.
- [x] 8.2 Add optional expected direct platform roles and multiple team-role expectations to both credential entry paths.
- [x] 8.3 Compare direct/effective roles, team permissions and real route access without changing grants or shared settings.
- [x] 8.4 Cover role combinations, unexpected access and denial, credential failures and cleanup with fakes; record Entra ID manual validation separately from new checks.

## 9. Automatic two-account campaign

- [x] 9.1 Add preflight, role snapshot, exclusive execution and token-free interrupted-run recovery.
- [x] 9.2 Exercise six platform profiles and six team profiles per visibility; keep the complete successful campaign to 149 checks including transport and recovery (150 with interruption).
- [x] 9.3 Verify actual access, reciprocal isolation, revocation, independent roster and cleanup/restoration after failures.
- [x] 9.4 Add separate confirmed UI for both credential modes and recovery; document effects and limits.
- [ ] 9.5 Add fake-backed regression tests, run quality gates and obtain independent review. Frontend gates and reviews passed; root quality remains blocked by missing `uv` (see verification.md).
- [x] 9.6 Validate the focused campaign on a running deployment: developer report 146 passed, 3 failed, 149 steps; one public-team session guard defect reproduced separately (see verification.md).

## 10. One authorization campaign

- [x] 10.1 Remove the observation-only second-account action and manual role/team expectation inputs.
- [x] 10.2 Move missing personal catalog, discovery, exact prompt, cross-team content and platform-route probes into the automatic campaign; at most 150 actual checks including recovery.
- [x] 10.3 Cover denied, leaked and error responses and the full budget with fakes; reconcile docs and obtain review.
