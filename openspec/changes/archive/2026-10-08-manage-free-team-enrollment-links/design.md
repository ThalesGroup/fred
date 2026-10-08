## Context

The current team metadata contains one token hash; generation rotates it and removing Free clears it. Admission mutations already serialize against a shared SQL advisory lock, while enrollment retains live ReBAC membership, suspension and legal checks. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:** independent persistent invitations, bounded history, authenticated page opening counters, live revocation/expiry/Free checks across replicas.

**Non-Goals:** message sending/delivery tracking, anonymous analytics, unique-person analytics, automatic removal of existing members on link revocation, deployment configuration.

## Decisions

- Replace the single team hash with link records (UUID, owning team, SHA-256 token hash, recoverable token, creator/time, optional 512-character note, optional timezone-aware expiry, revocation time, opening count/last opening). Team deletion cascades. Generate 256-bit opaque tokens; only creation and an explicit reveal mutation return plaintext under own-human platform-management credentials and no-store headers. Paginated metadata excludes tokens and other people's account values.
- Preserve the existing admin endpoint family. Add paginated link listing, creation metadata, explicit URL recovery and individual revocation under platform management. Creation requires a current non-personal Free team; listing/revocation remains available while Free is disabled.
- Resolve every preview/legal/enrollment against the current link and team in SQL. Removing Free pauses links without mutating their revocation state. Expired/revoked links remain unusable after Free reactivation. Link revocation stops future enrollment; existing membership remains its independent authority and can be removed separately.
- Count an authenticated page arrival through a dedicated own-credential POST, not through GET preview. Keep aggregate count and last-opening time on the link row; no visit table or visit identifiers are stored. The frontend sends one signal per authenticated page mount, including under duplicate React effects. Every accepted POST increments the counter; repeated network submissions can count again. Store no visitor identity, IP or payload. Repeated new page openings count again. Use the existing mutation lock to serialize enrollment/revocation/Free changes; counter mutation does not change the policy revision.
- Extract a focused link-manager dialog from the team table. Use shared controls for note, optional local datetime (converted to UTC), copyable URL output, status/history, revocation and pagination. The UI explicitly labels authenticated openings and suspended links.

## Risks / Trade-offs

- Recovering old URLs requires storing their capability token in SQL: protect the database as credential-bearing storage. Do not reuse an identity-provider secret as an encryption key or add an implicit key that can invalidate links on restart. Only own-human platform administrators can recover tokens; ordinary projections, audit logs and screenshots exclude them. Existing draft hash-only tokens cannot be recovered, although their original URLs remain usable if retained.
- Counts are page openings, not unique people or proof of delivery: label them accordingly and do not claim server-side visit deduplication.
- Revocation races with enrollment: retain the shared SQL mutation boundary and add a real PostgreSQL serialization regression.
- Cross-store membership writes are not one SQL transaction: preserve the existing fail-closed behavior and recheck admission after enrollment; never add permanent user exceptions.

## Migration Plan

Extend the one pending admission migration and table ownership, keeping one linear head for this PR. No released deployment has this draft link schema. Preserve local demo data when reconciling its already-applied draft migration; transfer existing hashes to link records before dropping the obsolete column. Update the existing operator migration note and regenerate OpenAPI/RTK Query from source. Rollback follows the admission feature's existing deployment ordering.
