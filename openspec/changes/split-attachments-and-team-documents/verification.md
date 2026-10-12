## Verified behavior

Covered by automated tests, against the scenarios in `specs/document-access-sources` and `specs/agent-capability-packs`:

- Config: the three legacy shapes, an absent `show_attach_files_control`, string booleans (`"false"` stays false), new keys winning over leftover legacy keys, both-off rejected, no legacy key in `model_dump` (`fred-capability-document-access/tests/test_capability.py`).
- Manifest: sources first in a `sources` group, `visible_when="team_documents"` on the scope fields, no legacy key.
- Chat controls: paperclip only with attachments; no scope picker and no bound libraries without team documents; `rag_scope` offers all modes with either source, preserving a document-only default.
- Tools: `include_attachments` / `include_team_documents` passed to the port; `list_document_tree` only with team documents.
- Adapter: every ceiling combination crossed with `hybrid`, `corpus_only` and `general_only`, asserting the flags sent to Knowledge Flow, or no call (`fred-runtime/tests/test_document_search_source_ceilings.py`); the removed `attachments_only` keyword is rejected; document-only mode includes attachments and respects source ceilings and explicit turn scope.
- Simple packs: each pack alone, both, turning off one, turning off the last (document access deselected, both sources reset, library scope kept), unavailable members, shared capability cleared, Advanced clear, legacy attachments-only agent read (`toolPackLogic.test.ts`); two cards and no retired card or switch (`SimpleCapabilitiesView.test.tsx`).
- Form: legacy keys normalized on load (`AgentFormModal.test.ts`), turning off the last source in Advanced deselects document access and resets both sources (`applyDocumentAccessConfigChange`), hidden gate hides its dependants (`CapabilityCard.test.tsx`).
- Composer: `RagScopeControl` renders only `params.options`; a remembered scope no longer offered falls back to the control default.

## Initial implementation test evidence (before reviewer decisions)

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

- Performance review (task 6.2, `fred-performance-reviewer`): no finding. The search path still makes at most one awaited Knowledge Flow call per tool call, now skipped entirely when no scope remains; the tool stays wrapped by the existing tool observability middleware; no new metric, client or blocking call. The warning flag was subsequently deleted by the reviewer decision.
- Advanced both-off: first implemented as a Save block, then replaced after developer review by deselecting document access (`applyDocumentAccessConfigChange` in `toolPackLogic.ts`, called from `AgentFormModal.handleCapabilityConfigChange`). Checks: `npx tsc --noEmit -p .` clean; `npx vitest run src/rework/components/pages/TeamAgentsPage` 12 files, 92 tests passed.
- Review fixes (after author/independent review): alias narrowing, manifest version 0.2.0 (control-plane chat-controls cache key), strict legacy bool parsing, Simple last-pack reset, pack card a11y (missing flag as description, expand button named per pack with `aria-controls`). Checks: document-access `make code-quality` + `make test` 59 passed; fred-sdk `make code-quality` + `make test` 565 passed, 3 skipped; fred-runtime `test_document_search_source_ceilings.py` 10 passed; frontend `npx tsc`, `npx eslint`, `npx prettier`, `npx vitest run` (TeamAgentsPage, shared/organisms) 39 files, 334 passed.
- Reviewer decision 3: require `fred-sdk[agents]>=4.4.2` now; the maintainer will publish the libraries immediately after PR merge.
- All port fakes now omit the removed `attachments_only` argument.
- Not covered by automated tests: the rendered pack cards, the library options under the Team documents card, the Advanced error message placement and the Help Center copy.

## Reviewer decision follow-up — 2026-10-08

The developer confirmed immediate removal of the SDK alias, document-only retrieval
including attachments, and patch increments for all libraries. The maintainer will
publish immediately after merge. The SDK warning state and helper are deleted;
stored-config compatibility remains. ReAct/Deep now receive a conditional
evidence-only answer instruction; custom Graph prompt policy is outside that hook.

| Current verification | Result |
| --- | --- |
| Repository-root `make code-quality` | pass across all modules; runtime: 0 errors, 5 existing warnings |
| SDK `make test` | 564 passed, 3 skipped |
| Runtime `make test` | 1835 passed, 11 skipped (optional fastapi_mcp unavailable), 21 deselected |
| Document access offline pytest suite | 60 passed |
| Agent pod `make test` | 120 passed, 6 expected failures |
| Frontend focused vitest | 14 files, 108 passed |
| Frontend package `release:check`, `release:test` | pass; 153 tests passed |
| Frontend package `pack:check` | all three archives pass |
| Migration declaration / OpenSpec strict validation | pass |

Independent read-only review covered the full branch against `swift`
`c074584822f3d1e785c54c253e642b34e86da164`, starting from `a6f538f9a` plus
pending implementation changes subsequently committed in `4dc140e5e` and
`9a05777d2`. Backend/contracts/performance review found no actionable defect;
frontend/composition/release review found one P3 French help-anchor mismatch,
fixed in `3fade3d4d`. Author review checked that fix and the subsequent negative
runtime test typing correction `32ff50467`.

| Responsibility | Challenged invariant and result |
| --- | --- |
| SDK/runtime/capability | Source ceilings intersect turn flags; removed keyword rejects before I/O; both-off and general-only skip search; all cases covered by tests |
| Config and consumers | Legacy booleans, canonical precedence, serialized values and cache invalidation agree with source controls |
| Answer policy | Shared ReAct/Deep prompt receives document-only instruction only in that mode; actual model adherence untested |
| UI composition | Simple/Advanced state, switch/expander events, shared modal consumers and translated scope labels reviewed; no live browser run |
| Package metadata | All 12 Python and 3 npm packages incremented, local locks aligned, SDK/runtime floors raised; package publication and external consumers untested |
| Performance | Existing awaited search transport and tool metrics retained; no new I/O or shared mutable state; no load campaign |

Live manual task 6.3 and post-merge archive task 6.5 remain pending. No registry
publication, live model evaluation, or live browser validation is claimed.

### CI follow-up: UI peer dependency assertion

Updated the stale exact peer-dependency expectation in `build-ui.test.mjs` to
include the approved `^0.1.1-alpha.0` token range. The production manifest is
unchanged. The full `libs/frontend` `npm test` now passes: 379 passed, 0 failed,
1 skipped (local iframe SDK consumer cache absent); the previously failing
UI build determinism/scoping/externalization test passes. Targeted ESLint,
Prettier and `git diff --check` pass. Author review is limited to this mechanical
test expectation against preceding head `b19069544`; no new behavior or OpenSpec
planning is needed, and no broader readiness claim is added.
