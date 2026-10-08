## 1. Picker-first editing

- [ ] 1.1 Start null policies with an empty local draft, load saved conditions unchanged, allow local final-condition removal and keep empty Test/Save disabled; verify empty/saved drafts and unchanged persistence.
- [ ] 1.2 Open the existing own-session JSON modal directly for add/edit, append only after confirmation, replace field dropdowns with exact-path text/edit actions and retain the optional value prompt; verify cancellation, field bounds, nested paths and background revision races.
- [ ] 1.3 Move the explicit save-rule action near the title and add localized unsaved/saving/saved feedback and persistence guidance; verify successful saves, failed/conflicting saves, busy guards and preview without saving.
- [x] 1.4 Reuse the home navigation control for four accessible panels, preserve draft/selection across navigation, move filtering to the last view and standardize page/modal typography with concise help; verify keyboard navigation, state retention, real-account rendering and focused regressions.

## 2. Verification and delivery

- [ ] 2.1 Validate real-account desktop/narrow journeys with actual local services before broad tests, capture safe screenshots and run focused editor/picker/page regressions.
- [ ] 2.2 Update existing UX/operator docs, run root quality once for the series and obtain author/independent read-only branch review; resolve supported findings and record coverage/exclusions in PR #2966.
- [ ] 2.3 Commit this UI refinement separately, update the existing issue/PR and screenshots, synchronize/archive verified specs and confirm final checks/reviews/mergeability.

Presentation verification: root `make code-quality` passed after correcting CSS property order. 36 focused page/editor/link tests passed. Real-account Playwright confirmed four tabs, one exposed panel, keyboard End/Home navigation, preserved draft and selection, and zero admission writes while navigating. The 418 px content view fits without horizontal page overflow. Ordinary text computes to 16 px and section headings to 22 px; real picker and invitation dialogs also compute to 16 px. Safe desktop/narrow rule screenshots contain only a generic unsaved operand. An independent read-only review of the delta against 679cd54e105443226e89427351e08a70bcffd2ad found no actionable issues; backend/SQL and pending picker/link/dry-run work were excluded.
