# Tasks

## 1. Knowledge Flow model selection

- [x] 1.1 Add optional `reranker_model` to the typed Knowledge Flow configuration, validate provider/name/base URL/credential binding, regenerate the JSON schema, and verify config parsing for absent, valid and invalid entries with focused tests.
- [x] 1.2 Implement the shared remote indexed-results HTTP adapter with a pooled bounded client, timeouts, response validation and secret redaction; verify success, malformed results, timeout, oversized response and explicit failure with offline tests.
- [x] 1.3 Preserve the image CrossEncoder as the absent-configuration path, initialize it safely under concurrent first use and run prediction off the event loop; verify local fallback and concurrent initialization with focused tests.
- [x] 1.4 Add an operator example and credential setup to Knowledge Flow config documentation and deployment YAML comments; verify each shipped config parses against the regenerated schema.

## 2. Knowledge Flow search integration

- [x] 2.1 Add optional `rerank` to `/vector/search` with a false wire default, gather a capped wider candidate pool, apply existing visibility checks before model use, and preserve the attachment quota after ranking; verify mixed scopes, hidden hits, pool and result limits, empty hits and the disabled path with focused service tests.
- [x] 2.2 Route targeted similarity and the authenticated direct rerank endpoint through the shared selector without changing their wire shapes or authorization; verify local/remote routing, `rerank=false`, targeted restrictions, score filtering and direct endpoint permissions with focused tests.
- [x] 2.3 Preserve reranking latency and counters on success and failure, with bounded dimensions and no content or credentials in logs; verify emitted metrics and error status in focused tests.
- [x] 2.4 Update Knowledge Flow retrieval API and configuration documentation for the request flag, model selection, 503 failure and compatibility behavior; verify documented examples match the API schema.

## 3. Agent setting and search transport

- [x] 3.1 Add default-on `rerank` to `DocumentAccessConfig` and the advanced manifest field, update English and French labels, and bump the manifest version; verify new, omitted-field and explicit-off configurations with capability and settings tests.
- [x] 3.2 Carry the typed flag through `DocumentSearchPort`, the runtime adapter and `VectorSearchClient` to Knowledge Flow without adding an agent tool; verify the request payload and scope narrowing with focused SDK, adapter and capability tests.
- [x] 3.3 Update agent configuration documentation for the advanced switch and confirm the form displays and persists it in the existing advanced section.

## 4. Integration and readiness

- [x] 4.1 Run root `make code-quality`, the affected projects' offline test suites, and raw `basedpyright` wherever a touched package has a baseline; record the commands and results in the PR.
- [x] 4.2 Review the full Swift diff against `origin/swift`, including all API consumers, authorization, bounded work and deployment docs; obtain an independent read-only review for the contract change and resolve findings before draft PR readiness.
- [ ] 4.3 Reconcile this change's proposal, design, specs and tasks with the implemented behavior, sync the durable spec and validate the change; verify the draft PR targets `swift` and links issue #3536 and Weaver PR #3535.

## Workflow follow-up

- Archive the OpenSpec change after verification and review requirements are satisfied.
