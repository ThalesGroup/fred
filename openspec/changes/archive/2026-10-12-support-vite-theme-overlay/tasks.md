# Tasks

## 1. Shared installer

- [x] 1.1 Extract existing installation logic into a shared shell script and update Docker packaging/entrypoint; verify valid, rejected, optional and required archive cases with the existing container smoke test.

## 2. Local frontend integration

- [x] 2.1 Add Vite startup installation and safe overlay serving, plus focused tests for asset precedence, MIME types, traversal, stock fallback, credentials and cleanup; verify the focused tests pass.
- [x] 2.2 Preserve shell overrides through Make and parse file theme settings with Vite and document local `config/.env` setup in the template/README; verify a shell URL overrides the file and the existing frontend task loads a ZIP without tracked public-file changes.

## 3. Integration and review

- [x] 3.1 Verify the Paris Aeroport ZIP through localhost Vite against local SeaweedFS, including catalog, font, logo and translations; verify restart activation and disabling the URL restore expected behavior.
- [x] 3.2 Review the full branch against Swift and obtain an independent read-only review; record findings, dispositions and focused verification in this task file or the existing PR.

## Workflow follow-up

- Sync the delta and archive after verification and required review.

## Verification and review evidence

- `node --test scripts/theme-overlay.test.mjs`: 10 passed, covering asset/MIME
  precedence, missing and invalid ZIPs, private SigV4, traversal, symlinks,
  quoted dotenv/shell precedence, restart activation and cleanup.
- `FRONTEND_IMAGE=fred-frontend:theme-overlay-smoke sh apps/frontend/tests/theme-container-smoke.sh`: passed. The local runtime test image overlays the current entrypoint, shared installer and public files onto the existing frontend image; no full production rebuild was performed.
- Frontend `tsc --noEmit`, targeted Prettier and `git diff --check`: passed.
- Real Vite on localhost:5174 downloaded the Paris Aeroport ZIP from local Docker
  SeaweedFS; catalog, properties, CSS, SVG logo, TTF MIME and French label verified
  over HTTP. Disabling the URL restored stock catalog/properties. Test server
  stopped; ignored `config/.env` prepared for the developer's frontend task.
- Independent read-only full branch review: base `origin/swift` at `8d5b413d7`,
  HEAD `117e8dfdf` plus the implementation working tree. Covered archive installation,
  nginx/Docker, Vite, Make/dotenv, browser configuration/boot, catalog and pickers,
  CSS, docs and specs. Whitespace-only catalog labels and raw dotenv exports were
  found, fixed and independently re-reviewed with no remaining actionable findings.
  PR target was also confirmed as Swift by the author using GitHub.
- Full frontend suite and authenticated browser UI were not rerun for this
  extension; HTTP integration and focused regressions establish the loader contract.

- OpenSpec change validates strictly. Synced main spec validates normally; strict
  validation reports a pre-existing >500-character requirement (requirement 2),
  whose text was preserved rather than changed outside this scope.
