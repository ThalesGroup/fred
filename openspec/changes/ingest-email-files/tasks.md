## 1. Implementation

- [x] 1.1 Shared parser, HTML sanitising, encrypted detection, caps.
- [x] 1.2 Library and chat processors, default fast-text registry, attached mails, attachment text.
- [x] 1.3 Processors in every config file and the chart values (config model unchanged, no schema regenerates).
- [x] 1.4 Upload format list, Help Center (fr/en), processing guide, migration note.

## 2. Verification

- [x] 2.1 `pytest tests/processors/input/email_processor`, `make code-quality` and `make test` in knowledge-flow-backend and the frontend.
- [x] 2.2 Owner test on a local stack: `.msg` and `.eml` in a library and as chat attachments, attached mails, attachment text, a rich PPTX attachment.
- [x] 2.3 `openspec validate ingest-email-files --strict`.

`.msg` fixtures are synthetic (`fixtures/build_msg_fixtures.py`): no permissively licensed Outlook samples exist.
