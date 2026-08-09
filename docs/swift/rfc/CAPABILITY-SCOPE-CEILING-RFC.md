# RFC: Capability scope as an authorization ceiling (agent-scope-first authorization)

**Status:** proposed — open design question; no implementation approved by this RFC alone
**Author:** Maxime Daragon
**Date:** 2026-08-05
**ID:** CAPAB-SCOPE-01
**Related docs:** `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8.11 (pod-side authorization), §8.15 amendment 2026-07-21 (`attachments_only`), §8.16 (document ports); `docs/swift/rfc/AGENT-FILESYSTEM-HARDENING-RFC.md` (F1/P1 — same problem at the `/fs` boundary); `docs/swift/capabilities/AUTHORING.md`; `docs/swift/platform/REBAC.md`

---

## 1. Problem

Today, when an agent tool reaches for a document, the only authorization that
runs is **the end user's** ReBAC. The agent contributes the _tool_; the user
contributes the _rights_. There is no step that asks, first, **"what is this
agent's mission allowed to touch at all?"**

That ordering is backwards for least-privilege. It means an agent whose entire
purpose is "work on the files attached to _this_ conversation" can, through a
tool like `summarize_document`, resolve a **corpus** document — provided the
_user_ happens to have corpus rights and a document identifier reaches the
model. The agent's narrow mission does not bound it; only the user's (possibly
broad) rights do.

The desired model is the inverse, in two ordered gates:

1. **Agent gate (ceiling).** What is _this agent instance_ — given the
   capabilities and configuration it was created with — allowed to see or do?
   This is a hard boundary. The user's rights can never widen it.
2. **User gate (within the ceiling).** _Inside_ that boundary, what is _this
   user_ allowed to see? This narrows further, never widens.

Effective access = **agent ceiling ∩ user rights**, with the agent ceiling
evaluated first and independently. An "attachments-only" agent must never
surface a corpus document, **even for a user who has full corpus access**.

This is the classic **confused-deputy** defense: the agent acts with the
user's borrowed authority, so without a mission-scoped ceiling it can be
steered — by a prompt, a pasted identifier, a tool-chaining accident — into
exercising the user's _broad_ authority outside the agent's _narrow_ purpose.

## 2. Current as-built baseline (honest state)

The security root is settled and is **not** in question here: there is no
control-plane-issued grant; every execute/resume request is authorized
pod-side by Keycloak JWT identity + OpenFGA, funnelled through
`_authorize_and_resolve` (RUNTIME-EXECUTION-CONTRACT §8.11, RUNTIME-07 rev. 2 /
decision D5). **This RFC does not touch that root and does not reintroduce any
signed grant.** It concerns what happens _after_ a request is authorized, when
the agent's tools call back into the platform for documents.

Two facts define the gap:

- **One tool already implements the agent-first model — as a special case.**
  `DocumentSearchAdapter.search()` computes
  `include_session_scope, include_corpus_scope = get_vector_search_scopes(runtime_context)`
  and then, **iff** the capability config set `attachments_only`, hard-overrides
  to `(True, False)`
  (`libs/fred-runtime/.../v2_runtime/adapters.py:820-823`). Knowledge Flow then
  _structurally skips_ every corpus branch when `include_corpus_scope=False`
  (`vector_search_service.py:690,695,722` — the corpus vector store is never
  queried, not merely filtered afterwards). This is a real ceiling — but it
  exists for exactly **one** tool and is expressed as a **per-tool boolean**.

- **Every other document tool follows user-rights-first, with no ceiling.**
  `DocumentSummarizeAdapter.summarize()` states it outright: _"No scope
  narrowing here: the caller already holds a concrete `document_uid` … and
  Knowledge Flow's own per-document ReBAC is the real authorization gate"_
  (`adapters.py:1034-1042`). The KF summarize service resolves the document via
  a per-**user** ReBAC check (`summarize/service.py:74-102`); the only
  attachment-specific isolation is a fallback that reconstructs text from
  session vectors owned by the requesting user. There is no step that asks
  whether _this agent_ was ever meant to reach beyond attachments. The same is
  true, by construction, of any future document-touching capability (PPT
  filler, tabular/filesystem MCP tools, writable-document exports, etc.): each
  reaches the platform its own way and authorizes against the user alone.

So the principle this RFC argues for is **already accepted and shipped in one
place** — it is not a new invention. What is missing is (a) making it a
**first-class, once-declared ceiling** rather than a per-tool boolean, and (b)
making **every** document-touching port honor it, not just search.

The `AGENT-FILESYSTEM-HARDENING-RFC` reaches the identical conclusion for the
`/fs` boundary (F1: _"Knowledge Flow receives only a `KeycloakUser`. It cannot
know whether a write … was made by the matching runtime agent instance or by
another first-party caller using the user's bearer token"_). This RFC is the
generalization of that finding from the filesystem to the whole document/
capability surface, and should share its enforcement mechanism rather than
invent a parallel one.

## 3. The principle we should adopt

**Capability selection defines an authorization ceiling that is enforced before
user rights, uniformly, for every platform resource a capability can reach.**

Concretely:

- An agent instance's selected capabilities + their config **derive a scope
  descriptor** — the set of resource classes and instances the mission is
  permitted to touch (e.g. `documents: {session_attachments}` for an
  attachments-only agent; `documents: {corpus(libraries=…), session_attachments}`
  for a full document-access agent; `filesystem: {agents/<id>/…}` for the
  workspace, already the filesystem RFC's subject).
- This descriptor is computed **once**, at the pod, from the agent instance —
  the same place and moment the pod already builds the tools and adapters. It
  is **not** user-supplied and **not** per-turn; the user's per-turn RAG-scope
  control can only narrow _within_ it.
- **Every** document/resource port intersects its call against this descriptor
  **before** the existing per-user ReBAC runs. A tool that receives a
  `document_uid` outside the ceiling fails closed **regardless of the user's
  rights** — exactly as `attachments_only` already makes corpus branches
  unreachable for search.

The mental model becomes: `effective = agent_ceiling ∩ user_rebac`, ceiling
first. `attachments_only` stops being a bespoke search flag and becomes one
value of a general, uniformly-enforced scope.

## 4. Risks if we do NOT adopt this

1. **Confused-deputy corpus exposure (primary).** An agent advertised and
   configured as "conversation-local / attachments-only" can, today, surface
   corpus content through any non-search document tool, for any user who has
   corpus rights. The isolation currently rests on _"the model was not given a
   tool that hands it corpus identifiers"_ — a discovery accident away from
   failing, not a boundary. As we add document-manipulation capabilities
   (summarize, PPT, tabular, export…), the number of tools that can be
   steered past the intended mission grows, and each is authorized only by the
   user's rights.

2. **The ceiling erodes silently with every new capability.** Because
   enforcement is per-tool (only search has it), every new document-touching
   capability is _opt-in_ to isolation and defaults to user-rights-first.
   Forgetting to add a bespoke `attachments_only`-equivalent to one new tool
   silently punches a hole in the ceiling, with no single place that would have
   caught it. A once-declared, port-enforced ceiling fails safe by default; N
   per-tool booleans fail open by omission.

3. **No coherent story for "restricted agent, privileged user."** The most
   valuable deployments — a locked-down assistant shared with users who _do_
   have broad corpus rights — are precisely the ones the current model cannot
   express. Without an agent ceiling, "give this agent to admins but keep it
   attachment-local" is unbuildable; the agent inherits each admin's full
   reach.

4. **Divergent, duplicated isolation mechanisms.** The filesystem boundary is
   already growing its own actor-scope mechanism (filesystem RFC P1). Document
   tools have `attachments_only`. Left unaddressed, each new surface invents its
   own ad-hoc scoping, and "what can this agent touch?" has no single
   answer — the opposite of the capability model's "one capability carried end
   to end" doctrine (`AUTHORING.md`).

5. **Weak auditability.** "Did this agent stay within its mission?" cannot be
   answered from one signal today; it must be reconstructed per-tool. A
   first-class scope descriptor is also the natural thing to log and to show in
   the admin capabilities surface.

## 5. Proposed model — two enforcement tiers

Following the precedent the filesystem RFC already set (trusted first-party
enforcement now; defense-in-depth at the service boundary later), enforcement
is staged. **Tier 1 delivers the principle; Tier 2 hardens it.**

### Tier 1 — Uniform ceiling in the pod's port layer (the target this RFC seeks approval to design)

- Define an **agent scope descriptor** derived at bind time from the agent
  instance's capabilities + config, carried on the runtime binding /
  `RuntimeServices` (the same object graph that already holds
  `document_search`, `document_summarize`, etc.).
- Make the descriptor's document-scope the **single source** of the
  session/corpus ceiling — `attachments_only` becomes _derived from_ it, not a
  parallel field. `get_vector_search_scopes` starts from the ceiling, not from
  the per-turn control.
- Have **every** document port (`document_search`, `document_summarize`,
  `document_content`, `document_folders`, and any future one) intersect its
  target against the descriptor **before** calling KF: a `document_uid` or
  library tag outside the ceiling is refused in the adapter, fail-closed,
  independent of user ReBAC. Search's existing corpus-branch skip is one
  instance of this rule; summarize gains the same treatment (an attachments-only
  ceiling refuses a corpus uid even when the user could read it).
- **Trust boundary (honest):** in Tier 1 the pod is the enforcer, consistent
  with RUNTIME-07 rev. 2 making the pod the execution authority. This is
  sufficient against the confused-deputy _application_ risk (a mis-steered LLM),
  which is the primary threat. It does **not** yet defend against a buggy or
  compromised pod code path — that is Tier 2.

### Tier 2 — Ceiling enforced at the Knowledge Flow boundary (defense in depth, later)

- Carry the agent scope descriptor to KF as an explicit request-scoped input
  (the actor-scope idea shared with filesystem RFC P1 — `actor_type`,
  `agent_instance_id`, permitted document scope), **derived from the existing
  JWT + pod-verified execution scope, not a control-plane-signed grant** (D5
  stands). KF then applies the ceiling server-side _before_ its per-user ReBAC,
  so even a pod path that forgot the Tier-1 intersection cannot exceed scope.
- This converges with, and should reuse, whatever principal the filesystem
  hardening lands — one actor-scope mechanism for `/fs` and document endpoints,
  not two.

## 6. Impact on existing contracts

- **`RUNTIME-EXECUTION-CONTRACT.md`.** The `attachments_only` amendment
  (§8.15, 2026-07-21) is reframed as the first instance of the general ceiling;
  the document-ports section (§8.16) gains the scope-descriptor input. Tier 1 is
  internal DI (no OpenAPI/wire change, same as the original `attachments_only`).
  Tier 2 _does_ change the KF request surface and needs its own dated contract
  entry + client regeneration when specced.
- **`CONTROL-PLANE-PRODUCT-CONTRACT.md`.** No change to admission itself:
  capability selection already lives on the agent instance; the descriptor is
  _derived_ from it, not a new stored field. If the admin capabilities surface
  later exposes the ceiling, that is an additive read.
- **`AUTHORING.md`.** New authoring rule: a capability that reaches a platform
  resource declares the scope it needs; the runtime, not the capability,
  enforces the ceiling. This keeps runtime/identity info out of LLM-facing tool
  signatures (existing doctrine) while giving the platform a uniform place to
  bound reach.
- **Filesystem RFC.** Its P1 actor principal and this RFC's Tier 2 should be
  specced as one mechanism. Flag the dependency in both.

## 7. Alternatives considered

- **Per-tool `*_only` booleans (status quo, extended).** Add an
  `attachments_only`-equivalent to each new document tool. Rejected as the
  _primary_ model: it is exactly the fail-open-by-omission risk (§4.2) and
  produces no single answer to "what can this agent touch?". It remains the
  _fallback_ if a uniform descriptor proves too invasive for Tier 1 — but even
  then the descriptor should own the booleans, not vice-versa.
- **Enforce only in Knowledge Flow (skip Tier 1).** Cleaner trust boundary, but
  larger blast radius and a wire-contract change up front; delays delivering the
  principle at all. Staging (Tier 1 now, Tier 2 later) matches the filesystem
  RFC's accepted approach and de-risks.
- **Reintroduce a control-plane-signed scope grant.** Explicitly rejected:
  contradicts RUNTIME-07 rev. 2 / D5 (§8.11). The ceiling must derive from the
  agent instance the pod already resolves + the existing JWT/OpenFGA context.
- **Do nothing / rely on not giving the agent discovery tools.** The current de
  facto isolation for summarize. Rejected: it is "the model doesn't know the
  identifier," not a boundary — one paste/history/guess away from failing, and
  it offers nothing for the privileged-user case (§4.3).

## 8. Open questions (for developer decision before any implementation)

1. **Scope granularity.** Is the document ceiling a small enum
   (`attachments_only` / `corpus+attachments` / `corpus_only`) — matching
   today's shape and shippable fast — or a richer descriptor (specific
   libraries/document sets) from day one? Recommendation: start with the enum
   that already exists implicitly, design the descriptor to grow.
2. **Fate of `document_access.search_attachments_only` / `show_attach_files_control`.**
   If the ceiling is derived from capability selection, these per-capability
   toggles are re-expressed as ceiling inputs. Migration story for already-stored
   agent configs is required (cf. the copy/rename work already in flight on
   `#2220`, and the separate question of splitting attach-files into its own
   capability).
3. **Tier boundary.** Approve Tier 1 alone now (pod-enforced, no wire change),
   with Tier 2 as a tracked follow-up gated on the filesystem actor principal?
   Recommendation: yes.
4. **Interaction with the standalone attachment/summarize capability discussion.**
   This RFC is the _authorization_ substrate under that product question:
   "an agent that can use attachments but not the corpus" is only a real
   guarantee once the ceiling exists. Sequence the two deliberately.

## 9. Non-goals

- Changing the pod-side authorization root (§8.11 / D5) — untouched.
- Any new control-plane-issued token or cryptographic grant.
- Reworking user-level ReBAC semantics — the user gate is unchanged; this RFC
  only inserts the agent gate _before_ it.
- The product/UX of which capabilities exist or how they are named/presented
  (tracked separately, e.g. `#2220`).

---

**Decision requested:** approve the _principle_ (§3) and the Tier-1 target
(§5) as the direction, so a scoped GitHub issue can be opened to design the
agent scope descriptor and the uniform port intersection. No code is proposed
by this RFC alone.
