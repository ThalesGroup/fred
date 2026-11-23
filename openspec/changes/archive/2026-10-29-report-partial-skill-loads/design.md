## Context

See proposal.md for motivation. DeepAgents 0.7.30 owns `read_file` and native
pinning. `skills/native.py` supplies a shared parent/child prompt;
`skills/native_reads.py` observes the actual tool response after execution.
`SkillLoadAttribution` already reaches SSE, history metadata and trace labels.

## Goals / Non-Goals

**Goals:** strengthen the existing prompt and disclose partial native instruction
reads through the existing activity, without another file read or model call.

**Non-Goals:** automatic limit rewriting, a replacement skill loader, cumulative
page-coverage tracking, new activity types, new metrics or persistent active-skill
state. A partial activity describes that read, not the skill's later global state.

## Decisions

1. Make the prompt explicitly require `read_file(file_path=..., offset=0,
   limit=1000)` for a fresh `SKILL.md` read. Explain the 100-line default and
   require inspecting pagination/truncation and continuing before applying the
   procedure. Retain complete-pin reuse and conditional reference reads.
   The alternative of rewriting tool arguments is excluded by the user.
2. Add `partial: bool = False` to the existing attribution model. Set it for
   observed native first-page reads whose actual returned envelope does not
   prove coverage from the first through last line without truncation. Use the
   runtime-generated range/continuation/truncation header, not the requested
   limit, a second disk read or a search through the skill's own instructions.
   Missing or unrecognized coverage is conservatively partial. Native full pins
   and ReAct loads retain the default; missing fields in old history remain
   compatible. Regenerate affected OpenAPI clients from their source.
3. Preserve current attribution/counting: one successful offset-zero read is
   one existing load event/KPI, with a partial flag describing its result.
   Continuations and references add no extra load count. Counting cumulative
   pages would add revision/context state outside this request's scope.
4. Propagate the flag through existing SSE/history metadata and render
   `Skill partiellement chargé` / `Skill partially loaded` in the activity row,
   its accessible name and shared trace label. Complete/legacy rows retain
   their existing labels. Reuse existing UI structure without new dialogs.

## Risks / Trade-offs

- Upstream envelope formatting can change: isolate its bounded-header
  recognition and test real native outputs, size clipping, mid-line clipping,
  notices and unknown coverage. Never use a substring in the file body as proof.
- A long skill can still require several calls: the prompt guides continuation;
  this change does not claim deterministic model compliance or cumulative proof.
- Scale and replicas: inspect only the bounded tool-result header; no additional
  I/O, clients, tables, shared coordination or process-local correctness state.
  Independent concurrent parent/child observations must keep their own flags.

## Migration Plan

No configuration or database migration. Ship additive metadata and translated
labels through normal deployment; older history without the field retains its
presentation. Verify known relay/consumer compatibility and regenerate schemas.
Rollback restores the old labels and ignores the additive history metadata.
