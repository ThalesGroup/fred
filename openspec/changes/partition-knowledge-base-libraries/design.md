# Design

## Context

See `proposal.md` — Why. Three constraints shape everything below.

**A library is an ordinary folder on purpose.** It is created through
knowledge-flow's own folder endpoint with the acting person's token, so the
team-level right to create a folder is checked against the person asking. That
decision is not reopened here; this change adds what was missing from it, not a
second creation path.

**ReBAC load is a standing concern in this repository.** A guard that resolved
"is this folder machine-written?" through the authorization engine would make a
known weakness worse. Everything below is measured against that.

**A document is tagged into exactly one folder** — its leaf. The delete-folder
count and the folder-size column both already rely on that invariant, so nothing
here may break it.

## Goals / Non-Goals

**Goals:**

- A person and a machine can never write into the same corpus folder.
- The guard adds no authorization-engine traffic on any path.
- An unmarked folder behaves byte-for-byte as it does today.

**Non-Goals:**

- Per-instance identity for a Knowledge Base pod (Decision 8).
- Correcting how a machine write is attributed in KPIs and logs.
- Any change to the existing ingestion surface a person uploads through.

## Decisions

### 1. The mark is a column on the folder, not something derived

The question "may this person write here?" has to be answered at the mutation
site, cheaply, inside the transaction, by the component that owns folders. A
stored column is the only option satisfying all three.

Alternatives considered:

- **Ask the authorization engine** which service account holds a grant on this
  folder. This is the reverse-lookup direction, the expensive one, on a weakness
  we are trying not to worsen.
- **Ask the control-plane.** A network hop inside an authorization decision.
- **Infer it from the documents present.** An empty folder — exactly the window
  in which a freshly created library is most exposed — would be unguarded.
- **A reserved path namespace.** Permissions inherit through the folder chain,
  so an extra level costs a resolution hop on every nested folder, and the
  reserved root would collide with folders people name themselves.

The cost is knowledge-flow storing a reference to a concept it does not own. The
precedent sits immediately above it in the same model: a library already stores
its source's version opaquely, handed back and never interpreted.

**No schema migration is involved.** A folder is persisted as a JSON document
alongside a handful of mirrored, indexed columns, and only those mirrored
columns are part of the table's shape. The mark is not queried by — the guard
reaches it by resolving a folder's root and reading that folder — so it belongs
in the document with the source version, not in a column of its own. A folder
written before this change carries no such key, which reads back as absent,
which is exactly "written by people".

### 2. Only the root carries the mark; nesting is derived

A folder nested under a library resolves its state by looking up its root
ancestor, rather than carrying a copy.

Strictly less state, no propagation to keep in step, no subfolder that can drift
out of agreement with its library, and folders created before this change are
covered without a data migration of their own.

The cost is one read to reach the folder and a second, on an already-indexed pair
of columns, to reach its root — and only on a **human** mutation, which is
interactive and rare. The second is not paid when the folder being mutated is
itself a library's root, and neither is paid on the synchronization path, which
is recognized by identity before any folder is read.

### 3. The value is a qualified owner reference, not a bare instance id

Stored as `<kind>:<id>`, matching the type-and-id vocabulary the authorization
references already use.

The axis this column grows along is not "more kinds of Knowledge Base" — it is
**more kinds of machine writer**: a platform import, an agent mirroring a source,
a future connector that is not a Knowledge Base at all. Each will want this exact
guard. Qualifying the value now means the guard is never re-modelled when the
second one arrives, and it costs one string today.

knowledge-flow does not parse it. It tests for presence.

### 4. The pod marks its own library, at the start of each run

Only a service identity may write the mark. That is what makes the guard airtight
by construction rather than by convention: no person can mark a folder, so no
person can lock themselves out of one, and no person can dress an ordinary folder
as a synchronized one.

**The control-plane cannot be the one to write it.** Marking requires the right
to write in that library, and the only grant creating an instance produces is the
*pod's*. The control-plane's own service account holds nothing over the folder,
and the permission check has no administrative branch to waive that. It has no
business there either: on Knowledge Bases the control-plane carries enablement,
instances and dispatch to the UI, and nothing that writes into the corpus.

So the entity that fills the folder is the entity that declares it filled. The
pod already holds the grant, is already a service identity, and already knows its
own instance — and it can only ever mark a library it was granted, a constraint
the existing permission check enforces without a rule being added for it.

This is why the recording endpoint is idempotent: it is sent once per run, and
every run after the first finds the library already marked and changes nothing. A
run that cannot record it logs and proceeds — a base that stopped synchronizing
because it could not write a marker would be a worse failure than a library that
stays open a little longer, and the next run repairs it.

The cost is a window: between an instance being created and its first successful
run, the folder is an ordinary one. What that exposes is a stray upload into an
empty folder, or a rename — both by the person who just created it. Deleting it
is *not* window-specific, being permitted throughout by Decision 6. Closing the
window would cost either a standing grant for the control-plane, a transient one
around every creation, or deployment configuration naming a client trusted to
mark anything — a ReBAC cost, a ReBAC cost, and a new trust model respectively.

A pod that keeps its own store never reaches this: the declaration is sent only
when the pod is configured with a Knowledge Flow URL, which is the same condition
that decides whether it writes documents into Fred at all.

### 5. The guard adds no authorization-engine call

Two properties make this true, and both were verified rather than assumed:

- Recognizing a service identity reads the token's roles. It is not an
  authorization-engine check, and says so in its own contract.
- Every site the guard is added to already performs an authorization check on the
  target folder immediately before. The guard is placed after that check and
  reuses the decision; it never triggers a second one.

The mark also travels inside the folder payload the frontend already fetches, so
displaying the badge and hiding the actions costs no request.

Net: zero added on every read path and every hot path; one added per Knowledge
Base instance creation, from Decision 4.

### 6. Content is guarded; existence is not

A person may not change what a machine-written folder holds or what it is called,
but may still delete it.

Forbidding deletion would break deleting the base itself, which removes the
library with the person's own token precisely because that is where the right to
delete anything at all is checked — and knowledge-flow cannot tell "deleted from
the base's page" from "deleted from Resources".

The alternative is a dedicated permission probe, letting the control-plane check
the person's right and then delete as a service identity. It adds an endpoint and
authorization-engine traffic, against Decision 5. Rejected for now; the asymmetry
is stated in the spec so it reads as chosen rather than overlooked.

The consequence — an instance left pointing at a deleted library — is better
answered on the instance's own side, where it also covers a library that
disappeared for any other reason. Out of scope here.

### 7. Nested documents are listed with two indexed reads, not a walk

Resolving a library's descendant folders is one prefix read on the tag store;
listing documents across that set is one read on the document store, extending
the existing single-folder read to take a set rather than introducing a new
concept. Because a document belongs to exactly one folder, a set read cannot
double-count, and the total counts the same set that can be paged through.

A single joined query would be fewer round trips, but the tag store and the
document store are deliberately separate components; joining them in SQL would
couple them in a way nothing else does.

Doing the walk in the frontend — as the Resources folder-count does — was
rejected: it costs one request per folder, and it puts a rule that belongs to the
corpus into one of its readers.

### 8. Cross-team isolation rests on the dispatched library id — entered, not a defect

There is no per-instance identity. One service account per contributor prefix
holds a write grant over every library of every team that instantiated any of its
definitions. What prevents a run dispatched for one team from writing into
another team's library is that Fred hands the run its own library id and the pod
uses it — a property of the pod's code, not of authorization.

**This is an entered decision, not an oversight.** It is recorded here because
the next reader will assume the opposite and may file it as a bug. Changing it —
one identity per instance — touches publication, the identity provider and
deployment, and needs its own RFC.

### 9. A requirement that is not true yet

The unarchived `knowledge-base-ingestion-facade` change carries a requirement
stating that a synchronizing write is recorded as a machine write. It is not:
attribution has only "human" and "system", and a machine write carries a subject,
so it is recorded as human.

That change is otherwise complete and would normally be archived. **It should not
be archived as it stands**, or a false requirement is folded into the current
spec. Either the attribution is fixed first, or the requirement is corrected to
say what actually happens. Tracked separately from this change.

## Risks / Trade-offs

**Libraries created before this change stay unmarked, so unguarded** → The
control-plane knows every library id it ever created; a one-shot marking pass
covers them. The population is small — the feature is recent — and an unmarked
folder behaves exactly as today, so a missed one is a gap, never a breakage.

**The mark is written after the grant, and writing it earlier silently fails** →
Covered by an explicit task and a test that asserts the order, rather than by a
comment.

**A wide library makes the descendant folder set large** → Both reads are on
indexed columns and the listing stays paged as it is today. Depth is already
capped by the folder model; breadth is not, so this is measured on a
tree-mirroring library rather than assumed.

**The guard is added at several sites, and a site missed is a hole** → The sites
are enumerated in `tasks.md`, each with its own test asserting a person is
refused and the machine is not. A site with no test is treated as not done.

## Migration Plan

Nothing to migrate: the mark is an additional optional key in the JSON document a
folder is already stored as, so no table changes shape and no Alembic revision is
added. Every folder that exists today reads back without the key, which the model
resolves to absent, which is today's behaviour.

Rollback is removing the field: absent is unguarded, so a rollback degrades to
today's behaviour rather than locking anyone out of a folder. No data is
stranded — a leftover key in a stored document is ignored by a model that no
longer declares it.

Order of deployment: backend, then the marking step in instance creation, then
the backfill pass, then the frontend. The frontend last because hiding actions
the backend still allows is cosmetic, while offering actions the backend refuses
is not.
