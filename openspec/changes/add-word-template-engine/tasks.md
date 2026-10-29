# Tasks - Fill and write any Word template from an agent conversation

The capability was built before this change was written; tasks record what
exists and how it is verified.

## 1. Capability package and storage

- [x] 1.1 Create `fred-capability-word-template` with its `fred.capabilities`
      entry point and register it in `apps/fred-agents`; verified by the
      registration test (`test_capability_registers_and_validates_clean`)
- [x] 1.2 Add the capability's Alembic tree (`cap_word_template_*`: sessions,
      batches, snapshots, analyses, attachments, images; one revision) and
      register it in the combined migration checks; verified by the
      single-head check
- [x] 1.3 Store and the fake store share one interface, including attachment
      and image deletion; verified by the store tests and an in-memory SQL
      round trip of `delete_attachment` / `delete_image`

## 2. Document map, analysis, operations

- [x] 2.1 Document map with positional addresses and parts; multi-part reads;
      verified by `test_docmap.py` and the `read_template` tests
- [x] 2.2 First-use template analysis, cached per sha256, single flight,
      60 s timeout and back-off, timed on `llm.call_latency_ms`; verified by
      the analysis tests (concurrency, timeout, metric dims)
- [x] 2.3 The six operations, batch validation, replay, undo and snapshot;
      verified by `test_operations.py`, `test_replace_text_and_lists.py` and
      the snapshot tests
- [x] 2.4 One reader for the analysis' addresses (lists, relative range
      ends, reversed ranges), shared by fixed wording, text still to write
      and repeatable blocks; a text also meant to be replaced is not fixed;
      verified by `test_analysis_addresses.py` (14 tests, suite 200 passed)
- [x] 2.5 A model `set_text` of several paragraphs or list items is handled,
      stored and gated as a `write`; a body `set_text` drops the guidance
      colour; verified by the `as_written` / colour tests in
      `test_operations.py`, the gate cases in `test_hitl.py` and the
      written-content test in `test_capability.py` (suite 212 passed)

## 3. Guards on the model's batches

- [x] 3.1 One edit per step; read before edit; re-read after a structural
      edit or undo (checked against the engine's real reply text); stale-read
      refusal after a collaborator edit; verified by the middleware tests
- [x] 3.2 Last table copy kept; headings kept; fixed wording kept unless
      `changes_template`; verified by `test_operations.py` and
      `test_fixed_wording_is_kept_unless_the_change_is_declared`
- [x] 3.3 One part of written content per turn, fields and cells free;
      verified by `test_written_content_goes_into_one_part_per_turn`
- [x] 3.4 Refusals as plain results, failures as errors; verified by the
      tool tests asserting `is_error`
- [x] 3.5 Approval gate for removals, new headings and declared fixed-wording
      changes, with the plain-language question; verified by `test_hitl.py`

## 4. Base, attachments, images, progress

- [x] 4.1 Library templates and attached-file bases, with the "source by
      default" rule; verified by `test_attachments.py`
- [x] 4.2 Images from the chat and from attached Word files; verified by
      `test_images.py`
- [x] 4.3 Parts still to write in every model call; verified by
      `test_parts_still_to_write_are_in_the_prompt` and
      `test_parts_to_write_follow_the_document_not_the_conversation`
      (superseded by 4.5-4.6: the per-part list is replaced, not kept)
- [x] 4.4 Delete routes for attachments and images (409 for the base and for
      placed images); verified by the route tests in `test_attachments.py`
- [x] 4.5 Part check in the reply of each applied model batch: places still
      holding template text (plain location, current address, start of
      text), [À COMPLÉTER] markers, fields inside fixed wording reported as
      details; follows removals, insertions and repeats; verified by
      `test_an_edit_reply_lists_the_places_left_in_the_part`,
      `test_after_a_removal_the_checked_part_is_named_by_its_title` and the
      `check_parts` tests in `test_docmap.py`
- [x] 4.6 Whole-document count per part (named by title) in every model
      call, replacing the per-part list; says when nothing is left; verified
      by `test_the_document_check_is_in_the_prompt_and_in_edit_replies`
- [x] 4.7 Template text: generic placeholder patterns added; TOC lines left
      out (the map has no field flag, so fields are not singled out);
      whole-table roles count only coloured text and patterns; patterns
      never remove fixed-wording protection; verified by
      `test_analysis_addresses.py` (suite 218 passed)
- [x] 4.8 Evidence: unit tests for the scenarios; replay of live
      conversations (unfilled guidance and fields are reported); bench over
      seven analysed templates (whole-table label false reports 24 -> 0 and
      87 -> 0); live tests on a specification and a letter

## 5. Routes and frontend

- [x] 5.1 Session routes with owner checks; verified by `test_router.py` and
      `test_redaction_routes.py`
- [x] 5.2 Frontend plugin: library widget, side panel (Rédaction, Aperçu),
      generated client (`make update-word-template-capability-api`); verified
      by the plugin's unit tests

## 7. Review and live-test fixes

- [x] 7.1 Document cache keyed by session and by the attachment's stored
      sha256: no conversation reads another's attached file, a reused short
      id never serves the old file; verified by
      `test_two_conversations_never_share_an_attached_document` and
      `test_a_reused_attachment_id_never_serves_the_old_file`
- [x] 7.2 One normalisation of model operations for the engine, the guards
      and the approval gate ("from_" read as "from", `remove` of one
      `address`, `set_text` to `write` only for a paragraph or a cell);
      verified by `test_operations_are_normalized_once_for_every_reader`
- [x] 7.3 ReAct only (the guards are ReAct middleware); `test_manifest_shape`
- [x] 7.4 A removal drops only real table-of-contents lines, not sentences
      cross-referencing the removed part;
      `test_removing_a_part_keeps_sentences_that_refer_to_it`
- [x] 7.5 A template table nested in a rewritten cell is guarded;
      `test_a_template_table_nested_in_a_cell_is_kept`
- [x] 7.6 The read mark is a log digest: an undo then an edit of the same
      length is a change; `test_an_undo_then_an_edit_of_the_same_length_is_still_a_change`
- [x] 7.7 Rédaction view keeps styles and links: another style starts its own
      segment, a paragraph with a link, footnote or content control is a
      `replace_text` place; `test_editing_a_chapter_keeps_its_styles_and_links`
- [x] 7.8 Frontend: Escape and "take theirs" never save the draft, the rich
      editor's draft starts when it opens, a failed upload is forgotten by the
      capabilities; `WordTemplatePlaceField.test.tsx` and
      `useChatAttachments.batch.test.tsx`
- [x] 7.9 Robustness: no approval for a batch that cannot parse; a store or
      replay failure is a tool result and a run stop ends the run; an applied
      batch always gets a reply; base choice and the model's undo refuse when
      the log changed or the last edit is the collaborator's. Frontend: only a
      409 with `seq` reloads, the pane pauses polling when hidden, deletions
      use the generated client
- [x] 7.11 Fields and table-of-contents paragraphs refused for the model;
      typed heading numbers dropped; the cover is part 0; written body text
      takes the template's explicit text colour; `test_operations.py`,
      `test_docmap.py`
- [x] 7.12 A planned edit is checked (guards + trial) before the approval
      gate and planned again once when refused; reads tracked per part; a
      final answer after an unapplied edit is asked again;
      `test_capability.py`
- [x] 7.13 An overlong chapter is read in pieces counted as one chapter; a
      field's refusal says Word computes it; today's date in every model
      call; `test_docmap.py`, `test_operations.py`, `test_capability.py`
- [x] 7.14 The session's template is named as already loaded in every model
      call; `test_attachments.py`
- [x] 7.15 Sub-headings of a level the template uses below its chapters run
      without approval; a bold line starting with a typed section number is
      refused; `test_capability.py`
- [x] 7.16 Bold-wrapped heading lines are headings; a heading line right
      under a template sub-heading of its level renames it; the model undoes
      only this turn's batches unless the collaborator asked (approval gate);
      one-cell frames are not blocks; `test_operations.py`,
      `test_capability.py`, `test_hitl.py`
- [x] 7.17 `remove_unused_template_parts` finds and removes the template's
      unused parts as one approved batch, offered once the wanted parts are
      written; `test_docmap.py`, `test_capability.py`, `test_hitl.py`
- [x] 7.18 Inactive headers/footers marked and refused, image-only
      paragraphs and moved values refused, the contents title kept;
      `test_operations.py`
- [x] 7.19 A heading line deeper than the template's sub-headings takes their
      deepest level; `test_capability.py`
- [x] 7.20 In a template with sub-headings, a bold line followed by content
      becomes a sub-heading; the part shown in the chat is in the
      conversation's language and holds only what the document holds;
      `test_capability.py`
- [x] 7.21 `move` operation (gated, alone in its batch); a typed number alone
      on a numbered heading is refused with the way to move; written
      paragraphs never take a caption style; `test_operations.py`,
      `test_hitl.py`
- [x] 7.22 A typed numbered title in a `set_text` or a write becomes a
      sub-heading; a move to its own place is refused; `test_operations.py`,
      `test_capability.py`
- [x] 7.23 `toc.py` rebuilds the table of contents' lines after each batch
      (numbers, text, order, line style per level); the download sets
      `updateFields` so Word recomputes page numbers; `test_toc.py`
- [x] 7.24 Chapter headings are never written over; titles numbered at two
      depths keep their hierarchy; colon-ended bold labels introducing a list
      stay bold; `test_operations.py`, `test_capability.py`
- [x] 7.25 When the replan still plans another part, the model is asked once
      more to end the turn, so the runtime's tool-call cap is not reached;
      `test_capability.py`
- [x] 7.26 Each edit's reply opens with the outline of the touched chapters;
      `test_capability.py`
- [x] 7.27 A heading line of any level sent over a heading renames it; a
      `set_text` changing nothing is dropped, refused only when nothing else
      is left; `test_operations.py`, `test_capability.py`
- [x] 7.28 A template whose analysed headings are all real titles has a set
      outline: a chapter keeps the template's sub-headings, new sub-chapters
      go through the approval gate (`changes_template`); the TOC is left
      untouched when its lines would not change; `test_capability.py`
- [x] 7.29 Batches holding a map note (`{blue}`...) are refused; the undo
      refusal says when to set `collaborator_asked`; written headings take
      the template's own heading style for their level, unstyled body text
      its main body style; the outline carries Word's heading numbers;
      `test_operations.py`, `test_capability.py`
- [x] 7.10 Conventions: keyboard characters in comments, docs and
      translations (model-facing formats unchanged); comments within three
      lines; unread fields removed; UI strings through i18n; no
      COMPONENT-UX.md entry (capability panels are not listed there).

## 6. Close-out

- [x] 6.1 Capability suite: 294 tests, ruff, format and basedpyright clean;
      fred-agents suite green
- [x] 6.4 `fred-performance-reviewer` run (2026-10-23): no blocking call on
      the event loop, docx work in worker threads, pod-local caches fall back
      safely
