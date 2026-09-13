## Context

Knowledge Flow already ingests documents, and does it well for the case it was
built for: a person picking files in a browser. The first Knowledge Base written
against that API worked, and its failures were instructive rather than
theoretical — they are recorded in the proposal, each measured against a pod that
ran.

This change adds a second surface for the other case. It is not a correction of
the first.

## Goals / Non-Goals

**Goals:**

- A synchronizing caller never learns, stores or returns a Fred-side document
  identifier.
- A caller's source does the versioning; Fred remembers where the caller was.
- Removal is addressed by the same name used to write, and touches no library
  metadata.
- A machine write is recorded as a machine write.

**Non-Goals:**

- Changing the existing ingestion surface or its per-upload versioning.
- The inventory-and-diff exchange (see decision 4).
- Interpreting a source key or a version.
- Anything about what a document becomes after it is stored.

## Decisions

### 1. Identity is the source's, and it is looked up rather than derived

A document is addressed by `(library, source key)`. The source key is the
caller's — for most sources the path relative to the library — and it is unique
within its library, enforced in the database.

Writing a key already held updates that document rather than creating a second.
That is the whole point: a source has one version of a file, and a library that
mirrors it should hold one document for it.

**The document's own identifier is not derived from the key.** An earlier draft
derived it, which bought a scheme to design, a collision question to answer
against the identifiers already stored, and a coexistence story to test. Storing
the key and looking the pair up buys none of that: a document keeps the opaque
identifier it was given, reused on update instead of regenerated, and the
existing per-upload scheme is untouched rather than avoided.

A document stored without a source key is therefore never matched by one. A
library is written by one caller in practice — a synchronized folder offers no
deposit action — so this is a property that holds by construction rather than a
case to manage.

*Why not keep the per-upload identity and have the caller clean up:* the caller
would have to publish the new document, then retract the old one, keeping the
old identifier in its own records to do so — two calls, not atomic, with a window
where both exist and a leak whenever the second fails. The first Knowledge Base
did exactly this and leaked. The defect is in the shape, not in the caller.

### 2. Two versions, both opaque, both optional

**A document version** — an etag, a content hash, a revision number — travels
with each document. Fred stores it, returns it, and compares it only for
equality.

**A source version** — a commit sha, a cursor, a timestamp the source
understands — belongs to the library as a whole. Fred stores the last one a
caller declared and hands it back on request.

Neither is parsed. A caller that has neither still works: it sends documents and
Fred keeps them, exactly as before.

*Why the second one earns its place:* it is what lets a pull-mode Knowledge Base
be driven by its own source instead of by a ledger it maintains. A pod mirroring
a Git branch asks Fred what it last accepted, asks Git what changed since, and
sends that. `git diff` is better at this than anything Fred or an SDK would
re-implement, and it is free. A source without versioning loses nothing — it uses
document versions alone.

### 3. Removal is addressed, never inferred, and never touches the library

A caller removes a document by the source key it wrote. It does not read the
library, does not rewrite the library's item list, and does not echo back the
library's name, path, description or type.

*Why this matters more than it looks:* the only removal available today requires
a caller to write the library's own metadata back. A caller that gets one field
wrong renames the user's folder, and two callers racing lose each other's work.
Neither hazard is acceptable for something that runs unattended on a schedule.

Fred still infers nothing from absence: a document disappears because a caller
said so, never because a caller failed to mention it.

### 4. The inventory exchange waits

The shape that removes a caller's last bookkeeping is an exchange: the caller
offers every `(key, version)` it has, and Fred replies which it wants bytes for
and which it will drop. It is rsync's model and it is the right end state — a
caller would then keep nothing between runs at all.

It is deliberately not built here. Decisions 1 to 3 already remove the identifier
bookkeeping, which is the part that was causing defects; what remains on the
caller's side is its own content hashes, which cost it little. The exchange is
purely additive on top of this surface, and it should be designed once a real
Knowledge Base has shown what its bookkeeping actually costs rather than from a
guess about it.

### 5. A machine write is recorded as a machine write

Writes through this surface are attributed to a service identity. The existing
ingestion surface attributes every write to a person, which is correct for it and
wrong here.

*Why it is worth naming as a decision:* the platform's KPI actor model offers
`human` and `system` only, and the audit model already distinguishes a human user
from a service identity. This surface must not widen the gap by recording
scheduled machine traffic as human activity, which would make any split of the
two wrong by exactly the synchronized volume.

### 6. Authorization is the library's, and nothing broader

Writing or removing requires permission to write in the target library. Folders
created along a document's path are authorized by permission on their parent, so
one grant over a library reaches its whole subtree and no further.

A caller holding a broad service role and no grant over a library SHALL be
refused. Reaching Fred at all and being allowed to write into one library are
two different permissions, and this surface keeps them apart.

## Risks / Trade-offs

**Two ingestion surfaces to keep coherent.** → Accepted deliberately: the two
model different things, and collapsing them is what produced the duplicate
documents in the first place. They share the storage and processing beneath them;
only the entry shape differs.

**A caller can choose a poor source key.** → Accepted and bounded: the key is the
caller's vocabulary by design, and a caller that changes its own key scheme
orphans its documents in its own library. Bounds on length and characters are
enforced; meaning is not.

**A deterministic identity means a caller can overwrite its own document.** →
That is the intent, and it is confined to the caller's own library by decision 6.

## Open Questions

1. **How is a document version compared when the caller sends none?** Writing
   unconditionally is the simple answer and the one assumed here; whether Fred
   should instead fall back to hashing the content it received is a cost question
   nobody has measured yet.
