## 1. Neutral ramp

- [x] 1.1 Regenerate every `--core-cold-grey-*` step in `apps/frontend/src/styles/color-ramps.css` as LCh(tone, 1.5, 280°) → sRGB (tones 0 and 100 stay black/white), add `-97-5` and `-94-5`, add a 2-line formula comment; verify each value by recomputing it with a one-off script and checking chroma ≤ 2 and hue within 10° of 280°

## 2. Semantic tokens

- [x] 2.1 Set `surface-main` and the five `surface-container-*` tokens in `colors-semantic-light.css` (100 / 99 / 97.5 / 96 / 94.5 / 93) and `colors-semantic-dark.css` (6 / 8 / 10 / 12 / 15 / 18); verify by reading the computed values in the running app in both themes
- [x] 2.2 Add `--surface-floating` (light 100, dark 15) to both files; verify it resolves in both themes

## 3. Usage remap

- [ ] 3.1 Move page and content backgrounds from `surface-container-lowest` to `surface-main` (`styles.css` body, GdprPage, GcuPage, ReleaseNotesPage, BootstrapPage, TeamAdminCharterPage, DocumentViewerPage); verify each page in both themes
- [ ] 3.2 Repoint blend-with-background usages (HorizontalScrollRow fade, TraceEntryRow dot ring, ChatList group header) to the token of the surface they sit on; verify no visible seam in both themes
- [ ] 3.3 Move filled fields from `surface-container-lowest` to `surface-container-highest` (TextInput incl. autofill shadow, TextArea, DateTimeInput, Select, SearchField, TagInput, PromptEditor, PromptViewDialog textarea); verify on a form page in both themes
- [ ] 3.4 Move inset wells from `surface-container-lowest` to `surface-container` (CodeBlock CSS and `customStyle`, TabularToolDetail, PlatformPromptPage instructions, MindMapBlock chart pane, LibraryTreePlayground card); verify a code block in chat in both themes
- [ ] 3.5 Move MarkdownRenderer zebra rows and MainNavBar to `surface-container-low`; verify a markdown table and the nav in both themes
- [ ] 3.6 Move floating elements to `surface-floating` (Menu, Tooltip, WritableDocumentPane popup and tooltip, SourceDetailModal); verify a menu, a tooltip and a modal in both themes
- [ ] 3.7 Classify the remaining `surface-container-lowest` and `surface-container-highest` usages listed in design.md (TeamSettings panels, AgentCard disabled icon, DocumentUploadDrawer and CreateFolderModal path, WikiEditor toolbar, MindMapBlock gradient) with the design.md role table; verify each in both themes and record the choice in verification evidence
- [ ] 3.8 Re-run the `surface-container-lowest` and `surface-container-highest` usage inventory; verify every remaining occurrence matches a role from the design.md table

## 4. Quality and docs

- [ ] 4.1 Run `make code-quality` and `make test` from the repo root (warn first: they restart Vite); verify both pass
- [ ] 4.2 Update the surface token section of `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` (rule, tones, `surface-floating`, role table) and the surface row of `docs/swift/ux/COMPONENT-UX.md`; verify no doc still describes the old ordering
- [ ] 4.3 Add the English migration note (patch, no operator action) per `docs/swift/ops/MIGRATION-GUIDES.md`; verify it follows the template
- [ ] 4.4 Run `/code-review` on the diff and record exact verification evidence in this change; then archive it with `openspec archive` and close #2915
