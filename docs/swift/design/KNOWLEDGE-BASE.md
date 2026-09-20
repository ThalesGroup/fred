# Knowledge Base integration

**Status:** current — describes what is shipped.

A Knowledge Base is a document source that fills one corpus folder by itself.
It is written by a third party, in its own repository, published as its own
image, and deployed as a pod on the same cluster as Fred. Fred dispatches it,
lends it an identity, and offers it somewhere to write. Fred holds no code
that knows what WebDAV, git or a filesystem is, and is not meant to.

This document is the design of that integration: what is offered, what is
deliberately refused, and how a pod is authenticated and constrained. It
covers `libs/fred-sdk` (the authoring surface), `apps/knowledge-flow-backend`
(the corpus it writes into), and `apps/control-plane-backend` (publication,
instances, dispatch).

Three working examples live outside this repository, in `fred-samples`:
`knowledge-bases/local-folder`, `knowledge-bases/git-repository` and
`knowledge-bases/webdav`. They are the contract's proof, not illustrations of
it.

---

## 1. The shape

One image publishes one or more **definitions**. A definition is a declaration
— an id, a version, display metadata, and the configuration fields an operator
will fill in — projected to JSON and posted to the Control Plane at deployment
time (`fred_sdk.knowledge_base.entrypoints.publish_knowledge_base`).

A team creates an **instance** of a definition. Creating it creates three
things at once, or none: the library it fills, the grant that lets its pod
write there, and the schedule Fred runs it on.

A **run** is dispatched by Fred through Temporal onto a task queue derived from
the definition id. The pod's worker picks it up, fetches the run context from
the Control Plane, and calls the author's handler.

One image, two commands: `publish` posts the declaration and exits, so it runs
as a deployment hook; `run` serves runs and does not return. Publishing is
never a side effect of running — two writers on one declaration with no
ordering between them is how a rolling upgrade restores a retired definition.

---

## 2. What Fred offers, and what it refuses

Fred offers a Knowledge Base exactly three things:

1. **Being run.** A cadence and a suspend switch. Not a calendar, not time
   zones — the narrow surface is deliberate.
2. **Somewhere to write.** A library, plus a REST surface to write documents
   into it addressed by the caller's own keys. This is an **offer, not a
   contract**: a pod that keeps its own store leaves `knowledge_flow_url` out
   of its configuration and never calls it.
3. **An identity.** The pod's own workload identity, which is what makes both
   of the above safe. See §4.

Fred refuses to offer connector logic. There is no Fred-side notion of a
source, a protocol, a diff, a cursor or a schedule of polls. Every one of those
lives in the third party's repository. The rules in §3 are what keep that
refusal enforceable rather than aspirational.

---

## 3. The decoupling, as rules

These are the load-bearing decisions. Each one exists to stop Fred from
acquiring knowledge about a source.

**A document is addressed by the caller's own key.** `source_key` names the
document inside the library and belongs to the caller alone. Writing the same
key again updates that document in place, for ever — so a source watched over
months leaves one document per file, not one version per run. Fred looks the
key up; it never derives it.

**The source's version is opaque.** An etag, a content hash, a revision — Fred
stores it and returns it, and never parses, orders or dates it. It is what
lets a pull-mode pod be driven by its own source (ask Fred where it got to,
ask the source what changed since) rather than keeping a ledger of its own.

**Silence is not a removal.** Fred never deletes a document because a caller
stopped mentioning it. Removal is addressed explicitly, through the document
boundary. An absence in a source proves a deletion only after a complete,
authoritative inventory — which is exactly what a run's
`reconciliation_complete` flag states — whereas an explicit tombstone stays
actionable during a partial pass.

**The task queue is derived, never configured.** `routing.task_queue_for`
builds it from the definition id using the same fred-pod function the Control
Plane uses, so the dispatching side and the worker cannot disagree by
construction. `scheduler.temporal.task_queue` is ignored on purpose:
configuring it would be the bug, because two sides disagreeing loses every run
in silence.

**The library is handed over, never named.** `library_id` arrives in the run
context. A pod that could name its own destination could name somebody else's.

**The machine marker is opaque.** `synchronized_by` is a qualified reference,
`knowledge_base:<instance-id>`. Fred acts on its presence and never on what it
names. Nothing downstream depends on its spelling.

**A pod publishes only under a prefix it owns.** The first publication claims
the dotted prefix for the calling client; every later one must present the same
client. Enforced in the store by a row whose primary key is the prefix, so the
claim cannot race.

---

## 4. Identity and authorization

A Knowledge Base pod authenticates as its own confidential Keycloak client,
machine-to-machine. The configuration **names** the secret and never carries
it: `security.m2m.secret_env_var` says which environment variable holds it, and
the token provider reads that variable itself.

Three gates stand between a pod and the corpus:

| Gate | Where | What it requires |
| --- | --- | --- |
| Publication | Control Plane | A service identity (a user session is refused), and the declaration's id under a prefix bound to that client |
| Grant | Control Plane, at instance creation | One OpenFGA relation: this definition's subject may write in **this one library**. Torn down when the instance is deleted |
| Every write | knowledge-flow | A service identity **and** a real ReBAC `tag.update` check on that library |

Both halves of the last gate matter. `require_sync_client` refuses a human
token outright — which is what makes it safe to skip the GCU check a person
would otherwise have to satisfy. The ReBAC check is not bypassed for service
identities: the `service_agent` allowance covers read-only *team* permissions
only and never reaches `TagPermission`. A pod therefore cannot touch a library
it was not granted, whatever role its token carries.

**A pod holds no store credential.** No OpenSearch, no object storage, no
database. It talks REST to knowledge-flow, which does the storing, processing,
permissioning and accounting through the same path a person's upload takes.
An author writes no auth code and holds nothing worth stealing beyond the
client secret.

**The blast radius, stated plainly.** There is one Keycloak client per
*definition*, not per instance. A definition serving twelve teams accumulates
twelve library grants under one identity. Whoever holds that client's secret
can write into every library that definition has ever served, across teams.
Cross-team isolation therefore does not rest on identity — it rests on the pod
choosing the `library_id` its run context gave it. That is an entered decision,
not an oversight; changing it means an identity per instance, which needs its
own design. Read §6 before describing this model as isolated.

---

## 5. Machine-written folders

A library is created through knowledge-flow's ordinary folder endpoint, with
the asking person's own token, deliberately: one set of rules governs every
folder, the same team-level right is required to make one, and the same cascade
takes its documents when it is deleted. A second creation path would be a
second set of rules to keep in step.

The cost of that choice is that nothing distinguished a machine's folder from a
person's. It now does.

**The mark.** The library root carries a nullable `synchronized_by`. Only a
service identity can write it, and the pod writes it — not the Control Plane —
because writing it requires the right to write in that library, and the pod's
grant over its own library is the only one an instance produces. A pod can
therefore never mark a folder it was not given. Recording the same machine
again is a no-op, so retries are safe; recording a *different* one is refused
rather than applied, because two machines filling one folder is a fault
upstream.

**Derivation, not copying.** Only the root carries the mark. Anything nested
resolves its answer from the root, through `features/tag/synchronized.py`, so
the two can never disagree. Every enforcement site asks that module rather than
reading the field.

**The guard.** A person may not add a document, remove one, create a folder
inside, or rename or move a marked folder. The service identity keeps exactly
the rights it holds today. The guard runs **after** the existing authorization
check, so a caller with no right is still told they have no right and learns
nothing about the folder from being refused. A refusal names the base, so the
reader learns why rather than only that they may not.

**Deletion stays available**, with its normal cascade. This is the one
asymmetry: content is guarded, existence is not. A team that wants to stop
taking a source deletes the base.

**In the UI, the partition is a withholding, not a badge.** Resources leaves
machine-filled libraries out of the corpus explorer entirely — they are not
folders people manage. The subtree is excluded by path prefix, because dropping
the marked root alone would leave its children behind and the tree builder
would raise the library straight back up out of their paths.

The Knowledge Base Documents page renders **the same Resources explorer**,
rooted at the library and read-only, rather than a second table beside it. A
library mirrors the shape of the source it follows, so it is browsed as a tree,
folder by folder, exactly as a corpus folder is. Read-only folds into the
single write gate the explorer already had, so both menus, both drop targets
and the toolbar follow it together. Row selection stays, because the bulk
download it also serves is a read.

---

## 6. What is not true today

Written down so nobody reads §§1–5 and infers more than is there. Each of these
is a candidate for its own scoped change.

**A machine's write is recorded as a human write.** KPI and audit attribution
has only "human" and "system", and a synchronizing write carries a subject, so
it is counted human. Anything reasoning about who wrote a document from the
operational record is currently wrong about Knowledge Bases.

**Fred imposes a result vocabulary on every author.** `KnowledgeBaseSyncResult`
requires `discovered / created / updated / removed / unchanged` and a
reconciliation flag. This forces every author to translate their business into
terms that are not theirs, to produce numbers Fred cannot verify and does not
act on. It is the clearest violation of §3 still standing in the SDK.

**Cross-team isolation rests on the pod's code.** See the blast radius in §4.

**Fred's vocabulary is compiled into the SDK.** `documents.py` hard-codes the
kind `knowledge_base` when building the marker. Harmless today, but it is Fred
knowledge inside the library a third party imports.

**Every pod declares its library on every run**, before the handler, whether or
not the author asked for it. Deliberate — a run that fails halfway has still
filled part of the library, and that part must not have been editable
meanwhile — but it is Fred plumbing running in someone else's process.

---

## 7. What an author actually writes

One declaration, and one handler:

```python
kb = KnowledgeBase(
    id="acme.kb.http-markdown",          # under a prefix this image owns
    version="1.0.0",
    name="HTTP Markdown",
    description="Synchronize Markdown documents",
    configuration_fields=[FieldSpec(key="base_url", type="url", title="URL")],
)

@kb.synchronize
async def synchronize(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
    ...
```

The context carries stable identifiers and the instance's resolved
configuration — never a credential for Fred, a transport client or any platform
object. Configuration is validated against the declared fields by the
dispatching Control Plane, not by the pod.

The pod is configured the way every other Fred component is: one
`configuration.yaml` resolved from `$CONFIG_FILE`, the models fred-pod already
owns, the same keys under `security.m2m` and `scheduler.temporal`, environment
variables carrying secrets only. A Knowledge Base pod installs
`fred-sdk[knowledge-base]`: fred-pod plus the workflow engine, none of the
agents platform. There is no `security.user` block — a
Knowledge Base pod serves no user, opens no inbound port and validates no user
token.

`fred-samples/knowledge-bases/local-folder` is the shortest complete example;
its `knowledge_base.py` is the whole authoring surface.

---

## Working on this

New Knowledge Base work is scoped as an OpenSpec change under
`openspec/changes/`, **one change per pull request**. A change that needs more
than roughly ten tasks is not a change — it is a design question, and it
belongs in an RFC or back in this document. The KB tree was previously carried
as three large changes totalling over ninety tasks; they were folded into this
document and deleted, because a plan that large reads as decided long before
anything is built.
