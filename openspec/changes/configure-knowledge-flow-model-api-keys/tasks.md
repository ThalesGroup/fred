## 1. Tracking and shared factory

- [x] 1.1 Search GitHub for an existing tracking issue and relevant open Epic, create or link the issue if needed, and start a dedicated topic branch; verify the issue and branch identify only this Knowledge Flow change.
- [x] 1.2 Add optional explicit OpenAI API key injection to the shared chat and embedding factory paths while preserving legacy callers; verify focused offline factory tests cover explicit-key use without `OPENAI_API_KEY`, legacy fallback, and unchanged non-OpenAI providers.

## 2. Knowledge Flow credential selection

- [x] 2.1 Add one Knowledge Flow resolver for the four role-specific variables and `OPENAI_API_KEY` fallback; verify focused tests cover nonblank dedicated keys, absent and blank dedicated keys, and the no-key error without exposing values.
- [x] 2.2 Wire chat, both vision construction paths, and embedding model construction plus embedding startup validation to that resolver; verify focused tests show each role uses its own key, a dedicated embedding key permits startup without `OPENAI_API_KEY`, and concurrent model construction leaves `os.environ` unchanged.
- [x] 2.3 Wire remote OCR to `KNOWLEDGE_FLOW_OCR_API_KEY` with the same fallback; verify the offline OCR tests inspect its outgoing authorization header for dedicated and fallback keys and reject the no-key case before any request.

## 3. Deployment and documentation

- [x] 3.1 Add optional Knowledge Flow `dotenv` entries and operator documentation for all four variables and fallback; verify a rendered chart shows the API and extraction workers using the same Secret, and examples contain no real key values.

## 4. Integration and close-out

- [ ] 4.1 Run the affected offline test suites and one root `make code-quality` near completion; verify all required checks pass and document any unrelated baseline failures.
- [ ] 4.2 Review the complete diff against its actual target branch, obtain an independent read-only review and the required performance review for the shared model factory path, then resolve findings; verify the review record names the reviewed base and head, coverage, findings, and dispositions.
- [ ] 4.3 Reconcile this change's proposal, design, tasks, and delta spec with the implementation, then sync and archive the change after acceptance; verify the current capability spec contains the shipped behavior and the tracking issue or PR records the result.
