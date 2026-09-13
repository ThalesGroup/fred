# Tasks

Nothing here changes the existing ingestion endpoints. If a task seems to
require it, that is a signal to stop and ask rather than to proceed: the two
surfaces model different things on purpose, and both are meant to keep working.

## 1. Storage of source identity and versions

- [ ] 1.1 Add the source key and document version to a document's stored metadata, and the source version to a library, with their Alembic migration. Bound the key's length and character set and store it uninterpreted. Verify with tests that a key round-trips unchanged including characters that are not path-safe, that two libraries may hold the same key independently, and that a document written without a version is valid
- [ ] 1.2 Make a source key unique within its library, enforced in the database, and resolve a write by looking that pair up: update the document already there, or create one. Do NOT derive an identity from the key — a document keeps the opaque identifier it was given, reused on update instead of regenerated, so the existing per-upload identity scheme is untouched and no collision question arises. Verify with tests that writing the same key twice leaves exactly one document carrying the later content and the same identifier, that the same key in two libraries stays two documents, and that a document holding no source key is never matched by one

## 2. The synchronizing surface

- [ ] 2.1 Add the write endpoint: a document's bytes, its path within the library, its source key and its optional version, returning an outcome rather than a progress stream. Report failure with bounded, sanitized error information and leave no partial document behind. Verify with tests for a create, an update through the same key, a write with no version, and a failure that leaves the library unchanged
- [ ] 2.2 Add the removal endpoint, addressed by source key, touching none of the library's own properties and succeeding on a key the library does not hold. Verify with tests that the library's name, description and other documents are untouched, that removing an absent key is not an error, and that a document never disappears merely because a caller stopped mentioning it
- [ ] 2.3 Add reading and recording a library's source version, stored and returned exactly as given. Verify with tests that an unordered, non-numeric, undated value round-trips unchanged and that a library that has never recorded one reports its absence rather than an error
- [ ] 2.4 Authorize every operation on permission over the target library, refusing a caller that holds only a broad service role. Reuse the platform's existing authorization rather than adding a check of its own. Verify with tests that a service role alone is refused, that permission over the library is sufficient, and that permission over one library authorizes nothing in another
- [ ] 2.5 Refuse a path that would place a document outside its target library, creating nothing. Verify with tests covering traversal, absolute paths, and any encoding of either that reaches the handler

## 3. Attribution

- [ ] 3.1 Attribute a write through this surface to the service identity that made it rather than to a person. The platform's KPI actor model offers `human` and `system` only, so record what is true rather than widening the gap — and if expressing it needs the shared actor model to grow, say so in the close-out rather than mislabelling the traffic. Verify with a test that a write by a service identity is not recorded as human activity

## 4. Contract and client

- [ ] 4.1 Regenerate the frontend API client with the documented make target and commit the regenerated file alongside the backend change, per the repository rule. Nothing in the frontend consumes this surface yet; the client is regenerated because the spec changed

## 5. Quality gate

- [ ] 5.1 Run `make code-quality` from the monorepo root and fix everything it reports
- [ ] 5.2 Run `make test` from the monorepo root and confirm the new tests pass with no regression elsewhere — in particular that every existing ingestion test still passes untouched
- [ ] 5.3 Run `/code-review` on the diff before reporting done, per the repository's Step 5 rule
