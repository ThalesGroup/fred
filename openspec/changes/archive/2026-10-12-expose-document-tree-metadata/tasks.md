## 1. Confirm scope and tracking

- [x] 1.1 Confirm metadata and compact expandable tool detail scope. Developer approved the proposed fields and preview, then requested implementation on 2026-10-12. Artifacts now include the accepted UI and metadata.
- [x] 1.2 Created ThalesGroup/fred issue #3052 after explicit publication approval. Worktree branch `feat/document-tree-tool-details` is based on `origin/swift`; patch-note commits from the initial checkout are excluded.

## 2. Expose timestamp metadata

- [x] 2.1 Extend the authorized batched leaf projection and existing leaf representation with stored arrival, creation, and modification dates plus title, format/MIME, language, page/row counts, labels and source. Verify `test_corpus_tree_service.py` covers opposite arrival/creation order and excludes unauthorized or out-of-scope metadata. Inspect legacy deserialization defaults and verify missing arrival values cannot silently become the current read time.
- [x] 2.2 Render compact JSON leaf records with labeled ISO 8601 timestamps, timezone, available precision and null unknown dates. Verify `test_corpus_tree_builder.py` covers same-day arrivals, offset/naive timestamps, absent embedded dates, duplicate folder membership, and pruning within the existing character budget.
- [x] 2.3 Update the tool description for arrival chronology and add the explicit incomplete-listing notice when the result is truncated. Verify `test_capability.py` preserves metadata and the notice in both text content and text blocks, including a truncated fake result without an existing textual warning.

## 3. Compact tool detail

- [x] 3.1 Parse current JSON tree leaves and historical plain text trees without showing internal ids or malformed raw payloads. Verify focused parser tests cover nested folders, repeated documents, optional fields, offset timestamps, pruning notices and punctuation/newlines.
- [x] 3.2 Implement the approved folder/document view, unique displayed counts, localized timestamps, latest displayed arrival marker and one expanded document at a time. Add English/French translations and verify focused component tests cover expansion, missing metadata, historical dates and incomplete-listing warnings.

## 4. Review and close out

- [x] 4.1 Update the existing runtime contract document-access section and component UX doc, and add an English migration note with no operator action expected. Verify terminology matches the Resources arrival-date contract and request/response models remain unchanged; regenerate generated clients if schema changes become necessary.
- [x] 4.2 Run the focused Knowledge Flow and capability tests, then the root quality check once before commit/push. Apply the branch audit and performance review procedures and obtain an independent read-only review of the implemented contract. Record reviewed base/head, findings, dispositions, and verification in these tasks or the PR.
- [x] 4.3 Reconcile approved scope with the final implementation, sync and archive the completed OpenSpec change, and push/open a draft PR after publication authorization. Verify only this work is committed and the PR links its tracking issue.

## Review dispositions

- Independent review of base/head `7dafb6f6c6f39eb457bbccad157ec6bcd8201b97` and the implementation working tree found two P2 defects: valid brace/newline folder names rejected by the parser, and Graph runtime ToolInvocationResult envelopes not decoded. Both are corrected with JSON folder records, historical text compatibility, allowlisted Graph text-block extraction and focused regressions. Re-review confirmed both corrections.

- Re-review confirmed the two initial P2 fixes and identified pre-2026-08-06 historical folder markers `[tag-id]/` leaking ids. Both parsed and fallback historical paths now redact prefixed and unprefixed markers using the existing redaction utility; raw/Graph and multiline historical regressions cover this correction.

## Verification

- Knowledge Flow: `pytest tests/features/test_corpus_tree_builder.py tests/features/test_corpus_tree_service.py -q` - 26 passed. Includes the event-loop responsiveness regression; executed outside the network sandbox because its restrictions block asyncio threadpool wakeups/shutdown.
- Document access: `pytest tests/test_capability.py -q` - 50 passed.
- Frontend: focused `vitest run` for `documentTreeTrace.test.ts`, `traceUtils.test.ts` and `DocumentTreeDetail.test.tsx` - 183 passed.
- Root quality: `UV_NO_SYNC=1 make code-quality 'MAKE=make -o dev -o node_modules'` - all modules passed. Existing installed dependencies were reused; dependency setup was skipped, no quality checks were skipped. Untouched fred-runtime retains five baseline warnings; changed capability and Knowledge Flow report `0 errors, 0 warnings, 0 notes`.
- Chromium: actual renderer output inside the Graph envelope, keyboard Enter/Space, one expanded row, ids hidden, no runtime errors and no horizontal overflow at 320/720 px in light/dark themes. Temporary preview files/server were removed after verification.
- `make migration-check MIGRATION_BASE=origin/swift` and `openspec validate expose-document-tree-metadata --strict` passed. API/SDK response shapes are unchanged; no generated client regeneration required.
- Author and independent review covered all task source, tests, translations, specs and docs against `7dafb6f6c6f39eb457bbccad157ec6bcd8201b97`, including ReAct, both Graph tool consumers, HTTP adapter, metadata authorization/store and UI. Three P2 findings were corrected and independently rechecked; no new actionable finding in the final delta. Review excluded preview/dependency artifacts. No live LLM turn, full-repository test suite or concurrency/load campaign was run; threadpool/GIL behavior under high load is unmeasured.

- Specs synced and change archived after successful verification and review. Implementation commits pushed on `feat/document-tree-tool-details`; draft PR creation completed. Archive close-out committed separately without changing implementation code.
