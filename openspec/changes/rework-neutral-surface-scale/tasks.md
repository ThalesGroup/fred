## 1. Neutral ramp

- [x] 1.1 Regenerate every `--core-cold-grey-*` step in `apps/frontend/src/styles/color-ramps.css` as LCh(tone, 1.5, 280°) → sRGB (tones 0 and 100 stay black/white), add `-97-5` and `-94-5`, add a 2-line formula comment; verify each value by recomputing it with a one-off script and checking chroma ≤ 2 and hue within 10° of 280°

## 2. Semantic tokens

- [x] 2.1 Set `surface-main` and the five `surface-container-*` tokens in `colors-semantic-light.css` (100 / 99 / 97.5 / 96 / 94.5 / 93) and `colors-semantic-dark.css` (6 / 8 / 10 / 12 / 15 / 18); verify by reading the computed values in the running app in both themes
- [x] 2.2 Add `--surface-floating` (light 100, dark 15) to both files; verify it resolves in both themes

## 3. Usage remap

- [x] 3.1 Move page backgrounds from `surface-container-lowest` to `surface-main` (`styles.css` body, DocumentViewerPage); bordered content sheets keep `surface-container-lowest` (design.md); verify each page in both themes
- [x] 3.2 Repoint blend-with-background usages (HorizontalScrollRow fade, TraceEntryRow dot ring; ChatList group header kept, see design.md) to the token of the surface they sit on; verify no visible seam in both themes
- [x] 3.3 Move filled fields from `surface-container-lowest` to `surface-container-highest` (TextInput incl. autofill shadow, TextArea, DateTimeInput, Select, SearchField, TagInput, PromptEditor, PromptViewDialog textarea); verify on a form page in both themes
- [x] 3.4 Move inset wells from `surface-container-lowest` to `surface-container` (CodeBlock CSS and `customStyle`, TabularToolDetail, PlatformPromptPage instructions, LibraryTreePlayground card; MindMapBlock kept, see design.md); verify a code block in chat in both themes
- [x] 3.5 Move MarkdownRenderer zebra rows to `surface-container-low` (MainNavBar rail kept on `surface-container-lowest`, developer decision); verify a markdown table and the nav in both themes
- [x] 3.6 Move every floating element to `surface-floating` (full list in design.md, found by scanning positioned + shadowed rules); verify a menu, a tooltip, a dialog and a toast in both themes
- [x] 3.7 Classify the remaining `surface-container-lowest` and `surface-container-highest` usages listed in design.md (TeamSettings panels, AgentCard disabled icon, DocumentUploadDrawer and CreateFolderModal path, WikiEditor toolbar, MindMapBlock gradient) with the design.md role table; verify each in both themes and record the choice in verification evidence
- [x] 3.8 Re-run the `surface-container-lowest` and `surface-container-highest` usage inventory; verify every remaining occurrence matches a role from the design.md table

## 4. Quality and docs

- [x] 4.1 Run the frontend quality gate and tests (same commands as `make code-quality` / `make test`, invoked directly so the running Vite keeps its cache); verify both pass
- [x] 4.2 Update the surface token section of `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` (rule, tones, `surface-floating`, role table) and the surface row of `docs/swift/ux/COMPONENT-UX.md`; verify no doc still describes the old ordering
- [x] 4.3 Add the English migration note (patch, no operator action) per `docs/swift/ops/MIGRATION-GUIDES.md`; verify it follows the template
- [x] 4.4 Add a token migration section to `libs/frontend/design-tokens/README.md` (rule, value table, old → new token by role, steps an assistant can follow), built from the final diff; verify every remap in the diff appears in it
- [x] 4.5 Run `/code-review` on the diff and record exact verification evidence in `verification.md`; verify every finding is fixed or answered
- [ ] 4.6 After the developer's in-app check in both themes, archive the change with `openspec archive` and close #2915 once the PR is merged

## 5. Surfaces by role everywhere

- [x] 5.1 Hover/focus: transparent elements use `--state-on-surface-hover` / `-focused`; filled elements step one level further from the page; rules that already layer a state over their base are left alone; verify by listing every hover/focus rule with a surface background
- [x] 5.2 Cards and chart sections on the page move to `surface-container` (KPI, leaderboard, marketplace, HITL, responsible AI, resource explorer, chart sections, chat attachment cards, migration cards, access-pack tree); the prompt view dialog card moves to `surface-floating`; verify no other surface usage inside those cards equals the card token
- [x] 5.3 Badges, switch track and group counts move to `surface-container-highest`; code block and Mermaid headers to `surface-container-high` over a `surface-container` body; verify a code block and a Mermaid diagram show a distinct header
- [x] 5.4 InlineDrawer defaults to `surface-floating` (overlay and floating push) and `surface-container-low` (flush push); caller overrides and pane backgrounds inside the capability side panel are removed; verify the chat side panel and a document preview drawer in both themes
- [x] 5.5 Help Center page and header move to `surface-main`, its sidebar to `surface-container-low`; verify the Help Center in both themes
- [x] 5.6 Raise dark `surface-floating` from 15 to 20 so every container level nested in a floating element reads darker than it; update spec, design and docs
