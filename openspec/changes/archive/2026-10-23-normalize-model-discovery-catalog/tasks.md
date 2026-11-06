## 1. Catalog contract

- [x] 1.1 Replace the two discovery YAML forms with one optional nonempty list and verify one-source, multi-source, invalid, and static catalog tests.
- [x] 1.2 Keep the manual `default_profile_by_capability` mapping and remove discovery-local default selection; verify routing and disappearance fallback tests.
- [x] 1.3 Project safe effective chat model bindings into the admin inventory and add selector/advanced-form coverage.

## 2. Rollout and review

- [x] 2.1 Update the sample catalog, Helm values, and operator documentation; verify the sample and static Helm catalogs parse.
- [x] 2.2 Capture the grouped selector, advanced form, and recurring no-default modal in Playwright using the real React UI.
- [x] 2.3 Run root quality checks, review the branch against `swift`, and confirm the draft PR CI passes.
