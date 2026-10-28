## Why

Users want to drop mail files exported from Outlook (`.msg`) or another mail client (`.eml`) into a team library or a conversation. Neither suffix has a processor today, so the upload is refused. Tracked by #3306.

## What Changes

- One shared parser and two processors (library and chat attachment paths) for `.msg` and `.eml`: header block, body, attachment names, attached mails, and the text of document attachments.
- Subject, sender and sent date become title, author and created date.
- Processors declared in every ingestion profile and in the chart values; upload format list and Help Center updated (fr/en); migration note.

## Capabilities

### New Capabilities

- `email-ingestion`: how Knowledge Flow turns `.msg` and `.eml` files into markdown and metadata, bounded and sanitised.

### Modified Capabilities

None.

## Impact

Knowledge Flow processors and config, chart values, two translation strings and the Help Center. `python-oxmsg`, `beautifulsoup4` and `markdownify` become direct dependencies (already locked through `markitdown[all]`). No API, schema or data change.
