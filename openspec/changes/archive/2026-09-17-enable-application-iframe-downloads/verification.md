# Implementation verification (2026-09-17)

Issue: ThalesGroup/fred#2727. Planning PR: #2726. Independent implementation review is complete; task 3.2 is checked.

## Automated results

| Gate | Result |
| --- | --- |
| `cd apps/frontend && ./node_modules/.bin/vitest run src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.test.tsx` | Passed: 40/40 tests. Exact five-token sandbox and existing admission, handshake, origin/source, route, request, and lifecycle regressions. |
| `cd apps/frontend && ./node_modules/.bin/vitest run src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.test.tsx src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.sdk-integration.test.tsx` | Passed: 40 tests; 7 packed-SDK cases skipped without the archive environment variable. |
| `cd libs/frontend && make host-integration` | Passed: 7/7 packed-SDK tests against the production host handler. A disposable test archive was packed; no release candidate or publication was created. |
| `cd libs/frontend && node --test tests/browser-smoke.test.mjs tests/browser-prerequisites.test.mjs` | Passed: 8/8 tests. |
| `cd libs/frontend && make browser-smoke` | Passed with pre-provisioned Playwright Chromium, staged consumers, and local loopback servers. Existing token, font, UI, and cross-origin SDK checks passed alongside the production-host download. |
| `cd apps/frontend && make test build` | Passed: application proxy tests 9/9; Vitest 2458 passed, 9 skipped across 236 files; production build transformed 5582 modules and completed. |
| Repository root `make code-quality` | Passed across all 13 configured modules, including `libs/frontend` and `apps/frontend`. Existing unreachable-code warnings remain in untouched `libs/fred-core/fred_core/scheduler/schedule_spec.py:87` and `libs/fred-runtime/fred_runtime/__main__.py:80`; no errors. |
| `openspec validate enable-application-iframe-downloads --strict` and `git diff --check` | Passed. |

The first sandboxed browser attempt failed with `listen EPERM` on `127.0.0.1`; the approved elevated Chromium runs passed. The first root-quality attempt was interrupted while provisioning unrelated Python dependencies to avoid overlapping the frontend install. A later sandboxed run failed DNS lookup for the `temporalio` wheel; the approved elevated rerun passed. Fixture import/JSX errors encountered during development were corrected before the final browser run.

## Real-browser download proof

`libs/frontend/scripts/browser-smoke.mjs` mounts the actual `TeamApplicationHostPage.tsx` in a test-only Vite page. Controlled hook/provider mocks supply an authorized collaborative-team application, whose configured UI URL is on a distinct loopback origin. The final full-browser evidence recorded host `http://127.0.0.1:5173`, child `http://127.0.0.1:56603`, and zero external requests. The child displays **Download Markdown**; clicking it creates a `text/markdown` Blob, object URL, and `<a download>`. Chromium emitted a download with suggested filename `synthesis.md`. Playwright saved the file and matched its exact 42 bytes to `# Hosted synthesis\n\nKnown Markdown bytes.\n`. The browser check also asserts the frame's production sandbox tokens and its child origin.

## Scope and review

The production change adds only `allow-downloads` after the four existing sandbox tokens. The exact set is `allow-scripts allow-same-origin allow-forms allow-popups allow-downloads`; `allow-top-navigation`, `allow-top-navigation-by-user-activation`, and `allow-popups-to-escape-sandbox` remain absent. Existing frame admission, protocol `"1"`, source-window/origin checks, bearer ownership, relative request routing, and host navigation logic are unchanged.

All browser fixture files live under `libs/frontend/fixtures/production-host/`, so the existing `libs/frontend/**` CI selection includes fixture-only edits. No public package source/version/export, npm workflow, backend, deployment, RAGS, canonical OpenSpec spec, or RFC file changed. No package publication, commit, push, PR, issue mutation, spec sync, or archive occurred.

## Independent review

Review found no blocking issues, requested no code changes, and found no scope drift. It confirmed that the production runtime adds only `allow-downloads`; the exact five-token sandbox excludes top-navigation and popup-escape permissions. The Chromium fixture imports and mounts the real production `TeamApplicationHostPage`, uses distinct loopback host/child origins, and enforces local-only requests. The browser observes and saves a real `synthesis.md` download and verifies the exact Markdown bytes. The review also confirmed no iframe protocol, public frontend package, package version, release workflow, backend, deployment, RAGS, RFC, canonical-spec, or CI-workflow change.
