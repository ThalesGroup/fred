## 1. Shared card

- [x] 1.1 Add the page-local `PlatformAccessCard` and its stylesheet (28rem card, `--spacing-l` paddings, `--font-title-medium-emphasized` title, inner surface, steps, footer groups) and remove the two former stylesheets; verify `tsc --noEmit` passes and no import of the removed files remains.
- [x] 1.2 Render `PlatformAccessError` in that card with unchanged props; verify `PlatformAdmissionGuard.test.tsx` still passes unmodified.

## 2. Access denied page

- [x] 2.1 Rebuild `PlatformAccessDeniedPage` (greeting, account block, two steps, sign-out, check, request access); verify with new tests covering first name present/absent, email missing, name and email both missing, support link present/absent, and the three actions.

## 3. Invitation page

- [x] 3.1 Valid state: new title, team in its inner surface, "Join the team" without icon, sentence removed; verify the updated `FreeEnrollmentPage.test.tsx`.
- [x] 3.2 Invalid-link state for `404 free_enrollment_link_invalid` (no retry, footer only with a support link); verify with tests.
- [x] 3.3 Temporary-problem state with retry for any other preview error and for a failed terms acceptance or join; verify with tests that it never shows the invalid-link copy.

## 4. Copy

- [x] 4.1 Add the French and English strings and delete the unused keys in both languages; verify by grep that no deleted key is referenced and that both files expose the same keys under `rework.platformAccess`.

## 5. Docs and close-out

- [x] 5.1 Update the platform access entry of `docs/swift/ux/COMPONENT-UX.md` and check the Help Center content for pages describing these screens.
- [x] 5.2 Add the migration note (impact: none).
- [x] 5.3 Record the exact verification evidence below and run `openspec validate friendlier-platform-access-entry-pages --strict`.

## Verification evidence (2026-10-13)

Run from `apps/frontend`, on the branch stacked on `feat/platform-access-ui-condense`:

- `npx tsc --noEmit`: exit 0.
- `npx eslint src/rework/components/pages/PlatformAccessPage`: exit 0, no finding.
- `npx prettier --config .prettierrc --check src/rework/components/pages/PlatformAccessPage src/locales/fr/translation.json src/locales/en/translation.json`: all files pass.
- `npx vitest run src/rework/components/pages/PlatformAccessPage/PlatformAccessDeniedPage.test.tsx`: 7 passed (first name present/absent, email missing, name missing, neither known, three actions, no support link).
- `npx vitest run src/rework/components/pages/PlatformAccessPage/FreeEnrollmentPage.test.tsx`: 15 passed (terms step, join, invalid link with and without support link, network / 503 / other 404 keep a retry, failed join, link revoked while open, loading, opening recorded once).
- `npx vitest run src/rework/core/guards/PlatformAdmissionGuard.test.tsx`: 2 passed, file unmodified.
- `rework.platformAccess` exposes the same 197 keys in French and English; no reference remains to `deniedTitle`, `deniedMessage`, `joinTitle`, `joinTeam`, `join` (string) or `invalidLink`.
- Backend answer checked by reading: `require_link` (`platform_access/service.py`) raises `HTTPException(404, "free_enrollment_link_invalid")` and the store lookup filters revoked, expired and link-access-disabled teams; the base query passes `FetchBaseQueryError` through unchanged.
- Help Center content (fr, en): no page describes these screens; nothing to update.
- `openspec validate friendlier-platform-access-entry-pages --strict`: valid.

Not run:

- `make code-quality` and `make test` (they restart the dev server the owner was using); the commands above cover the touched files only.
- `make migration-check` (`uv` not on this shell's PATH); the note follows the template by inspection.
- No visual check: rendered layout, the one-line invitation title in both languages, footer alignment and both themes remain to be confirmed on screen.

Divergence from the first plan: while the invitation is loading the card title is "Checking your invitation…" instead of the invitation title, so an invalid link never flashes "You have been invited".
