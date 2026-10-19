## 1. One authorization path

- [ ] 1.1 Introduce the single `authorize` helper and route every read and mutation through it, deleting `api::require`, `documents::authorized` and per-request `require_context`; verify `make test-integration` with the updated request budgets (no caller role Reads)
- [ ] 1.2 Drop context checks from team/project and personal-space creation, keeping `may_attach` and `/me/spaces`; verify creation, isolation and I23 tests

## 2. Uniform answers

- [ ] 2.1 Foreign-organization targets return 403 on folders, documents, receipts and downloads; probes answer `allowed: false` for foreign and missing targets; verify with one cross-organization test per route family
- [ ] 2.2 Folder parent outside the space returns 404 on creation; dependency failures return 503 on every authorization; verify with focused tests

## 3. Close-out

- [ ] 3.1 Update arc42 security, matrix, documents and quality cost tables to the single Check (prefer one sequence diagram over prose); verify `docs.py generate` and `check`
- [ ] 3.2 Independent review, fixes re-reviewed; `make code-quality`, `make test`, `make test-integration` green; archive this change
