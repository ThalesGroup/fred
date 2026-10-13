## 1. Invitation URL

- [x] 1.1 Generate `/join/:token` URLs and route them to the enrollment page; verify with focused frontend tests.
- [x] 1.2 Recognize `/join/:token` as a standalone admission path and preserve it through OIDC; verify focused route and OIDC tests.

## 2. Token protection and verification

- [x] 2.1 Mask `/join/:token` in Fred logs and update the operator note; verify with the focused log sanitizer test.
- [x] 2.2 Check the new URL and left-visible selection in dark-mode Playwright, then run root quality and review the diff.
