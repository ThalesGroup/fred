# Tasks - Let capability plugins keep - and forget - files attached in the chat

Built before this change was written; tasks record what exists and how it is
verified.

## 1. The hook

- [x] 1.1 Add `ChatAttachmentContext`, `ChatAttachmentForget` and the optional
      `onChatAttachment` plugin field; verified by the type-check of the
      changed files and their imports
- [x] 1.2 Add the handler registry keyed by capability id; verified by
      `chatAttachmentRegistry.test.ts`
- [x] 1.3 Call the active capabilities' handlers from `useChatAttachments`, in
      parallel with ingestion and before the attachment turns ready; verified
      by `useChatAttachments.batch.test.tsx`

## 2. Forget on removal

- [x] 2.1 Keep each handler's forget callback per attachment and call it on
      removal (chip and persisted-attachment paths); verified by "asks the
      capability to forget a file the user removes"
- [x] 2.2 Apply a removal that lands before the handler answered; verified by
      "forgets it too when the removal lands before the capability answered"
- [x] 2.3 `word_template` returns forget callbacks for Word files and images;
      verified by `sessionAttachments.test.ts` (DELETE call, 409 kept quietly)

## 3. Multi-file asset slots

- [x] 3.1 `FileDropzone` multi-file mode and `disabled` state, exactly one of
      `onFile` / `onFiles`; verified by `FileDropzone.test.tsx`
- [x] 3.2 Stage several files per slot and send them in order on save;
      verified by the agent-form save path used by the `word_template` library

## 4. Close-out

- [x] 4.1 Update `docs/swift/capabilities/AUTHORING.md` and the
      `add-fred-capability` skill for the forget callback (they describe the
      hook without it)
