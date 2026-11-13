## 1. Verified model binding and exact counter

- [ ] 1.1 Add the official tokenizer dependency and pinned Small 4 / 2603 assets through existing model-profile resolution; verify alias resolution, asset checksum and unknown/mismatched model rejection without changing the execution model or performing per-call downloads.
- [ ] 1.2 Implement exact counting for fully captured parameter JSON and complete model-visible text, retaining model/tokenizer provenance; verify deterministic official-tokenizer fixtures, accents/escaping, true empty content and missing-raw-input cases without generic or character-based fallbacks.

## 2. Runtime, history and clients

- [ ] 2.1 Add optional typed per-tool usage to existing SDK/runtime events and JSON history, then regenerate frontend API types; verify backward-compatible JSON round trips and unchanged model usage/billing contracts.
- [ ] 2.2 Wire counting at the actual model/tool boundaries by session/exchange/call ID; verify complete results, actual error content, parallel calls with different payloads and unaffected redaction with focused integration tests.
- [ ] 2.3 Verify live SSE and reload from a second runtime/application instance retain identical per-call counts; ensure old rows without verified measurements remain unavailable and no automatic backfill or tool re-execution occurs.

## 3. Requested drawer and close-out

- [ ] 3.1 Add the two compact French/English badges and precise tooltips beside existing status/duration, with honest running/missing states; verify original SQL/JSON colors, every preview column, full-response counting/copying and absence of the rejected paragraph in renderer and browser checks.
- [ ] 3.2 Exercise large payloads and concurrent measurements with bounded workers, cancellation and measurement failure; record loop responsiveness, memory bounds and latency overhead, and obtain independent runtime/performance review before readiness.
- [ ] 3.3 Run affected tests, root make code-quality and migration/spec validation; reconcile runtime/UX/operator docs, record independent review and remaining limits in #3527/#3528, then sync/archive this change only after implementation and verification pass.
