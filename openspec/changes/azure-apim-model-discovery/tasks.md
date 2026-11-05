# Tasks

## 1. Azure APIM source contract and routing

- [ ] 1.1 Add a typed Azure APIM discovery source with required non-secret settings and URL consistency validation; verify malformed or credential-shaped YAML is rejected by focused catalog tests.
- [ ] 1.2 Generate `azure-apim` profiles for eligible listed chat models, preserving wire IDs and filtering; verify the resulting profile can construct the existing provider and standard OpenAI sources remain unchanged.

## 2. Authenticated discovery and URL boundary

- [ ] 2.1 Use pod-local OAuth client secret and APIM subscription key in synchronous and asynchronous list requests and asynchronous detail requests; verify headers, missing-secret failure, redacted errors, and no request to unapproved origins with focused tests.
- [ ] 2.2 Reject Azure APIM URL overrides before token acquisition or network access, retain safe refresh at the configured URL, and mark the admin URL read-only; verify pod and UI behavior with focused tests.

## 3. Operator guidance and integration

- [ ] 3.1 Update the discovery operator guide with C2's tested list URL, existing credential variables, chat-model allowlist, rollout dependency, and rollback; verify the documented YAML parses and matches the source contract.
- [ ] 3.2 Run relevant model-discovery and routing tests, root `make code-quality`, and full branch review against `swift`; record any remaining draft limitations in the PR.

## Workflow follow-up

- Archive after the implementation is complete and reviewed. A release tag and C2 deployment require a separate later decision.
