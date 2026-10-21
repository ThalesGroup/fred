Tracking: GitHub issue #3208. Paths relative to the repository root.

## 1. Package and capability

- [ ] 1.1 Scaffold `libs/capabilities/fred-capability-spreadsheet/` from `fred-capability-html-artifact` (pyproject with `openpyxl>=3.1.5`, entry point `spreadsheet`, Makefile, baselines, `uv.lock`, README)
- [ ] 1.2 `SpreadsheetCapability`: manifest (`id="spreadsheet"`, i18n name/description, `icon`), `ConfigModel = EmptyModel`, `tools()` returning `create_spreadsheet`; default `execution_models` and `team_scope`
- [ ] 1.3 Tool input models (D2) with case-insensitive enums and the per-column currency
- [ ] 1.4 Workbook builder (D3) in a worker thread: types to number formats, currency symbols, header style, freeze, auto filter, widths, totals formulas
- [ ] 1.5 Validation and limits (D4) with messages naming sheet / row / column; formula-injection guard (D5)
- [ ] 1.6 Delivery through `workspace_fs` and `LinkPart` (D6); `is_error` when the port is absent
- [ ] 1.7 Wire into `apps/fred-agents` (pyproject, `uv.lock`, image, pyright) and the repo lists (root Makefile, pre-commit, CI change detection, release order); `registry.validate()` passes at boot

## 2. Frontend

- [ ] 2.1 `toolPacks.ts`: `CAP_SPREADSHEET` and a pack in `document_production`
- [ ] 2.2 `locales/{en,fr}/translation.json`: `capability.spreadsheet.name/description`, pack title/description
- [ ] 2.3 Pack logic tests updated (toolPackLogic) if they enumerate packs

## 3. Help Center

- [ ] 3.1 "Create an Excel file" section under Document production in `helpCenter/content/en/features/capabilities.md` (what it does, limits, example)
- [ ] 3.2 Same section in `fr/features/capabilities.md` ("Créer un fichier Excel")

## 4. Tests and verification

- [ ] 4.1 Offline tests: workbook read back with openpyxl (sheets, headers, values, number formats, currency symbols, freeze, widths, totals formulas), every validation error, every limit, injection guard, missing port
- [ ] 4.2 Capability tests: manifest, entry point discovery, tool schema has only LLM arguments, Graph assembly accepts it
- [ ] 4.3 `make code-quality`, `make test` in the package, fred-agents and frontend; `ruff --select I` and basedpyright
- [ ] 4.4 Live check on the default Mistral model, ReAct and Deep agent: request -> tool call -> download -> file opens in LibreOffice without repair; record in verification evidence
- [ ] 4.5 `fred-performance-reviewer` on the tool call site (CPU work off the event loop)

## 5. Docs and release

- [ ] 5.1 `docs/swift/capabilities/AUTHORING.md` one row; package README
- [ ] 5.2 Migration note (`docs/swift/ops/MIGRATION-GUIDES.md`): new admin-gated capability, new dependency in fred-agents
- [ ] 5.3 Record verification evidence, archive the change, close #3208

## Verification evidence

(filled during implementation)
