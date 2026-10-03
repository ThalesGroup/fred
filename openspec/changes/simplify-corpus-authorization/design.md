## Context

See [proposal](proposal.md) for motivation and scope. Audited Swift behavior:
`schema.fga` already derives document permissions entirely from parent tags;
`document_models.py` nevertheless stores an unconstrained `tag_ids` array.
Metadata listing enumerates readable documents; `get_tag_for_user` loads item
IDs even when vector-hit enrichment only needs a folder name. Overwrite unions
memberships, and source synchronization explicitly supports reparenting.
These are model/consumer changes, not merely a batch-check optimization.

## Goals / Non-Goals

**Goals:** one corpus membership authority; authorization cost independent of
documents per folder; explicit, testable bounds for broader discovery.

**Non-goals:** new authorization framework, new library permission tier, new
folder hierarchy, positive authorization cache across requests, or legacy
compatibility mode. Existing team grants and folder-parent inheritance remain.

## Decisions

### 1. Keep rights in OpenFGA and membership in SQL

Use the existing folder/tag identity. Corpus metadata gains a mandatory indexed
`folder_id` referencing its folder; any descriptive labels are non-authorizing.
Remove document relations from the FGA model and their writers/readers. Keeping
one parent tuple per document would retain duplicate membership and cross-store
consistency work without adding permission expressiveness.

Reuse the existing authorization facade: resolve a document's folder from SQL,
then check that folder. Read maps to folder READ; document update, delete and
process map to folder UPDATE, as in today's FGA model. Folder deletion retains
its own permission. Authentication and existing service-principal/team policies
stay intact; no owner or JWT-role shortcut replaces ReBAC.

### 2. Close every membership writer

Creation requires one existing, authorized destination; membership cannot change.
Same-folder overwrite preserves UID and folder. Conflicting UID/folder requests,
including source-sync path changes, return an explicit conflict before content
or membership mutation. Multi-folder and missing-folder requests are rejected.
Session attachments stay on their existing owner/session path, outside corpus
membership. Import/export accepts only the target format; legacy archives need
the separately delivered translator.

Enforce same-folder filename uniqueness transactionally to close the import
precheck race. Deletion/ingestion concurrency must not create an orphan: folder
deletion closes new writes, removes canonical rows before residual search hits
can be served, and uses the existing retryable cleanup flow. Do not add a second
job framework. Quota ownership derives from the folder, once per document.

### 3. Authorize bounded scopes, then query contents

SQL candidates are not grants. Batch-check distinct candidate folders using the
existing ReBAC client (extend its same-resource batch API for heterogeneous
resources); deduplicate within the request. Do not replace document ListObjects
with an unbounded folder ListObjects. Use stable SQL cursor pages plus checks;
return continuation even when a candidate page contains no authorized rows.
Never fill a page by scanning an unlimited number of denied candidates.

For explicit scopes, authorize the distinct folders before querying the corpus;
any denied scope rejects the request, never widens it. For unscoped retrieval,
process a bounded candidate window, resolve canonical membership in bulk, and
filter before returning content to the caller/model. Mark incomplete retrieval
explicitly; callers can continue within a finite request budget. This trades
single-call exhaustive discovery for predictable work without silent truncation.

Let B be the batch-check capacity, P the maximum candidate folders per page,
S the maximum explicit scope size and R the maximum retrieval candidates. These
are finite, enforced limits; over-limit inputs are rejected, not truncated.
Count checked tuples as well as HTTP calls; batching alone is not the bound.

| Operation | Maximum distinct folder checks per request | Corpus traversal |
| --- | --- | --- |
| Read one document | 1 | One indexed membership lookup |
| List/count one folder | 1 | Indexed page/count; no document authorization loop |
| Discover folders | P, per requested relation | One candidate page, explicit continuation |
| Search explicit folders | S | Search limited to authorized scope |
| Search without explicit scope | R | Bounded candidate window, explicit continuation |

Transport calls are at most `ceil(checks / B) * A` per relation, where A is the
finite maximum number of attempts including retries (B = 1 for individual checks).
This bounds application requests, not OpenFGA's internal graph traversal or SQL
count cost. Record actual configured limits and retry budgets in verification.

### 4. One gate across consumers; indexes never grant access

Use the same folder gate for metadata, content/download, vector/tabular search,
Resources and agent filesystem tools. Search indexes carry folder IDs as filters,
but returned candidates must still have canonical SQL rows in the authorized
folder. Deleted, missing or mismatched rows cannot leak content or counts.
Folder summaries carry counts, not eager item IDs; loading documents is a
separate paginated operation. Resolve folder names in bulk without content reads.
Regenerate APIs and update ReAct/Deep and UI consumers in the same change.

Use fresh higher-consistency FGA checks at the request gate, without cross-request
positive caching. A completed revocation applies to subsequent requests; already
authorized in-flight operations are not cancelled. FGA failure fails closed.
This favors predictable revocation over a cache-based performance patch.

### 5. Give documentation one authoritative home

Apply the following at implementation close-out, when the described behavior
ships. This planning PR does not relabel the current implementation as the target.
Paths below are relative to `docs/swift/`.

| Document | Disposition and evidence |
| --- | --- |
| `platform/REBAC.md` | Keep canonical overview; replace corpus mechanics with a link to the shipped capability spec. Preserve non-corpus grants. |
| `platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md` | Correct the opening global admin/editor/viewer RBAC description; link to the canonical identity/ReBAC boundary. |
| `design/INGESTION.md` | Keep pipeline/operations guidance; replace duplicated conflict rules with spec links and remove multiple-membership assumptions. |
| `design/KNOWLEDGE-BASE.md`, `design/RESOURCES-DASHBOARD.md` | Keep; update source reparenting and eager item-list assumptions respectively. |
| `backlog/AUTHZ-MIGRATION-BACKLOG.md` | Retirement candidate: closed #1875, deleted ID registry link and mixed completed/unchecked steps. First preserve still-valid guardrails in existing contracts/testing docs and repoint their links; retain history. |
| `rfc/RESOURCE-INGESTION-UX-RFC.md` | Recheck its two remaining questions against shipped code/issues; trim settled parts, retire only if no open decision remains. |
| `rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md` | Keep for open #2921; reconcile only its document-parent assumption when this target ships. |
| `rfc/DOCUMENT-VIEWER-AI-PANEL-RFC.md` | Keep: agent-picker/AI-panel decisions are unrelated and still open. |

No new RFC, audit/status document, or blanket deletion of frozen/history files.

## Risks / Trade-offs

- Breaking contracts → update all producers/consumers together; reject legacy
  shapes, including sync reparenting, rather than retaining dual semantics.
- Denied candidates reduce page density → explicit continuation/incompleteness;
  test sparse authorization so it cannot masquerade as end-of-results.
- SQL/search skew → canonical membership gate, including deletion and stale hits.
- Distributed cleanup and active ingestion → test failure/retry and concurrent
  writes; database constraints alone cannot clean external blobs/indexes.
- Scale claims → compare fixed requests with increasing documents per folder;
  instrument existing ReBAC metrics and database rows read, not latency alone.

## Migration Plan

Develop and validate on an empty, isolated local dataset. Do not reset the Monday
validation environment. Fresh-install success does not establish upgrade safety.
The later, separately reviewed offline translation must reconcile membership,
FGA model and indexes, reject ambiguous data, and provide backup/restore rollback.
No online compatibility layer or executable data translation belongs here.
The later release must classify operational impact independently of this
documentation-only PR; a minor version is not assumed sufficient.
