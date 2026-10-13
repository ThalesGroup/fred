## 1. Shared card

- [ ] 1.1 Add the page-local `PlatformAccessCard` and its stylesheet (28rem card, `--spacing-l` paddings, `--font-title-medium-emphasized` title, inner surface, steps, footer groups) and remove the two former stylesheets; verify `tsc --noEmit` passes and no import of the removed files remains.
- [ ] 1.2 Render `PlatformAccessError` in that card with unchanged props; verify `PlatformAdmissionGuard.test.tsx` still passes unmodified.

## 2. Access denied page

- [ ] 2.1 Rebuild `PlatformAccessDeniedPage` (greeting, account block, two steps, sign-out, check, request access); verify with new tests covering first name present/absent, email missing, name and email both missing, support link present/absent, and the three actions.

## 3. Invitation page

- [ ] 3.1 Valid state: new title, team in its inner surface, "Join the team" without icon, sentence removed; verify the updated `FreeEnrollmentPage.test.tsx`.
- [ ] 3.2 Invalid-link state for `404 free_enrollment_link_invalid` (no retry, footer only with a support link); verify with tests.
- [ ] 3.3 Temporary-problem state with retry for any other preview error and for a failed terms acceptance or join; verify with tests that it never shows the invalid-link copy.

## 4. Copy

- [ ] 4.1 Add the French and English strings and delete the unused keys in both languages; verify by grep that no deleted key is referenced and that both files expose the same keys under `rework.platformAccess`.

## 5. Docs and close-out

- [ ] 5.1 Update the platform access entry of `docs/swift/ux/COMPONENT-UX.md` and check the Help Center content for pages describing these screens.
- [ ] 5.2 Add the migration note (impact: none).
- [ ] 5.3 Record the exact verification evidence below and run `openspec validate friendlier-platform-access-entry-pages --strict`.
