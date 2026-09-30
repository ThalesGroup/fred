## Context

See proposal.md for the observed failure. The captured Deep checkpoint for session `cf35a179-74d5-4b79-9d5d-953d9446a03c` reports `model_name: mistral-medium-latest`, `finish_reason: stop`, no native tool calls, and a content-list tail shaped like `{"type":"text","text":"read"}`, `"_query"`, `{"type":"reference","reference_ids":[]}`, `{"type":"text","text":"{\"sql\":\""}`, then a plain string containing the rest of the arguments and a second call. The persisted final answer is the literal rendering of those fragments. A second supplied exchange (session `bdd5c685-9826-4706-9d2e-d0160138a802`) shows the same mixed boundaries for `search_documents_using_vectorization`. The raw provider trace store is unavailable locally; these checkpoints prove the LangChain message shape received by the runtime, not the wire response before LangChain conversion.

A later ReAct checkpoint for session `921269a5-2880-48b9-9499-5c7458e2ea01` carries a native `list_tabular_documents` call and a mixed content tail with the exact marker followed by repeated empty objects and unrelated text. History rank 5 contains that tail as a `model_native` Planning thought because the stream bridge releases its pending recovery buffer when the native call completes. Another checkpoint for session `9325efb3-b690-49ca-8c38-ea459a75f4a3` has no native calls and contains two exact markers, each after `read_query`, within four valid calls. The completed parser rejects the second marker, and the final answer contains the literal call syntax. The local trace store is unavailable; the checkpoints establish the LangChain messages and persisted history, not the provider wire shape.

Before this change, `ToolCallTextRecoveryMiddleware` rejected any non-dictionary list item before parsing. `decode_stream_chunk` enabled sentinel handling only when every item was a typed dictionary. Both rejected this mixed list. The existing completed-message path already validates the exact empty sentinel, configured Mistral name, available tool, strict JSON, tool schema, and size limits. ReAct and Deep already install the middleware and route recovered calls through their normal controls.

## Goals / Non-Goals

**Goals:**

- Accept the captured mixed list without weakening the existing call-validation gates.
- Keep streaming and completed-message interpretation aligned for the same content shape.
- Preserve the existing behavior of ordinary answers, native calls, and rejected recovery candidates.

**Non-Goals:**

- Parse arbitrary textual tool-call syntax without the typed empty sentinel.
- Change how the model selects a table, SQL query, or final numerical answer.
- Change public APIs or the frontend view model.

## Decisions

### Interpret mixed fragments only within the typed recovery candidate

Treat a plain string as a text fragment alongside `{"type":"text","text":...}` in the existing bounded content-list parser. Concatenate fragments around the exact sentinel without inserting display separators, so a split tool name or JSON string retains its original bytes. Continue rejecting every other content item and every non-empty or extended reference block. The existing strict parser and schema validation remain the authority for execution.

Alternative: flatten the whole list through the generic text renderer and parse the result. That renderer adds newlines and stringifies the reference dictionary, losing the typed-marker distinction and making a prose example look executable.

### Make the stream bridge recognize the same mixed shape

Treat plain strings, typed text blocks, thinking blocks, and the exact empty sentinel as eligible content-list members when detecting the marker. Collect text on either side in order, and pass the joined fragments to the existing tool-name suffix probe. An unknown typed block keeps the generic rendering path so its text is not lost when recovery is rejected. Keep the current completed-message metadata decision: a recovered call discards its buffered encoding, while an unrecovered response releases buffered text. Do not broaden the branch for non-Mistral output.

Alternative: hide every empty reference block in generic text rendering. That would mask the visible symptom but leave the tool unexecuted and could silently alter ordinary responses.

### Handle repeated markers and native calls without leaking syntax

Allow a later exact marker only after another registered tool name. Remove only validated markers while preserving the original text bytes, then validate the entire call sequence before allocating any call IDs. Adjacent markers, modified references, malformed arguments, and a later marker without a registered name reject the whole recovery candidate.

When the completed message already carries native tool calls, keep those calls and IDs. If its mixed content contains the exact marker, discard the pending marked stream buffer instead of releasing it as answer text and then reclassifying it as a Planning preamble. Safe prose emitted before the tool-name probe remains available as a preamble.

### Reproduce from a redacted checkpoint shape

Add minimal fixtures preserving the important boundaries from both checkpoints: a tool name split between a text block and a string, the exact typed sentinel, JSON split between a text block and a string, and a second call in the trailing string. Use fake table names and document IDs. Test recovery directly and through both runtime stream routes. Add rejection cases for non-Mistral, malformed mixed content, non-empty references, native calls, and ordinary text. Confirm recovered calls still meet approval and tool-result pairing checks.

Alternative: rely on the current all-dictionary fixtures. They pass while this captured shape fails, so they cannot guard the regression.

## Risks / Trade-offs

- [Accidental execution from a mixed prose response] → Require the same exact typed sentinel, registered tool, strict complete JSON, schema validation, Mistral identity, and bounds before creating a call.
- [Streaming text is lost when recovery fails] → Release the buffered original text on the existing unrecovered path and assert ordinary mixed-text behavior.
- [Middleware and stream parser drift] → Use the same definition of eligible fragment shapes in both paths and test them as one end-to-end case.

## Migration Plan

No data migration or API rollout is needed. Deploy with the runtime; rollback restores the previous parser. Historical malformed final answers remain unchanged.
