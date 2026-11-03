## 1. Admin persistence and API

- [x] 1.1 Add the pod-default store to the PR migration and verify database round-trip and reset tests.
- [x] 1.1a Repair databases already stamped at the earlier PR revision and verify fresh and interim migration paths.
- [x] 1.2 Add read, save and clear API routes with live pod-profile validation and verify authorization and unavailable-pod tests.

## 2. Managed routing

- [x] 2.1 Pass the saved pod default and manual fallback through the trusted per-turn binding and verify routing precedence, YAML fallback and disappearance tests.
- [x] 2.2 Apply the same effective default in the composer and team policy validation; verify focused routing policy tests.

## 3. Administration UI

- [x] 3.1 Regenerate the control-plane client and build Agent pods/Platform tabs with per-pod selectors; verify focused component tests.
- [x] 3.1a Restrict both pod selectors and API writes to platform-enabled models while preserving the display of existing YAML and saved choices; verify focused tests.
- [ ] 3.2 Verify both tabs and the per-pod default display in the local UI, including an unreachable pod state.

## 4. Close-out

- [ ] 4.1 Update docs and migration notes, run root quality once, audit the full PR, and leave draft PR CI green.
