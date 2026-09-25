## Context

See `proposal.md` — Why. What shapes the approach here is what already exists.

`InfoBanner` (`apps/frontend/src/rework/components/shared/molecules/InfoBanner/`)
already solves the hard parts of the presentation: full-width strip mounted at
the app root inside `.appShell`, pushing `.appContent` down instead of
overlaying it; a 300 ms eased collapse whose DOM removal is driven by a
fixed timeout rather than `transitionend`, because under
`prefers-reduced-motion` the transition never fires an end event; localized
text resolved through `resolveLocalizedText`. Its content comes from
`getInfoBanner()` in `common/config.tsx`, which reads the public pre-auth
`/control-plane/v1/frontend/config` payload loaded once before React renders.

On the backend, `platform_prompt/` is the closest existing shape for an
admin-authored, DB-persisted platform setting: a four-file module
(`api.py` / `schemas.py` / `service.py` / `store.py`) where the store does pure
CRUD and never checks authorization, and the service owns the ReBAC gate. It is
a singleton; announcements are a collection, which is the one structural
difference.

`ProseMdxEditor` (`shared/organisms/ProseMdxEditor/`) exports
`proseMdxPlugins()` and `ProseToolbarButtons()` — a shared MDXEditor plugin list
and toolbar row, already consumed by the team wiki. Each caller still owns its
own `<MDXEditor>` instance. `MarkdownRenderer` handles the read side, and
`Dialog` (`shared/molecules/Dialog/`) is the central dialog molecule.

## Goals / Non-Goals

**Goals:**

- One way to put a banner on screen, with the deploy-time path removed rather
  than left alongside.
- Reuse the existing banner presentation, markdown editor, markdown renderer
  and dialog rather than growing parallel ones.
- A data model that scheduling can be added to without reshaping it.

**Non-Goals:**

- Scheduling (start/end dates) — the next change.
- Per-team or per-role targeting. Announcements go to everyone.
- Server-side dismissal state, read receipts, or any per-user announcement
  record.
- Rich media in announcements. Markdown text, no images or embeds.

## Decisions

### Store dismissals in `localStorage`, keyed by id + content version

**Why:** the control-plane has no user-preferences store at all — a server-side
dismissal would mean a new table, a new endpoint, a write on every close, and a
GDPR purge path, for a preference whose worst failure mode is a banner
reappearing. Keying on `content_version` rather than id alone is what makes an
edited announcement reach people who dismissed the previous wording, which is
the behaviour operators actually want when they fix a typo or change a date.

**Alternative considered:** a `announcement_dismissals` table keyed by user. It
follows the user across devices, which is genuinely better. Rejected for this
slice on cost, not on principle — the model does not preclude adding it later,
since the client would simply stop consulting `localStorage`.

**Accepted consequence:** dismissals are per-browser and are lost when site
data is cleared. Every read and write is wrapped so that unavailable storage
(private window, blocked site data) degrades to "never dismissed" rather than
throwing.

### Poll every 60 s with a refetch on focus, rather than open an SSE channel

**Why:** the control-plane has exactly one SSE route today
(`tasks/api.py`), and this deployment has already hit the browser's ~6
concurrent-connection ceiling when task streams were left open. A second
always-on stream per tab, to deliver a payload that changes a few times a
month, is the wrong trade. RTK Query gives both the interval and the
focus-refetch declaratively (`pollingInterval`, `refetchOnFocus`).

**Alternative considered:** piggybacking announcements onto the task SSE
stream. Rejected — it couples an admin-content concern to the task lifecycle
and would deliver nothing to a user with no tasks running.

### Version the content with a monotonic integer, bumped in the service

**Why:** an `updated_at` timestamp would also work as a cache key, but it
changes on any write including a pure `enabled` toggle, which would
resurrect banners every time an admin flicks a switch. A counter bumped only
when content-bearing fields actually change keeps "the announcement changed"
distinct from "the announcement was toggled". The service compares incoming
fields against the stored row and bumps only on a real difference.

### Sort by severity then creation date, with no cap on the stack

**Why:** an operator enabling an `error` banner during an incident needs it
above a week-old `info` banner. Ordering is computed client-side from the
delivered set — the server returns the set, not a presentation order.

No hard cap: truncating silently would hide exactly the announcement someone
took care to publish, and "N more" affordances at the top of the viewport are
their own usability problem. Operators control the count; the admin page makes
the enabled count visible so it is hard to forget one.

### Reduced editor toolbar for `description_short`

`description_short` sits in a constrained strip. It gets a locally composed
toolbar — undo/redo, bold/italic, link — instead of `ProseToolbarButtons()`,
whose block-type select, lists and table insert would let an admin author
markdown that cannot render in a banner. `description_long` uses the shared
prose set unchanged. Both reuse `proseMdxPlugins()`; the difference is only
which buttons are offered.

### Move the banner stack inside the guards

`InfoBanner` renders above `GcuGuard` in `app/App.tsx` precisely so it shows
pre-auth. Announcements are authenticated content, so the stack moves into the
authenticated subtree. This is the behavioural regression named in the
proposal: a maintenance notice can no longer reach someone stuck at the login
or terms screen. Accepted because serving admin-authored DB content on a public
unauthenticated endpoint is the larger problem.

### Gate on `CAN_MANAGE_PLATFORM`

Administration uses the catch-all platform gate, matching the other
admin-only surfaces (`main.py`'s import/export, tasks and platform reset).
`organization_authz.py` deliberately keeps no helper for the catch-all — the
named helpers exist so delegated surfaces cannot reuse it — so the service
calls `rebac.check_user_permission_or_raise` directly, as those routes do. The
frontend route guard uses `requires="admin"`, which resolves to the same
authority. The read route is gated by authentication only.

## Risks / Trade-offs

- **Removing `info_banner` silently drops a live banner on upgrade.** →
  Called out as BREAKING in the proposal, and the migration note tells
  operators to recreate it from the admin page. No automatic data migration:
  the Helm value lives in a values file the control-plane cannot rewrite, and
  seeding a row from it would leave a transitional code path to delete later.
- **An admin can stack enough banners to bury the app.** → Ordering and the
  absence of a cap are deliberate; the admin page shows the enabled count so
  the state is visible. Revisit with scheduling, which naturally limits how
  long a banner lingers.
- **Markdown authored by an admin is rendered into every user's page.** →
  Only `CAN_MANAGE_PLATFORM` holders can write it, and it goes through the same
  `MarkdownRenderer` (with `rehype-sanitize`) as every other markdown surface.
  No raw HTML passthrough is enabled for these fields.
- **60 s polling adds a request per tab per minute.** → The payload is small
  and the query is cached by RTK Query; the endpoint reads one indexed table.
  Worth re-measuring if the enabled set ever grows large.
- **`content_version` bumping is service logic, so a careless later edit could
  bump on toggle.** → Covered by a test asserting that toggling `enabled`
  leaves the version unchanged while editing text changes it.

## Migration Plan

1. Ship the backend module, the Alembic revision and the read route first —
   nothing renders yet.
2. Ship the admin page and the banner stack; remove `info_banner` from the
   frontend config accessor in the same change so no window exists where both
   banners can render.
3. Remove the `info_banner` Pydantic model, the `/frontend/config` field, the
   Helm values block and the configuration samples.

The Alembic revision is additive (one new table) and must be re-parented onto
the current `swift` head at merge time so the control-plane tree keeps exactly
one head. Rollback is a downgrade dropping the table; operators who had an
`info_banner` and roll back recover it by restoring the Helm value.
