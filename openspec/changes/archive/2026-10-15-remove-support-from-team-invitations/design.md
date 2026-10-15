## Context

See proposal.md. `FreeEnrollmentPage` supplies a support footer to its checking, invitation and invalid-link cards. Its temporary-error path uses `PlatformAccessError`, which currently adds support even when its caller hides sign-out. `PlatformAccessDeniedPage` already shows a configured "Request access" action; `PlatformAdmissionGuard` uses `PlatformAccessError` for a separate verification failure.

The shipped entry-page behavior was recorded in `friendlier-platform-access-entry-pages`, whose issue and PR are merged. That change was synchronized and archived before this delta was applied to the main capability spec.

## Goals / Non-Goals

**Goals:** Keep the invitation route free of a support action in every state while leaving admission refusal and the guard's verification failure unchanged.

**Non-Goals:** Change admission decisions, link validity, enrollment operations, copy, configuration or shared support destinations.

## Decisions

- Remove support-property consumption and support footers from `FreeEnrollmentPage`. Its invalid-link message already directs the visitor to the inviter; loading and valid invitation need only their current content and join action.
- Replace `PlatformAccessError`'s enrollment-only `hideSignOut` prop with `hideFooterLinks`. This expresses the invitation's lack of both sign-out and support as one caller choice while keeping its Retry button in the footer; the guard keeps its sign-out and support links. An extra support-specific prop would preserve a combination neither caller needs.
- Keep `PlatformAccessDeniedPage` unchanged. Its existing request-access button uses `contactSupportLink` only when configured, and its focused tests verify the destination and absent-link state.

## Risks / Trade-offs

- [The shared error card could lose support on guard failures] - Keep the default footer and cover the guard's support link with a focused test.
- [The capability spec could retain stale support behavior] - The earlier shipped change was archived first; verify the final spec excludes invitation support.

## Migration Plan

Normal frontend deployment is sufficient. There is no API, configuration or data change. Rollback restores the former invitation footer.
