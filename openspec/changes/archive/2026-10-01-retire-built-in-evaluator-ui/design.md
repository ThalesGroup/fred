## Context

See proposal.md. TeamSettingsPage selects the evaluation screens by route; TeamContentNavbar exposes the entry. TaskActivity polls an evaluator RTK slice also registered globally. The built-in StatusPill was modified by #2890 to consume the shared badge.

## Goals / Non-Goals

Remove the duplicate frontend integration and its unused support code. Backend routes, permissions, deployment configuration, evaluation records and the external evaluator repository remain outside this removal.

## Decisions

- Delete the evaluator views and dedicated slice rather than merely hide navigation, so Fred no longer ships or polls that obsolete integration.
- Use the existing unknown-section Members redirect for old URLs. Do not hardcode an application ID or bypass configurable Apps admission with an automatic evaluator redirect.
- Remove evaluator-specific Activity, rehydration, SSE routing and task metadata plumbing. Inspect shared task helpers and preserve generic task behavior needed by Fred services.
- Keep shared SDK exports, including StatusBadge, SectionHeader and Breadcrumb. Reconcile the specification that currently requires the removed StatusPill consumer.
- Use a dedicated removal commit in existing PR #2890 because that PR changes the deleted consumer and its associated specification. Track the removal separately in #2904.

## Risks / Trade-offs

- Deployments using the built-in UI need the external application registered → document the operator action in a migration note.
- Broad locale deletion could break shared task labels → trace consumers before deleting keys.
- Old bookmarks no longer open evaluations → test the explicit existing fallback and explain Apps access in UX/migration documentation.

## Migration Plan

Register and validate the external evaluator in Apps before deploying the frontend removal. No evaluation data is migrated or deleted. Rollback restores the previous Fred frontend image; the external evaluator remains independent.
