Tracking: GitHub issue #3208.

## 1. Capability

- [x] 1.1 Package, manifest, tool schema (D1, D2), wiring into fred-agents and the repo lists
- [x] 1.2 Writer, validation, limits (D3, D4)
- [x] 1.3 Delivery through `workspace_fs`, duplicate-call guard (D12)

## 2. Formulas

- [x] 2.1 Parser, allow-list, references, text-pattern refusals (D5, D6)
- [x] 2.2 Evaluator, cached values, budget (D7)
- [x] 2.3 `compute` removed, sheet-level `total` map applied or refused (D8)
- [x] 2.4 Success-text notes (D9)

## 3. Revisions

- [x] 3.1 `changes` applied on the base, formula references adjusted (D10)
- [x] 3.2 `cap_spreadsheet_workbook` table, store, Alembic tree (D11)
- [x] 3.3 Versioned names and latest-version marker (D12)

## 4. Frontend and docs

- [x] 4.1 Agent form pack, en/fr strings
- [x] 4.2 Preview card and side panel (D13): formula bar, keyboard navigation, referenced-cell highlight
- [x] 4.3 Help Center en/fr, package README, AUTHORING row, DATABASE_MIGRATIONS row, migration note

## 5. Verification

- [x] 5.1 Package, fred-agents and frontend `make code-quality` and `make test`; `ruff --select I`, basedpyright
- [x] 5.2 `fred-performance-reviewer` on the tool call site
- [x] 5.3 `python -m fred_runtime migrate` on the local dev database created `cap_spreadsheet_workbook` (revision `s5p1r2e3a4d5`), 2026-10-28
- [x] 5.4 Live check in the UI by the owner with a ReAct agent, 2026-10-28
- [ ] 5.5 Live check with a Deep and a Graph agent (creation and revision)
- [ ] 5.6 Archive the change, close #3208
