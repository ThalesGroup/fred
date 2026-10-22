# RFC — In-app notifications

**Status:** Slices 1 and 2 are settled and built; slice 3, catalogue items
7–9 and the delivery guarantee of §5 remain open. GitHub issue #3232. The current truth lives in the
OpenSpec changes `add-in-app-notifications` (framework, bell, marketplace
types, platform switch) and `add-team-join-requests` (`on_request` mode, join
request types, not-a-member screen), and in
`CONTROL-PLANE-PRODUCT-CONTRACT.md` §69 and §70.

## 1. Problem left open

Quota boosts (#3223) are granted by admins, with no way for a user to ask.
The owner decided (2026-10-22) that a boost request goes to the admins of every
non-personal team the requester belongs to, with no platform admin fallback
since every team has an admin; the first grant or decline resolves it for all,
matching #3223's "once per user per week across all teams". Three more
notifications wait for something else to exist first.

## 2. Catalogue still open

Legend: AR = action required, R = answer to your request, I = information.

| # | Notification | Trigger | Recipients | Cat. | Buttons | Group / handled | Exists |
|---|---|---|---|---|---|---|---|
| 5 | X asks for a quota boost | "Request a boost" in the quota tooltip (#3223 slice c) | admins of the requester's teams (§1) | AR | Grant +20%, Decline | `boost_request:<user>:<week>`; resolved by grant/decline | No: after #3223 |
| 6 | Your boost request was granted / declined | decision on 5 | requester | R | none | `boost_outcome:<id>` | No: after #3223 |
| 7 | Your weekly quota is at 80% / exhausted | #3223 spend counters | the user | I | none | one per window | No: after #3223; the composer indicator already warns in context |
| 8 | An agent finished a turn while you were away | turn end | the user | I | Open the conversation | per session | No: a turn ends with its browser connection (`agent_app.py` "a closed connection ends the run") |
| 9 | Your agent is waiting for your answer (HITL) | runtime `AWAITING_HUMAN` | the user | AR | Open the conversation | per interrupt | No: control-plane is never told |

5 and 6 are slice 3. 7 is decided after slice 3 lands. 8 and 9 wait for turns
that can outlive the connection.

## 3. Slice 3: quota boost requests

After #3223 slices (b) and (c): types 5 and 6 on the existing framework (one
row per recipient, `group_key`, `resolve`, `call` buttons on the domain
endpoint, the payload class's `PERMISSION` set to the team admin right). It gets its own
OpenSpec change; once scoped, this RFC has nothing left open and is archived.

## 4. Alternatives considered (kept for slice 3)

- **Per-user SSE stream.** Instant, but one held connection per tab and a
  `LISTEN` connection per subscriber in the current bus. Rejected for v1.
- **Reuse the announcements tables.** Announcements are broadcast with one
  high-water mark per user; per-recipient rows, actions and handled state
  would bend that model past recognition.
- **Reuse task acknowledgement.** Tasks are work the user started, owned by
  the backend that runs it; notifications are addressed by someone else.
- **Store rendered text.** Freezes the locale at creation and blocks wording
  fixes. Rejected; ids plus a display snapshot instead.
- **Generic action endpoint** (`POST /notifications/{id}/actions/{name}`).
  Duplicates domain authorization in a second place. Rejected.
- **Outbox and worker for emission.** Durable, but every v1 trigger is in
  control-plane and best effort is acceptable for a notification.

## 5. Open question: notifications that represent work

Today every producer calls `notify` after its own commit, best effort: a
failure is logged and counted, and the notification is lost. That is fine for
information and for join requests, whose Members tab still lists the request.
It is not for a notification that is the only place some work surfaces:
workflow approvals, HITL (item 9), quota boost requests (item 5). Losing one
silently leaves the work waiting with nobody told.

Alternatives:

- **Insert in the producer's transaction.** `upsert` accepts an optional
  session, so the notification commits or rolls back with the domain write.
  Simple, but couples the producer's transaction to the notification tables
  and still needs recipients resolved (ReBAC) inside it.
- **Outbox.** The producer writes an outbox row in its transaction; a worker
  turns it into notifications and retries. Durable and decoupled, at the cost
  of a worker and a delay.
- **Keep best effort**, and make each such domain list its pending work on its
  own page so the notification is only a shortcut, as join requests do.

To decide before the first type that represents work ships (slice 3).
