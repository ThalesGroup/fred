## 1. Backend

- [x] 1.1 `JoiningMode.ON_REQUEST`, `team_join_requests` table, revision `fd4dc8d9d058`
- [x] 1.2 Ask, cancel, list, accept, refuse routes; authz matrix entries
- [x] 1.3 Join request notification types and decision support
- [x] 1.4 Automatic refusal on leaving the mode; membership hook closes requests
- [x] 1.5 Expiry and cleanup on user and team deletion

## 2. Frontend

- [x] 2.1 Regenerated client, cache tags and aliases
- [x] 2.2 Team card states, `JoinRequestDialog`, Parameters mode
- [x] 2.3 Members and Requests tabs
- [x] 2.4 Decision tiles in the bell; `TeamMemberGate`
- [x] 2.5 Help Center fr+en

## 3. Verification

- [x] 3.1 `make code-quality`, `make test` (control-plane, fred-core, frontend), `alembic heads` = 1, `alembic upgrade head` on a scratch database
