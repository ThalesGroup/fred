## Context

See proposal.md. Today `api::require`, `spaces::require_context` (+ `authorized_write`)
and `documents::authorized` each call `spaces::organization`, which reads all of the
caller's direct roles and the placement of each space, then a Check.

## Goals / Non-Goals

**Goals:** one helper, one Check per authorization decision, uniform status codes.

**Non-Goals:** caching, changing write-time attachment checks (`may_attach`), lock
timeouts on governance routes, agent-facing probe semantics beyond status codes.

## Decisions

- **Single helper** `authorize(pool, fga, user, permission, space) -> Space`: active
  space + placement, one Check, `Forbidden` on false, `Unavailable` (503) on dependency
  error. Mutations call it under the organization lock after the guard capture, then
  fence, preserving I5. Alternative (keep context as defense in depth) rejected by the
  developer: uniqueness is enforced at write time and the cost grows with roles.
- **Kept resolution:** `may_attach` (grant, import, org creation) and `/me/spaces`.
  `create_space` and personal-space creation drop their caller/admin context checks:
  the nominated admin's direct parent role and the Checks already bind the organization.
- **Probes** return `allowed: false` when the target is missing or foreign.
- **Folder parent** outside the space: 404, matching listing filters (replaces 400).

## Risks / Trade-offs

- [Corrupt data giving one person roles in two organizations] → no longer blocked
  per request; each Check still only grants what that person's tuples grant, and
  `/me/spaces` reports the contradiction for repair.
