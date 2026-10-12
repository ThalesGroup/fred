## 1. Presentation

- [x] 1.1 Default both sources to root text account attributes, with explicit advanced mode and cleared pending selections.
- [x] 1.2 Update English/French wording and regressions for default fields, metadata, search and advanced compatibility.

## 2. Delivery

- [x] 2.1 Verify a real-account browser journey, capture the simplified view and complete targeted tests, root quality and independent review.
- [x] 2.2 Update existing docs/specs and archive the verified change with the reviewed block. Final push, PR evidence, CI and mergeability are tracked in PR #2966 as the delivery gate.

Verification: all 15 editor regressions passed; root make code-quality passed across all modules. Real local-account Playwright received HTTP 200 from own-claims, displayed five root text fields and no nested summaries, toggled advanced mode with Enter, selected a technical field, confirmed return to simple mode disables confirmation, and exercised observed-root search. No requests were mocked and no policy/access state was saved. Published session values are masked; observed capture contains a generic searched key only.

Independent bounded review against 064c5b58d plus working changes covered the picker, editor consumer, Dialog/Button/TextInput composition, projection/catalog contracts, both locales and delta artifacts. No code defects found. Corrected the spec to require unsupported-value explanations in advanced mode. Tests/browser were author-run; other feature changes, production and independent browser execution are excluded. Existing full-PR review remains separate. The target has since advanced from c0745848 to ce4a30635; integration and final CI evidence will be recorded in the PR.
