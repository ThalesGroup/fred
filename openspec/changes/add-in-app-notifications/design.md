## Decisions

1. **One row per recipient, no stored text.** `type` + `payload` (ids plus a display snapshot of names) render through i18n in the viewer's locale.
2. **Rules on the payload class.** Each type is an enum value and one payload class declaring `TYPE` and `PERMISSION` (team permission needed to receive and act on it). The view is a union discriminated by `type`, so the generated client types every payload.
3. **One open row per subject.** `group_key = "<type>:<subject>"`, unique while unhandled; re-emitting only updates the payload and keeps the seen state. `resolve` deletes the actor's row and marks the others handled ("Handled by <name>").
4. **Best effort after commit.** `notify`/`resolve` never fail the triggering action; a failure logs ids and is counted.
5. **Polling, not a stream.** `GET /notifications/summary` every 15 s while the tab is visible; the summary route is skipped by `KPIMiddleware`. A stream can replace it behind the same contract.
6. **Seen by cursor.** Opening the popover marks rows up to the newest one listed, so a later arrival still badges. Tiles have no read state; a dot marks what was unseen at opening.
7. **Only who can act receives it.** `notify` filters recipients by `PERMISSION`; losing the permission (role change, leaving, team deleted) deletes the open rows, so the summary stays one indexed count.
8. **Acting on a tile deletes it.** "View" and navigate buttons delete the row, then follow the link.
9. **Switch per type hides, never deletes.** `disabled_notification_types` holds the types turned off; producers still store, reads skip them. `can_manage_platform`, audited.
10. **Expiry.** `expires_at = created_at + 30 days`, filtered on every read; one bounded delete (1000 rows) per lifecycle tick.

## Risks / Trade-offs

- Up to 15 s badge latency, accepted.
- Entries published before `published_by` existed notify nobody until republished (stated in the Help Center).
