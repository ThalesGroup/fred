# Tasks

## 1. Azure APIM source contract and routing

- [x] 1.1 Add a typed Azure APIM discovery source with required non-secret settings and URL consistency validation; verify malformed or credential-shaped YAML is rejected by focused catalog tests.
- [x] 1.2 Generate `azure-apim` profiles for eligible listed chat models, preserving wire IDs and filtering; verify the resulting profile can construct the existing provider, inherit matching manual model options, and leave standard OpenAI sources unchanged.

## 2. Authenticated discovery and URL boundary

- [x] 2.1 Use pod-local OAuth client secret and APIM subscription key in synchronous and asynchronous list requests and asynchronous detail requests; verify headers, missing-secret failure, redacted errors, and no request to unapproved origins with focused tests.
- [x] 2.2 Allow Azure APIM URL overrides within the configured origin and product path, reject other URLs before token acquisition or network access, and retain the existing admin edit/refresh flow; verify both outcomes with focused tests.

## 3. Operator guidance and integration

- [x] 3.1 Add an operator migration note with C2's tested list URL, existing credential variables, chat-model allowlist, rollout dependency, and rollback; verify the note with the migration checker and the staged C2 YAML separately.
- [x] 3.2 Run relevant model-discovery and routing tests, root `make code-quality`, and full branch review against `swift`; record any remaining draft limitations in the PR.

## Workflow follow-up

- Archive after the implementation is complete and reviewed. A release tag and C2 deployment require a separate later decision.
