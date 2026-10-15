## 1. Invitation presentation

- [x] 1.1 Remove the support footer from checking, valid and invalid invitation cards; verify focused enrollment tests show no support action in those states while join and inviter guidance remain.
- [x] 1.2 Make the invitation's temporary-error card omit its footer links without changing the admission guard's footer links; verify focused enrollment and guard tests cover both callers and retry remains available.
- [x] 1.3 Verify the refusal page still offers the configured request-access destination and hides that action when unconfigured with its focused tests.

## 2. Documentation and verification

- [x] 2.1 Update the Platform access entry in `COMPONENT-UX.md` and add an English `impact: none` migration note; verify `make migration-check` passes.
- [x] 2.2 Run focused frontend formatting, lint, type and test checks, then the required root quality gate once; record exact results or unrelated failures in the PR.
- [x] 2.3 Review the full branch against `swift`, including the shared error consumer and existing specs; dispose of findings and validate this OpenSpec change strictly.

## 3. Specification close-out

- [x] 3.1 Reconcile the previously shipped entry-page delta before syncing this one; verify the resulting current capability spec preserves denial support and excludes invitation support, then archive completed changes.
