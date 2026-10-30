## Decisions

1. **One parser, two thin processors.** `email_message_parser` returns a neutral result; `EmailMarkdownProcessor` (library) and `FastEmailProcessor` (chat) only adapt it.
2. **`.msg` via `python-oxmsg` (MIT), `.eml` via stdlib `email`.** `extract-msg` is excluded: GPL-3.0.
3. **Plain body first, sanitised HTML second.** Scripts, styles, embedded objects, forms, event handlers and non-`cid:` images are removed before `markdownify`; no network access. RTF-only `.msg` bodies give a "body not extractable" line (no RTF decompression).
4. **Metadata.** Title = subject (fallback: file stem), author = `Name <address>` (address alone without a name), created = sent date; `to`, `cc`, `message_id`, `in_reply_to` under `extensions.email`. Bcc is never stored. Stored labels are English.
5. **Encrypted mails fail permanently.** S/MIME or rights-protected messages raise `EncryptedEmailError(ValueError)`, which the extraction child classifies as non-retryable; signed-only mails are ingested.
6. **Attached mails are rendered after the parent,** depth 3, 20 per file; beyond, by name only. An unreadable attached mail becomes one line. The metadata stays the parent's.
7. **Document attachment text is appended, deduplicated by SHA-256.** PDF, DOC(X), PPT(X), ODT, TXT, MD, read with the fast text processors on every profile: in-process docling cannot be stopped on timeout, and rich would add vision calls. A failure gives one line.
8. **Caps, as code constants.** 25 MB per file (checked before parsing), 1,000,000 characters of bodies plus attachment text (60k on the chat path), 10 distinct attachment extractions, 15 MB and 100,000 characters each, 60 s per attachment, 300 s per LibreOffice conversion.

## Deferred gaps

Attachments as child documents, profile-based attachment extraction, images, threading, recipient filters, `.pst`/`.ost`, mail retention, configurable caps.
