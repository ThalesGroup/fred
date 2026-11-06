## 1. Effective pod default

- [x] 1.1 Infer a chat default only from one manual chat profile without an explicit default; verify focused policy tests for one, zero, multiple, discovered, and explicit cases.
- [x] 1.2 Advertise that same effective default in `/agents/models-catalog`; verify focused projection tests and a one-manual-model Playwright admin view without the required-choice modal.

## 2. Documentation and delivery

- [x] 2.1 Update routing and operator documentation for the inferred default and unchanged database schema; verify the OpenSpec delta with `openspec validate --strict`.
- [ ] 2.2 Run root quality checks, review against `swift`, push the draft PR, and verify its CI is green.
