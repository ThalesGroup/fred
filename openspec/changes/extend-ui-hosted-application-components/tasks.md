## 1. Neutral canonical components

- [x] 1.1 Export props for the eleven already-neutral components and narrow packaged icon contracts; verify source TypeScript and positive/negative icon cases.
- [x] 1.2 Replace KPI/table translation hooks with typed label props and OptionModel with neutral SelectOption; update FRED callers and verify KPI states plus existing selection/sorting/client/server pagination tests.
- [x] 1.3 Include the internal drawer resize/storage dependency chain and resolve canonical aliases; verify close/layout/resize/persistence behavior and restricted-storage rendering.
- [x] 1.4 Inject Toast copy behavior and configurable action labels through Toast and ToastProvider; wire FRED's existing clipboard action and verify copy, expiry, dismissal, and multiple-toast identity.
- [x] 1.5 Add token-based StatusBadge, migrate StatusPill, and remove superseded pill styles; verify evaluation labels/tone mapping and all five visual tones.

## 2. Package surface and evidence

- [ ] 2.1 Extend `ui/src/index.tsx` exports and `scripts/package-inputs.mjs` with exactly the required canonical source/style/helper inputs; verify build/declaration closure and CI input-selection tests.
- [ ] 2.2 Extend UI archive/build validators and their existing tests for all new values/types and forbidden aliases/dependencies; verify malformed/missing-export candidates fail.
- [x] 2.3 Extend the existing isolated React fixture with every new export and meaningful type-negative cases; verify the actual packed candidate type-checks and builds outside the checkout.
- [x] 2.4 Extend browser smoke with both-theme rendering and form/disclosure/table/file/drawer/toast interactions; verify local assets, scoped styles, and existing ten-component regression checks.

## 3. Release preparation and verification

- [x] 3.1 Bump only UI to `0.1.0-alpha.3`, regenerate affected lockfiles and selected candidate fixture coordinates, and update UI CHANGELOG/README plus necessary release guidance; verify release-coordinate validation without rewriting historical evidence.
- [x] 3.2 Add the required English migration note and update applicable component UX guidance; verify docs describe neutral labels, copy injection, new exports, and no operator action.
- [ ] 3.3 Run root `make code-quality` and `make test`, frontend TypeScript/Prettier checks, and producer `make pack-check`, `make isolated-consumer`, and `make browser-smoke`; record exact results and any prerequisite blockers here.
- [x] 3.4 Obtain the required independent code review and design-system/contract review, resolve findings, and verify affected checks after fixes.
- [ ] 3.5 Reconcile final artifacts, sync/archive this change, commit reviewable blocks, push the existing topic branch, and open a draft PR titled `feat(#2887): ...`; verify the PR links #2887 and excludes publication and consumer migration.

## Verification evidence

- Approved scope: developer confirmation in this session, 2026-10-01.
- Targeted frontend tests: 5 files, 43 tests passed (KPI labels, table/pagination, Toast, restricted storage).
- Producer pack-check: all three archives passed; UI candidate is alpha.3, other coordinates unchanged.
- Isolated-consumer: token, React (including new public types and type-negative cases), and SDK consumers passed.
- Browser smoke: both themes and existing SDK/production-host checks passed with zero external requests. Hosted forms, disclosure, selection/sorting/pagination, file upload, badges, drawer resize/persistence/dismissal, and toast copy/expiry/dismissal are exercised.
- Independent correctness/design-system/contract review: one type-negative directive placement finding fixed and verified by isolated-consumer; no product-code findings.
- Migration-check passed. Full root quality/tests are in progress after reinstalling ignored local Python environments whose scripts pointed to the previous worktree path.
