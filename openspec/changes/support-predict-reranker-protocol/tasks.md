## 1. Tracking and contract

- [x] 1.1 Find or create a tracking GitHub issue for the generic predict protocol adapter, use a dedicated topic branch, and verify the issue scope matches this change.
- [x] 1.2 Extend Knowledge Flow reranker configuration with the generic `predict` provider and safe model-name handling; verify valid configuration loads and unsupported providers or settings fail focused configuration tests.

## 2. Adapter and verification

- [x] 2.1 Add predict request and response handling to the shared reranker; verify focused tests assert model-derived API paths, `apikey` header, query/documents payload, positional score mapping, and reuse of the existing key fallback.
- [x] 2.2 Verify focused tests reject missing, extra, nonnumeric, boolean, and nonfinite predictions, HTTP errors, and timeouts without local fallback or credential disclosure.
- [x] 2.3 Verify existing `rerank` provider and local CrossEncoder tests still pass, plus a concurrent predict test that keeps request results and credentials isolated while using the existing shared client and batch limits.
- [x] 2.4 Update operator guidance for both remote providers and their credential headers, then verify the predict example matches the supplied OpenAPI contract and the configured validation schema.

## 3. Review and local activation

- [x] 3.1 Run the relevant focused tests and the required root quality check once, perform full branch review with independent read-only review, and record findings and dispositions in the issue or draft PR.
- [ ] 3.2 Obtain a Fred release containing the adapter and verify the published chart and image versions include it before selecting that version in local deployment values.
- [ ] 3.3 Set `reranker_model` for Knowledge Flow API and worker in both local PRISM int and prod values, use `https://api.corp.thales/corp/genai/reranker/v1` and existing `OPENAI_API_KEY`, and verify both YAML documents parse with the expected model fields and remain untracked and unstaged.
- [ ] 3.4 Verify an authenticated predict response and a reranked document search from integration, then check production using the same service URL; record results without logging document content or credentials. Leave each agent's reranking switch under its existing default-off control.
