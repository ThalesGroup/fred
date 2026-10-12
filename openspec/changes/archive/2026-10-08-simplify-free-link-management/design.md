## Context

PlatformAccessLinkManager already owns paginated history, creation, explicit URL recovery and revocation mutations. Its current single dialog renders note and raw datetime-local inputs above history, and row recovery shows a URL requiring a second copy action. Platform admin AnalyticsPage uses TimeRangeSelector, whose CustomRangePanel uses shared DateTimeInput. The existing shared atom provides the same native date/time picker with localized 24-hour rendering. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:** separate browsing from creation, reuse the real KPI date component and make invitation copying explicit and dependable.

**Non-Goals:** changing link lifecycle, authenticated counting, authorization, visitor storage or backend contracts; automatic message delivery or a new calendar library.

## Decisions

- Retain PlatformAccessLinkManager as the owning component with exclusive list/create/revoke views, using shared Dialog. The list shows history and a Create link action; creation shows note followed by an optional expiration selector using the KPI popover layout. Cancel returns to the list without generating. This avoids duplicated manager state or a second history endpoint.
- Reuse TimeRangeSelector styles, its clock trigger, date/time panel, shortcuts and Apply action. An invitation needs one optional future timestamp, so use one DateTimeInput, future 24-hour/7-day/30-day shortcuts and No expiration instead of past ranges or a historical month strip. Keep the panel inside the creation dialog for correct focus trapping and unclipped content; Escape dismisses only the selector and restores trigger focus. Creation stays disabled while a date draft is open. Retain future-date validation, local-to-UTC ISO conversion, error association and busy/Free guards; leave the analytics selector and shared atom unchanged.
- After creation, keep a success view containing the usable URL and Copy URL button. Do not depend on automatic clipboard permission across the asynchronous creation request. Explicit clicking supplies a fresh user gesture and separates creation success from clipboard outcome.
- History Copy URL reuses the own-admin reveal mutation and then clipboard.writeText. Announce copied only after resolution. If recovery succeeds but copying fails, expose the already recovered URL with a retry/manual-copy option; retain no reusable payload in RTK Query after unwrap. This preserves recovery authorization and avoids generation retries after clipboard failures.
- Change only the column wording to Clicks and keep its authenticated-openings definition in explanatory text; preserve values, last-opening time, polling and pagination.
- Clear temporary URL/copy status on dismissal or appropriate view changes; never log or place URLs in public screenshots. Suspended teams retain list, copy/recovery where supported and revocation; creation remains disabled.

## Risks / Trade-offs

- Browser clipboard APIs can reject asynchronous writes or be unavailable: show a selectable URL and an explicit retry button, with separate copy feedback.
- Hidden list/create views can misplace errors: render each mutation error in the active view and preserve creation inputs after API failures.
- Repeated clicks could create duplicate links: keep existing mutation busy guards and generate once per confirmed submission.
- Date entry could appear to use another timezone: retain localized date input and the existing UTC request conversion and future-only validation.

## Migration Plan

Deploy or roll back the frontend normally. Update the existing operator note with no additional action. No migration, configuration key or generated API change is required.
