# Deterministic agent routing and per-row analysis over tabular data

**Status:** Open — no proposed solution yet, on purpose. Two connected but
distinct open questions surfaced live-testing ATTACH-TAB-01 (session-scoped
SQL-queryable CSV attachments); this RFC exists to frame them precisely
enough for a focused discussion, not to prescribe an answer ahead of it.
**ID:** `TAB-AGENT-01` (informal)
**Author:** Dimitri Tombroff / Claude Code
**Date:** 2026-09-04
**Participants for the follow-up:** Dimitri, Simon, Timothe, Florian
**Related:** `docs/swift/design/DESIGN.md` §2 (Tabular Artifact & DuckDB
SQL-Mounting Contract, INGEST-06; "Session-Scoped Attachment Datasets",
ATTACH-TAB-01 — the machinery both tracks below build on), issue #2530 /
PR #2420 (ATTACH-TAB-01 implementation this RFC follows from)

---

## 1. Problem statement

ATTACH-TAB-01 makes CSV chat attachments SQL-queryable (`tabular_v1` +
DuckDB, reusing the corpus tabular pipeline) instead of only text-searchable.
Live-testing it against a real CVE-scan CSV (5,436 rows) surfaced two
separate gaps, both about what happens *around* the SQL call itself rather
than the call's correctness:

**Track A — the agent doesn't reliably reach the SQL tool the same way
twice.** First live query attempt:

```
POST /tabular/query status=400
{"detail":"Query references unauthorized datasets: vulnerability_scan_report_2026_07_06"}
```

The model guessed the SQL relation name from the filename instead of first
calling `get_tabular_documents_schemas` to learn the real alias
(`d_83bab9414486_vulnerability_scan_report_2026_07_06`). It self-corrected
on retry (schema call → correct alias → 713-row `COUNT` succeeded), but that
retry is not guaranteed, and the discovery path itself has a structural gap:
`list_tabular_documents` — the endpoint that would otherwise let an agent
"just browse" and notice a dataset — deliberately never surfaces attachment
datasets at all (`_resolve_owned_attachment_dataset` is wired only into the
uid-scoped call sites, not the enumerating ones, to avoid an unbounded
metadata-table scan on every listing call — see DESIGN.md). So for an
attachment specifically, `get_tabular_documents_schemas(document_uids=[uid])`
is the *only* discovery path, and nothing today makes calling it before the
first `read_query` mandatory rather than optional.

Separately, and resolved same-day rather than deferred to this RFC: the
CSV's text-chunk vector preview (a truncated 20-row Markdown table, present
alongside the SQL dataset) has been removed entirely for CSV attachments —
it was a second, imprecise answer source competing with the exact one, with
nothing forcing the agent toward the right one. That's shipped (see
DESIGN.md), not an open question here. What *is* still open is Track A
above: making the *one* remaining path (SQL) reliably discovered before
first use.

**Track B — SQL alone can't do the next thing you'd actually want.** Once an
agent knows "713 rows match severity = 'Critical'", a realistic next ask is
per-row work that isn't expressible as SQL at all — e.g. "for each critical
CVE, check whether a public exploit exists and draft a one-line remediation
note." That needs a reasoning step per row (or per batch), not a query.
Florian is independently prototyping a pattern for this: an agent capability
that clones/spawns independent sub-agents to fire off that per-row work
concurrently. This RFC doesn't attempt to specify that pattern — it isn't
this author's design to make — but flags where it connects to Track A: any
per-row execution pattern still needs a reliable, deterministic way to first
resolve "which rows" via SQL, so a fix to Track A is likely a prerequisite
for Track B to be worth building on, not an independent concern.

---

## 2. What's already known (not proposals — groundwork for the discussion)

- **The schema/alias contract already carries everything needed for
  determinism**, it's just not mandatory to consult. `TabularColumnSchema`
  includes exact sample values for low-cardinality string columns (≤20
  distinct values) specifically so an agent doesn't have to guess casing —
  e.g. `severity: ["Critical", "High", "Medium", "Low"]` verbatim. The gap
  is procedural (call it first), not informational (the data to be
  deterministic already exists).
- **A prompt-level fix for Track A is cheap and has precedent.** #2418
  already proved that a paragraph-level instruction alone gets ignored in
  practice, but a per-line annotation glued to the attachment's uid changed
  model behavior reliably (`_CSV_ATTACHMENT_NOTE` in `react_prompting.py`).
  The same technique — an explicit "call schema-discovery before your first
  query on this uid" instruction — was not attempted before writing this
  RFC, on purpose: it's a plausible fix, not a decided one, and worth
  discussing whether it's sufficient or just a stopgap.
- **`search_tabular_values` (`POST /tabular/search`) already gives exact,
  full-data keyword/value lookup** across every column (substring,
  case/accent-insensitive), which is what the removed text-chunk preview was
  informally standing in for — but it is not semantic/fuzzy matching. A
  free-text column ("description", "notes") won't match a query like "rows
  about phishing" against a row that says "credential harvesting" without
  the literal word. Whether that gap needs closing, and how, is squarely
  Track A/routing territory: is exact substring search sufficient, or does
  some tabular content need a semantic layer back, deliberately designed
  this time (unlike the removed chunk, which was never authored as a
  router) rather than reintroduced as an ad hoc fallback?
- **Track B has no code yet to react to.** Nothing in this RFC assumes a
  shape for Florian's sub-agent-clone pattern; noted here only so the
  four-person discussion has both threads on the table at once, given they
  were raised together.

---

## 3. Open questions for the discussion

**Track A:**
- Does "call schema-discovery before first query" need to be enforced
  server-side (e.g., reject a `read_query` naming a dataset the caller
  hasn't `describe_documents`'d yet in this turn) or is a stronger prompt
  instruction enough? Server-side enforcement is more deterministic but adds
  state/complexity to `TabularService`; prompt-only is cheaper but inherits
  the same "usually works" ceiling every prompt-based fix has.
- Should attachment datasets get *some* discovery signal beyond "the agent
  already has the uid", given Track A shows that's not sufficient alone?
  (Not the removed vector chunk specifically — that mechanism is gone for a
  documented reason — but the question of whether an equivalent, deliberate
  signal belongs somewhere else, e.g. a stronger inline prompt instruction,
  is still open.)
- Is exact substring search (`search_tabular_values`) an acceptable
  permanent answer for "find rows about X" on tabular attachments, or does
  free-text-heavy tabular content need real semantic search back —
  deliberately scoped and authorized this time, not reintroduced as the old
  chunk was?

**Track B:**
- What does Florian's sub-agent-clone pattern need from the tabular surface
  specifically — a `read_query` result set handed directly to spawned
  sub-agents, or does each sub-agent need independent SQL/tool access to the
  same dataset?
- Execution-model implications: does spawning N sub-agents per row (or per
  batch) interact with anything in `RUNTIME-EXECUTION-CONTRACT.md`'s
  existing concurrency/cost model (KPI/cost accounting per turn, checkpoint
  isolation across parallel sub-agents, session/thread scoping)? Worth
  Florian confirming before this becomes its own RFC.
- Scope boundary: is this pattern generic (any tool result set fanned out to
  sub-agents) or tabular-specific? If generic, it likely deserves its own
  RFC entirely, with Track A here only as one example consumer.

---

## 4. Out of scope for this RFC

- **A prescribed solution for either track.** That's the point of raising it
  as an RFC now rather than shipping a fix unilaterally.
- **Excel/XLSX attachment SQL support** (`tabular_multi_v1`) — a separate,
  already-scoped follow-up noted in DESIGN.md, orthogonal to both tracks
  here.
- **Florian's sub-agent-clone implementation details** — his design to
  bring to the discussion, not this author's to draft.
