## Why

A person who finds a public team can join it only if it is `open`; otherwise they must find an admin outside the platform. In-app notifications (`add-in-app-notifications`) can now route a request to the team's admins. GitHub issue #3232.

## What Changes

- Opt-in access mode `on_request` for public teams; no team changes mode on upgrade.
- Ask to join from the team card, with an optional message; cancel while pending.
- Admins accept or refuse from a notification or from a Requests tab in Members; "Accept anyway" for 7 days after a refusal.
- The requester gets the answer as a notification.
- A not-a-member screen on team pages, with "Ask to join" when possible.
- Notification tiles that ask for a decision: no close button, kept by "Clear all", buttons calling the domain endpoint.

## Capabilities

### New Capabilities

- `team-join-requests`: the `on_request` mode and the join request lifecycle.

### Modified Capabilities

- `notifications`: two join request types and decision tiles.

## Impact

Control-plane `teams/join_requests.py`, `teams/join_request_store.py`, routes in `teams/api.py`, `JoiningMode.ON_REQUEST` (fred-core), Alembic revision `fd4dc8d9d058`; regenerated client; `TeamCard`, `TeamMemberGate`, Members/Requests tabs, `JoinRequestDialog`; Help Center fr+en.
