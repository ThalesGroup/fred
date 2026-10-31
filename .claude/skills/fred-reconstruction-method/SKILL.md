---
name: fred-reconstruction-method
description: Design or review Fred Weaver domain and persistence changes from business needs, lifecycle invariants, PostgreSQL schema and transactions before application behavior, API and UI. Use for ownership, access, invitations, resources, quotas, document lifecycle or schema work; not routine formatting or local startup.
---

# Weaver foundations

Read the active checkout's `AGENTS.md` and relevant arc42 chapters. This skill
holds the team's agreed design method and business constraints. They are intended
requirements, not claims that every table or journey already implements them.
Distinguish currently used behavior, schema preparation, functionality still to
implement and historical Swift behavior throughout the work.

Work in this order: **business need -> invariants and lifecycle -> schema and
transactions -> application usages -> API -> UI**. Existing code provides facts;
it does not alone define the right business model. Keep the authorized increment
short. Do not redesign unrelated domains or turn each topic into a test campaign.

## Converge before adding

Apply `AGENTS.md`'s reduction/reuse acceptance rule. Identify the current domain
owner, shared library and design-system element that should carry the behavior.
Explain what to reuse, extend, replace or remove before proposing new code. Prefer
a smaller maintained surface and fewer concepts, not a separate "new feature"
implementation. Justify unavoidable additions in the agreed increment; never trade
away constraints, safety or readability to reduce a line count.

## Establish the need

Use concrete actors and examples: who creates, uses, changes, shares, expires or
deletes the object; in which space; with what rights and quota effects; what must
remain after deletion; and which operations can overlap. Consult existing agreed
decisions before asking a question already settled below.

When doubt changes rights, isolation, retention, cardinality or lifecycle, ask a
specific business question and explain the consequence. Do not ask the business
to choose between interchangeable SQL details. Resolve ordinary technical choices.

Prefer few precisely named concepts, one authority per fact, explicit relations,
verifiable constraints and short transactions. A SQL constraint can eliminate
application complexity. Do not turn PostgreSQL into a universal business-rule
engine: distinguish schema, Control Plane policy and specialized components.
Explain what the solution covers, its limits and what a plausible future change
would require; do not build speculative infrastructure for that future.

## Agreed design constraints

### Authority

Control Plane and PostgreSQL own application identity, memberships, roles,
placement and access-decision facts. Control Plane applies authorization policy;
SQL protects structural consistency. Python components call Control Plane;
Knowledge Flow uses workload identity and receives the authorized document scope.
S3 holds objects. OpenSearch and vector indexes are specialized projections, not
a second source of rights or current placement. OpenFGA is removed; no remote
authorization engine or generic relationship graph should be reintroduced.

### Spaces and invitations

- Initial hierarchy: organization -> team -> project. Personal spaces belong to
  an organization and are strictly individual, with no invitations.
- Do not anticipate nested teams/projects or generic cross-organization sharing.
  The specific cross-organization invitations below are an agreed exception to
  that absence of generic sharing, not permission to build a generic graph.
- Invitations use the same mechanism for organizations, teams and projects.
  Invite an already known user; access starts at the responsible person's decision,
  with no acceptance step. Expiration is mandatory. Record invited status, author
  and dates. Invitations in different spaces are independent; permanent and
  temporary grants remain independent. Permanent space deletion purges invitations.
- Example: the owner of team E in organization A invites Florian from B as analyst
  and Bill from C as editor. Each gets the functional rights of that role. Invited
  status records provenance and duration; it is not a reduced functional role.
- Make inherited access and access to common resources explicit. A local invitation
  does not imply permanent global membership. Organization governance may reserve
  invitation administration to central admins without changing the data mechanism.
- Vocabulary: admin is technical responsibility; owner/responsible person is
  business responsibility, including agents, prompts, skills and members.

### Agent execution

A turn already admitted may finish despite revocation, invitation expiry or user
deletion. New admissions use the new state. State the admission boundary and access
context lifetime. Do not add loop complexity to interrupt these existing turns.
Preserve separate cancellation, execution limits and resource-specific checks as
specified in `AGENTS.md`; do not silently convert them into admission refreshes.

### Documents

Reprocessing is a first-class need. Moves may cross folders or spaces within one
organization, not organizations in the initial scope. Temporarily refuse moves
during ingestion or reprocessing. A temporary search absence during a move is
acceptable; continued unauthorized access through the old space is not.
Unchanged content needs no new embeddings, but index metadata may still need
updating. Conversation attachments remain bound to their conversation.

### Quotas

Enforce a global organization ceiling while retaining local budgets. A team
shares its budget with its projects; personal spaces have their own budgets.
A team-conversation attachment consumes the team's budget. Account for originals
and reserved uploads. A reservation allocates bytes to an admitted but unfinished
upload so concurrent uploads cannot collectively exceed quota. Derived files and
physical bytes awaiting purge need separate monitoring, not silent inclusion in
or substitution for the agreed logical quota.

### Agent resources

Use a stable UUID identity, a mutable display name and a stable logical name for
references, including future agent calls. For prompts the logical name is also
the command: no second command identifier. Keep technical identifiers unobtrusive
for users. Do not add a generic resource abstraction, generalized versioning or a
skill table without a confirmed need.

## Design capacity targets, not demonstrated performance

| Dimension | Target |
| --- | --- |
| Organizations per installation | 5-10 |
| Teams per organization | Up to 100 |
| Known users per installation | 50,000 |
| Simultaneously connected users | 5,000 |
| Simultaneous agent requests | Up to 5,000 |
| Documents per installation | About 10 million; one organization may hold several million |

Projects include a few dozen durable projects and temporary projects, such as a
two-month tender, followed by closure and possibly deletion. Document activity
includes large batch imports, regular daily increments, continuous conversation
attachments, reprocessing, deletions and purges running concurrently.

Distinguish open sessions, in-flight HTTP requests, active agent turns, concurrent
model calls and concurrent document processing. Model cost/capacity is a separate
sizing problem from the SQL catalog. Never treat 100 million rows as a universal
PostgreSQL limit: queries, indexes, row size, writes, locks, hardware and maintenance
all matter.

## Inspect the schema and its enforcement

After the business need and invariants, inspect migrations and the generated
schema reference for identity/uniqueness, ownership/placement, cardinalities,
nullability, foreign keys, constraints, state transitions, logical deletion,
purge and existing indexes. Then inspect actual writes and readers to identify
compatibility and coordination gaps. Do not assume the live database matches the
checkout; inspect applied migration history when a database operation is requested.

For each proposal, identify which responsibility enforces each guarantee:

- SQL invariant, including uniqueness, references and structural constraints;
- application transaction, including concurrent state transitions and locking;
- authorization check, including actor, space, scope and freshness boundary;
- external projection synchronization, including stale data and retry behavior.

Reuse a table when its meaning, ownership and lifecycle fit. Do not force unrelated
objects into one table to avoid a justified new table. Preserve applied migrations
and inspect the next sequence number just before adding one.

## Cost and concurrency

For each important path identify actual rows read/written, expected selectivity,
usable indexes, pagination/batches, lock order/duration, shared contention and
retry/concurrent-execution effects. Focus on organization counters, concurrent
quota reservations, publication/reprocessing, move/process/delete races, and bulk
hierarchy deletion/purge. Explain which writes must be atomic.

SQL indexes and OpenSearch indexes solve different problems. A partial index over
non-deleted rows may serve normal reads but not purge or foreign-key checks.
Inspect existing indexes and queries first; justify each addition with a concrete
access path and its write/storage cost. Do not default to partitioning, sharding,
caches, distributed counters or repair machinery without an established need or
measurement. Keep work bounded across replicas, not just in a single-process demo.

A synthetic SQL plan demonstrates index use for that fixture. It does not prove
production capacity for 10 million documents or 5,000 simultaneous agent requests.
Honor the repository's execution scope before running database or load experiments.

## Deliver a bounded increment

Schema-only work is valid when current writes remain coherent, rights do not
change silently, no incomplete mechanism activates and no competing authority
appears. Name the obligations of future consumers. If a constraint requires an
application change now, explain that before modifying it. Never drop an existing
protection to enable a feature whose coordination is not ready.

A temporary transition needs a reason, remaining adaptations and an exit condition.
Record these in the existing task/issue and appropriate migration comments, not a
new standing RFC or architecture plan. Prepared structure can be identified as such
in technical references; it must not be described as an operational user journey.

Report the understood need and settled decisions, genuinely open business questions,
the minimal recommended solution, invariants and owners, volume/write/concurrency
consequences, immediate/later application adaptations, and actual verification with
its limits. Scale detail to the increment. When the foundation is sufficient, say so
and proceed with authorized implementation; do not prolong schema design indefinitely.
