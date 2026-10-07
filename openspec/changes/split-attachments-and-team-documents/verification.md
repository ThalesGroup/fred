## Verified behavior

Covered by automated tests, against the scenarios in `specs/document-access-sources` and `specs/agent-capability-packs`:

- Config: the three legacy shapes, an absent `show_attach_files_control`, string booleans (`"false"` stays false), new keys winning over leftover legacy keys, both-off rejected, no legacy key in `model_dump` (`fred-capability-document-access/tests/test_capability.py`).
- Manifest: sources first in a `sources` group, `visible_when="team_documents"` on the scope fields, no legacy key.
- Chat controls: paperclip only with attachments; no scope picker and no bound libraries without team documents; `rag_scope` drops `corpus_only` and an impossible default falls back to `hybrid`.
- Tools: `include_attachments` / `include_team_documents` passed to the port; `list_document_tree` only with team documents.
- Adapter: every ceiling combination crossed with `hybrid`, `corpus_only` and `general_only`, asserting the flags sent to Knowledge Flow, or no call (`fred-runtime/tests/test_document_search_source_ceilings.py`); the `attachments_only` alias narrows to attachments, never re-enables attachments turned off (`test_document_search_port_1906.py`), and warns once.
- Simple packs: each pack alone, both, turning off one, turning off the last (document access deselected, both sources reset, library scope kept), unavailable members, shared capability cleared, Advanced clear, legacy attachments-only agent read (`toolPackLogic.test.ts`); two cards and no retired card or switch (`SimpleCapabilitiesView.test.tsx`).
- Form: legacy keys normalized on load (`AgentFormModal.test.ts`), turning off the last source in Advanced deselects document access and resets both sources (`applyDocumentAccessConfigChange`), hidden gate hides its dependants (`CapabilityCard.test.tsx`).
- Composer: `RagScopeControl` renders only `params.options`; a remembered scope no longer offered falls back to the control default.

## Test evidence

| Suite | Result |
| --- | --- |
| `fred-capability-document-access` `make code-quality` / `make test` | pass / 59 passed |
| `fred-capability-documents` `make code-quality` / `make test` | pass / 75 passed |
| `fred-sdk` `make code-quality` / `make test` | pass / 565 passed, 3 skipped |
| `fred-runtime` `make code-quality` / `make test` (re-run after review fixes) | pass / 1822 passed, 11 skipped, 21 deselected |
| `fred-agents` `make code-quality` / `make test` | pass / 120 passed, 6 xfailed |
| Frontend `npx tsc --noEmit -p .` | pass |
| Frontend `npx prettier --check` + `npx eslint` (touched files) | pass |
| Frontend focused `npx vitest run` (TeamAgentsPage, ManagedChatPage, features/capabilities) | 50 files, 508 passed |
| Frontend full `npx vitest run` | 293 files passed, 1 skipped; 3373 passed, 7 skipped |
| `make migration-check MIGRATION_BASE=origin/swift` | 1 new declaration valid |
| `openspec validate split-attachments-and-team-documents --strict` | pass |
| Generated clients unchanged (task 2.4) | `make generate-openapi` in fred-runtime and control-plane-backend: no diff in either `openapi.json` |

Root `make code-quality` and frontend make targets were not run: they wipe the running Vite dev server's cache. The per-module and npx runs above cover the same checks.

## Manual checks

Pending (task 6.3), for the developer on a local stack.

## Review and limitations

- Performance review (task 6.2, `fred-performance-reviewer`): no finding. The search path still makes at most one awaited Knowledge Flow call per tool call, now skipped entirely when no scope remains; the tool stays wrapped by the existing tool observability middleware; no new metric, client or blocking call. The once-per-process warning flag is pod-local by design and has no await between check and set.
- Advanced both-off: first implemented as a Save block, then replaced after developer review by deselecting document access (`applyDocumentAccessConfigChange` in `toolPackLogic.ts`, called from `AgentFormModal.handleCapabilityConfigChange`). Checks: `npx tsc --noEmit -p .` clean; `npx vitest run src/rework/components/pages/TeamAgentsPage` 12 files, 92 tests passed.
- Review fixes (after author/independent review): alias narrowing, manifest version 0.2.0 (control-plane chat-controls cache key), strict legacy bool parsing, Simple last-pack reset, pack card a11y (missing flag as description, expand button named per pack with `aria-controls`). Checks: document-access `make code-quality` + `make test` 59 passed; fred-sdk `make code-quality` + `make test` 565 passed, 3 skipped; fred-runtime `test_document_search_source_ceilings.py` 10 passed; frontend `npx tsc`, `npx eslint`, `npx prettier`, `npx vitest run` (TeamAgentsPage, shared/organisms) 39 files, 334 passed.
- Reviewer decision 3: raising the capability's `fred-sdk` floor to the release that ships the new port keywords (the migration note states the runtime requirement meanwhile).
- Test fakes of `DocumentSearchPort` still declare `attachments_only`, because basedpyright rejects an override that drops a parameter.
- Not covered by automated tests: the rendered pack cards, the library options under the Team documents card, the Advanced error message placement and the Help Center copy.
