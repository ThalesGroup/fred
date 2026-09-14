## 1. Package scaffold

- [x] 1.1 Create `fred_capability_ppt_filler/builder/` (models, analysis, overrides, render, tools, capability, router) and the second `fred.capabilities` entry point `ppt_builder`; verify `registry.validate()` passes with both capabilities registered in a test
- [x] 1.2 Bundle the built-in theme `default_theme.pptx` (one layout per intent, neutral styling) as package data; verify it analyses into every intent of the vocabulary in a test

## 2. Analysis

- [x] 2.1 Inventory models (`TemplateInventory`, `Pattern`, `Zone`, `RepeatGroup`, `AnalysisSummary`, stable ids) with JSON round-trip tests
- [x] 2.2 Layout classification from placeholder signatures, including the top-band BODY-as-heading rule; verify with a synthetic deck covering every intent and with the reference template (`tests/test_builder_analysis.py`, reference file optional via env var, skipped when absent)
- [x] 2.3 Example-slide analysis: placeholders kept, shared decoration excluded, sample-text lexicon, free-box roles by geometry and font rank; verify each rule with a synthetic slide and one mutation test per rule
- [x] 2.4 Repeated-group detection (sibling groups and aligned clusters, structure signature, reading order); verify on synthetic agenda/KPI/steps/team slides that the count and per-item roles are right
- [x] 2.5 Intent assignment, exclusion-by-default rules (chart, table, icon bank, placeholder-less layout), `preferred` flag; verify the reference template yields the expected intents for its 20 layouts and 38 slides (table in the test)
- [x] 2.6 Annotation channels: shape-name vocabulary, `intent:` notes, `{{key}}` markers; verify each overrides the heuristic in a test

## 3. Overrides and configuration

- [x] 3.1 `PatternOverride` model and `apply_overrides(inventory, overrides)` returning the effective inventory plus dropped overrides; verify keep-role, excluded pattern, relabel, and re-upload re-application with drops
- [x] 3.2 `PptBuilderConfig` and `validate_config` three states (upload → analyse, store template and patterns PDF, keep matching overrides; ordinary edit → pass-through; no template → built-in theme); verify with the in-memory fakes
- [x] 3.3 Router `POST /analyze`, `POST /preview`, `GET /theme`, `GET /theme/preview.pdf` (bounded, stateless); the saved thumbnails PDF is fetched from its Knowledge Flow path stored in the config, so no proxy route; verified with the FastAPI test client

## 4. Rendering

- [x] 4.1 Layout instantiation and placeholder fill by role, bullets with levels through the shared traversal; verify title/body/columns rendering re-parses correctly
- [x] 4.2 Example-slide duplication (spTree deep copy + picture/media relationships) and original-slide removal; verify a duplicated slide keeps its pictures, the output has only plan slides in plan order, and file size stays within 1.2× the template for 10 duplications
- [x] 4.3 Repeat-group fill and unused-item removal, sample-text clearing, empty image-placeholder removal; verify no lexicon text remains in a rendered deck
- [x] 4.4 Overflow control (line estimate, fontScale floor, word-boundary truncation, report); verify a long value is shrunk and a very long one is truncated and reported
- [x] 4.5 Image zones from team folders (reuse the listing tool and embedding helper); verify placement, empty-zone removal and invalid-reference error
- [x] 4.6 Intent degradation order; verify a plan asking for a missing intent renders with the substitute and reports it

## 5. Tool and middleware

- [x] 5.1 `SlidePlan`/`DeckPlan` models, dynamic `pattern` enum, tool description catalogue built from the effective inventory; verify the description lists every included pattern with its zones and limits
- [x] 5.2 `build_presentation` tool: validation (unknown/excluded pattern, empty plan), bounded render, workspace write, PDF preview part or download chip, truncation report; verify with fakes mirroring `test_fill.py`
- [x] 5.3 Middleware with the prompt fragment, `execution_models=("react",)`, side-panel spec reusing the preview pane; verify assembly on a ReAct definition and rejection on Graph

## 6. Frontend

- [x] 6.1 `Makefile` target `update-ppt-builder-capability-api`, generated slice under `features/capabilities/ppt_builder/api/`; verify the generated hooks compile
- [x] 6.2 `usePptBuilderAnalysis` hook (upload → analyze + preview, blocking error, summary); verify with vitest
- [x] 6.3 `PptBuilderConfigForm` (upload row, summary, review button) and `PptBuilderPackOptions`; verify render and blocking behaviour with vitest
- [x] 6.4 `PatternGrid` (react-pdf thumbnails, label, intent Select, zone chips, include Switch small, excluded section) and `PatternDetailDialog` (zone outlines, role Selects) writing overrides through `onConfigChange`; verify overrides serialisation with vitest
- [x] 6.5 Plugin registration, tool pack "Presentation builder", `AgentFormBody` pack options branch, `en`/`fr` strings; verify `make code-quality` and `make test` in `apps/frontend`

## 7. Verification and docs

- [ ] 7.1 End-to-end on the local stack: agent with the reference template, chat "prépare une présentation de 8 slides sur X", preview and download work; then the same agent without template
- [x] 7.2 `make code-quality` and `make test` green in `libs/fred-capability-ppt-filler`; `fred-performance-reviewer` on the tool path (per-turn call site)
- [x] 7.3 `/code-review` on the branch diff; apply fixes
- [x] 7.4 Docs: `COMPONENT-UX.md` (config widget section), `AUTHORING.md` worked-example row, package `README.md`; issue #2679 updated
