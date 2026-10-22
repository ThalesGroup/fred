## Why

A person who finds a public team in the Teams marketplace can join it only if its admins chose `open`; for every other team the card reads "Invite only" and the person has to find an admin outside Fred. `request_only` once filled that gap but was removed (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §29) because nothing could route the request to the admins. Slice 1 of in-app notifications (`add-in-app-notifications`) now can.

Tracking: GitHub issue #3232. Design and catalogue: `docs/swift/rfc/NOTIFICATIONS-RFC.md` (this change is its slice 2, catalogue types 3 and 4). Same branch and PR as slice 1.

## What Changes

- **New opt-in access mode `on_request`** ("On request"), next to `open` and `invite_only`, chosen by a team admin in Team settings > Parameters. Like `open`, it exists only for public teams; making a team private turns it back into `invite_only`. Teams keep their current mode: nobody receives requests until an admin picks it.
- **Join request record.** At most one request per person and team. A pending request expires after 30 days. A refused one stays 7 days after the refusal; its requester may ask again once 24 hours have passed, and the new request replaces it. An accepted or cancelled one is deleted.
- **Requester side, on the existing team card** (Teams marketplace, "Other teams"): "Ask to join" opens a dialog with an optional short message (at most 280 characters, shown to admins only); the card then reads "Request sent" with "Cancel request"; after a refusal it reads "Request declined" until the requester may ask again.
- **Admin side:** notification "X asks to join <team>" with **Refuse** (left) and **Accept** (right), sent to every holder of `can_administer_members` on the team. The first decision resolves it for the other admins ("Handled by <name>"). The Members tab shows a "Pending requests" section with the pending requests (Accept, Refuse) and the requests refused in the last 7 days (**Accept anyway**, which grants `team_member` and tells the requester they were accepted).
- **Leaving the mode refuses what is pending:** when a team leaves `on_request` or becomes private, every pending request is refused automatically and each requester gets the refusal notification; this automatic refusal imposes no 24-hour wait and offers no "Accept anyway".
- **Answer to the requester:** "Your request to join <team> was accepted" (button "Open the team") or "... was refused". It needs no team permission; an acceptance carries the team, so leaving or deleting it removes the tile, a refusal carries none.
- **Accept grants `team_member`** to the requester, nothing else, and only while the team takes requests. Becoming a member any other way closes the request.
- **Not-a-member screen** on any team page opened by a non-member (platform admins included), UI only; server-side enforcement is #3260.
- **Endpoints:** create, cancel, list mine, list a team's pending and recently refused requests, accept (also accepts a refused request: "Accept anyway"), refuse.
- **Importer:** a legacy `request_only` still imports as `invite_only` (it was the default of every team, not an admin's choice); `on_request` imports as is.
- **Help Center** fr+en, migration note of the PR updated, contract entries.

Out of scope: requests to private teams, email, a per-user rate limit beyond one request per team and the 24-hour wait after a refusal, quota boost requests (slice 3).

## Capabilities

### New Capabilities

- `team-join-requests`: the `on_request` access mode, the join request lifecycle (ask, cancel, accept, refuse, accept anyway, automatic refusal on a mode change, expiry) and its requester and admin surfaces.

### Modified Capabilities

- `notifications` (introduced by the in-flight `add-in-app-notifications`): two new types, `team.join_requested` and `team.join_request_answered`, and types addressed outside a team carry no action permission.

## Impact

- Backend (control-plane): `JoiningMode.ON_REQUEST` in `fred_core/teams/metadata_store.py`; new `teams/join_requests.py` (service) and `models/team_join_request_models.py`; routes in `teams/api.py`; `update_team` downgrade rule and automatic refusal; `delete_team` and `delete_user` cleanup; expiry in the lifecycle notification step; `notifications/schemas.py` (`PERMISSION = None` on the answer type); importer comment and mapping; the Alembic revision `83b81adf7450` shared with slice 1; `authz-endpoint-matrix.yaml`.
- Frontend: regenerated `controlPlaneOpenApi.ts`, aliases in `controlPlaneApiEnhancements.ts`; `TeamCard`, `MarketplaceTeams`, `TeamSettingsParameters`, `TeamSettingsMembers` (pending section), `notificationTypes.ts`; fr+en strings; Help Center fr+en.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` dated entry (and a pointer from §29), `COMPONENT-UX.md`, `NOTIFICATIONS-RFC.md` slice plan, migration note `3232-add-in-app-notifications.md` (still minor).
