## 1. Implementation

- [x] 1.1 Knowledge Flow keeps the bounded preview at fast ingest, serves it to its uploader on `GET /fast/preview/{document_uid}` (404 otherwise, 503 when busy) and deletes it with the fast delete. Verify with `test_attachment_preview.py`, `test_fast_lite_image_processor.py`.
- [x] 1.2 Runtime middleware adds the 5 newest images to the first human message of every vision call, fetched once per turn, with the fallbacks of the spec. Verify with `test_react_vision_attachments.py`.
- [x] 1.3 Omit the vision description of an image sent as pixels, keep SVG facts; update the prompt rules. Verify with `test_react_vision_attachments.py`, `test_react_prompting.py`.
- [x] 1.4 Frontend stops sending data URLs and lists a just-persisted image before the list refetch; Knowledge Flow client regenerated. Verify with `useChatAttachments*.test.*`.
- [x] 1.5 Preview route in `authz-endpoint-matrix.yaml`.

## 2. Docs and review

- [x] 2.1 `RUNTIME-EXECUTION-CONTRACT.md` §8 entry, Knowledge Flow `DESIGN.md`, migration note.
- [ ] 2.2 Reviewers settle the preview route's `pending_review` authz entry.
- [x] 2.3 `fred-performance-reviewer` on the per-turn fetch.

## 3. Close-out

- [ ] 3.1 Update the capability Purpose (it still says answers come from the description only) and archive, after owner review.
