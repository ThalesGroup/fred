## Context

See proposal.md — Why.

Three existing mechanisms shape the approach and are deliberately reused rather
than replaced:

- **Activation** already works for native capabilities. `default_mcp_servers` is
  a misleading name for a list that carries any capability id; `platform_ops`
  declares `platform_postgres` there today. Nothing about activation needs to
  change.
- **Instance config** already has its shape: `AgentTuning.capability_config`, a
  map of capability id → the pod-validated envelope `{schema_version, config}`
  produced by `validate_config` and persisted verbatim. A template-side default
  should produce the same envelope through the same path.
- **Reasoning** already has template-level fields (`reasoning_enabled`,
  `reasoning_default_on`), with `platform_ops` as precedent. The "Reasoning"
  pack is not a capability and needs nothing new.

## Goals / Non-Goals

**Goals:**

- One new field, carrying configuration only, mirroring a field that already
  exists on the instance side.
- A template that is genuinely usable on creation without opening the
  capabilities view.
- A system prompt that makes an eight-capability agent route reliably.

**Non-Goals:**

- Renaming `default_mcp_servers`, or making `locked` / `require_tools` survive
  the projection to `default_capability_ids`. Both are real (the projection is
  lossy and `locked` is dead on the capability path), both are out of scope by
  explicit decision.
- Admin-editable templates. Templates stay code-defined in the pod.
- Any change to "offered but off" semantics: `available_capabilities` versus
  `default_capability_ids` stays as it is.
- Making an existing instance inherit a changed template default.
- **Attachment/corpus tabular parity.** An attached CSV gets a SQL dataset, an
  attached spreadsheet does not, and neither appears when listing tabular
  documents — so a conversation file and an ingested one behave differently.
  Making them behave alike (same access, different storage) is agreed follow-up
  work, deliberately out of this change.
- **`TABULAR-DATA-AGENTIC-ANALYSIS-RFC` Track A.** That RFC's status is "Open —
  no proposed solution yet, on purpose", and it records that the
  "call schema discovery before your first query" instruction was *not* tried
  yet, on purpose, so the discussion could happen. This prompt therefore does
  not implement it: it states what is true today (an attached CSV is reached by
  uid, not by listing) and prescribes no routing technique the RFC reserved for
  that discussion.

## Decisions

**Configuration only, named for what it carries.** `default_capabilities_config`
holds capability id → default config values. Activation stays in
`default_mcp_servers`. Alternative considered and rejected: one field carrying
both, superseding `default_mcp_servers` — cleaner on paper, but it leaves two
sources of activation until the old field is retired, which is the "one
mechanism, not two" trap this codebase already climbed out of once when the MCP
tuning trio was retired.

**Validate through the pod, not against a local schema.** A declared default is
run through the capability's own `validate_config`, the same call a member's
submitted values take, so the stored envelope is produced one way only. A
malformed default then fails against the template rather than lazily at agent
assembly, where the symptom is a suspended instance far from the cause.

**Seed the form, do not special-case the payload.** The form gains a
`defaultCapabilityConfig` seeding step beside `defaultCapabilitySelection`,
narrowed through the same `can_use`-filtered advertised set. Everything
downstream — the submit payload dropping config for unticked capabilities, the
pack derivation, the save path — stays untouched. This is what makes the
declared configuration visible in the form rather than only true at runtime.

**Why the knowledge assistant needs it at all, given `document_access`'s own
defaults are already corpus + attachments.** `withResourceState` derives the
attachments pack from an explicit `show_attach_files_control === true` and reads
an absent config slice as `false`, while the corpus side reads absent as on. So
a template pre-selecting `document_access` with no declared config produces an
agent that *does* offer attachments while the creation form *shows* that pack
off. Seeding the config removes the discrepancy at its source. (The asymmetry in
`toolPackLogic` is pre-existing and left alone: after the first save the stored
envelope carries explicit values and the two agree again.)

**The template's capability set**, as the union of the four requested packs:

| Capability | Why it is there |
| --- | --- |
| `document_access` (corpus + attachments) | search the team corpus and the conversation's files |
| `document_summarize` | short overviews |
| `document_verbatim` | exact wording of a passage |
| `document_extract` | exhaustive enumeration |
| `document_similarity` | compare and cross-reference — the primitive behind "recouper" |
| `mcp-knowledge-flow-mcp-tabular` | numbers, filters and aggregates over CSV/Excel |
| `team_wiki` | the team's stated conventions and rules |
| `writable_document` | return the answer as a downloadable document |

`default_capabilities_config` declares three slices:

- `document_access`: `search_attachments_only: false`,
  `show_attach_files_control: true` — the corpus + attachments row of the truth
  table.
- `document_extract`: `require_confirmation: false`.
- `document_summarize`: `require_confirmation: false`.

**Why the confirmation gates come off.** Both capabilities ship
`require_confirmation = True`, a proceed/cancel shown before any LLM work
because each is token-heavy. That default is right for a capability an operator
adds deliberately; it is wrong for a template whose declared posture is
exhaustive-by-default, where it would put a modal in front of the median
question and make the "answer without opening the capabilities view" promise
false. Turning them off is precisely what `default_capabilities_config` exists
to allow, and it is a per-template decision, not a change to either capability's
own default. Summarize is included for consistency: leaving one gate on would
mean a modal appears only when the user explicitly asks for the cheaper of the
two operations. Both remain editable per instance.

Reasoning: `reasoning_enabled = True`, `reasoning_default_on = True`.
Tool pacing: `REASONING_SAFE_TOOL_SELECTION`.

**`team_wiki` stays in read mode** (its own default): this agent consumes the
team's stated conventions, it does not author wiki pages. That binds
`wiki_list_pages` and `wiki_read_page` only, and keeps three write tools out of
an already large tool set. Stated here because the default is implicit
otherwise.

**The prompt says only what nothing else in the context says.** Roughly half a
first draft was already injected at run time from a closer authority: the per-turn
attachment suffix annotates each CSV/Excel uid inline (and the RFC records that
the paragraph-level form of that rule was *ignored* in live testing while the
inline form worked), the `team_wiki` capability injects the team's rules and page
index every turn, the tabular MCP server's own description carries the
schemas-before-query flow, and every document tool's docstring already forbids
echoing a document uid. Restating those costs context and, where a restatement
drifted, created a conflict the model would have had to arbitrate — one draft
told the model to use the SQL tools on a spreadsheet while the runtime was
telling it, on the same line as the uid, never to do that for an attached one.
The prompt below keeps only what is genuinely its own, and uses
`{response_language}` rather than restating the language rule.

**The system prompt is about routing, not tone.** Eight capabilities is roughly
fifteen tools. `TABULAR-DATA-AGENTIC-ANALYSIS-RFC` Track A documents, from live
testing, a model that did not reach the SQL tool the same way twice and guessed
a table alias from a filename. On this template the prompt is the component that
decides which tool answers which shape of question, so it is written as a
routing table with the traps named. It stays editable through the `prompts.system`
field, which is also where a member changes the default brevity.

Proposed prompt (EN; the FR variant mirrors it, as in `general_assistant`):

```
You are a knowledge assistant for this team. You answer from the team's own
written material: its document corpus, the files attached to this conversation,
and its wiki.

Respond in {response_language}.

## Be exhaustive by default

Unless the user asks for a summary, an overview or the gist, treat the material
exhaustively: when a question could be answered either from the most relevant
passages or by covering the whole document, cover the whole document.

Exhaustive means COVERAGE, not length. Cover everything, then answer as briefly
as the content allows — an enumeration lists every item found, prose stays
tight. Never compress an enumeration into "the main ones". If you could not
cover everything, say which part you did not.

## Choosing a tool

- What a document the user identified says → `extract_from_document`. This is
  the default, not a special case for "list every…".
- Which documents matter → search to FIND them, then cover those exhaustively.
  Search returns the most relevant passages, never all of them: it locates
  material, it does not answer from it.
- The exact wording of a passage → `read_document`.
- The user explicitly asked for a summary → `summarize_document`. Only then: it
  omits detail on purpose.
- Compare, cross-reference, "what else resembles this" → `find_similar_passages`.
  Its anchor is a passage of text, never the user's question; corpus only.
- Values, counts, filters, or which rows mention something, in a spreadsheet or
  CSV → the tabular SQL tools. A CSV attached here is reached by its uid; it
  does not appear when you list the tabular documents.

Tool calls per turn are bounded: prefer one well-aimed call to three speculative
ones, and never repeat a call you already made this turn.
```

**Proposed descriptions.**

- EN: "A ready-to-use knowledge assistant. It searches your team's documents,
  the files you attach to a conversation and your team wiki, then answers,
  cross-checks and summarises — and can return the result as a Word document."
- FR: « Un assistant de connaissance prêt à l'emploi. Il cherche dans les
  documents de votre équipe, dans les fichiers que vous joignez à une
  conversation et dans votre wiki d'équipe, puis répond, recoupe et synthétise —
  et peut restituer le résultat en document Word. »

**The blank slate stays blank.** `general_assistant` keeps declaring no
defaults and keeps its place as the first registry entry and the generic
starting point. The #2429 reasoning — that defaults on the universal starting
point turn into an admission hurdle — is about that template specifically. A
specialized template is the opposite case: a knowledge assistant without
knowledge access is pointless, so its dependencies are correct semantics.

## Risks / Trade-offs

**Seven of eight capabilities are `ADMIN_GATED`, so the template goes through
the dependency gate** → Mitigated, not avoided: the "Enable all" flow shipped
2026-08-28 grants every missing dependency at the same scope in one
confirmation, then the template. Without it this template would need seven
manual grants per team; with it, one dialog. Worth verifying by hand on a team
that has none of them, because the promise of the template rests on it.

**Fourteen tools in one agent's context is a lot** → Accepted, and the reason
the prompt is written as a routing table. Live testing on a real corpus is the
honest check; unit tests cannot tell whether the model routes well.

**Exhaustive-by-default is expensive, and the tool-call cap does NOT bound it**
→ Accepted deliberately. Extraction is a server-side map-reduce: ~26 LLM calls
per document at concurrency 3 (`extract/extractor.py`, measured live at 609k
chars before windowing cut it 18×), against one call for a search. The
deployment's 12-call-per-turn cap counts the AGENT's tool calls, so all of that
happens inside a single counted call and the cap never sees it. The cap also
truncates silently (`exit_behavior="continue"`), which the prompt's
"say what you did not cover" line cannot detect — the model gets no signal that
it was capped. This is the template's main operating cost and it is a chosen
trade, not an oversight: the alternative is an assistant that answers from the
top-k passages and quietly misses things, which is the failure mode this
template exists to avoid.

**A declared default becomes wrong when a capability's config schema changes**
→ Validation through the pod's `validate_config` makes that fail loudly at the
template rather than silently producing a broken instance, which is the whole
reason for routing it that way.

## Migration Plan

None required. The new field is optional and absent from every existing
template; a template that does not declare it behaves exactly as today. Existing
instances carry explicit stored selections and configuration and are untouched.
Rollback is reverting the change: the field disappears, the new template
disappears from the registry, and agents already created from it keep their
stored capabilities and configuration like any other instance.
