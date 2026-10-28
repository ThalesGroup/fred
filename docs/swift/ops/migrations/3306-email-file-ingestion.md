---
schema: 1
title: "Ingest Outlook .msg and .eml mail files"
impact: minor
configuration: production
configuration_reason: "The Fred chart values add .msg and .eml entries to the fast and rich ingestion input processors and to the commented attachment_processors example; the configuration model and schemas are unchanged."
---
## Applicability

Existing Fred deployments. Impact is **minor** only for overlays that replace the
processor lists: they must add the entries below. Deployments using the bundled
chart lists get mail support with a normal deployment.

## Prerequisites

None. `python-oxmsg` (MIT), `beautifulsoup4` and `markdownify` become direct
Knowledge Flow dependencies; they were already installed, so the image is unchanged.

## Configuration

Reference: [the Fred chart values](../../../../deploy/charts/fred/values.yaml).
Overlays that replace `processing.profiles.<profile>.input_processors` (every
profile, API and workers) add:

```yaml
- suffix: ".msg"
  class_path: knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor.EmailMarkdownProcessor
- suffix: ".eml"
  class_path: knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor.EmailMarkdownProcessor
```

Overlays that set `attachment_processors` explicitly add:

```yaml
- suffix: ".msg"
  class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_email_processor.FastEmailProcessor
- suffix: ".eml"
  class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_email_processor.FastEmailProcessor
```

Without them, `.msg` and `.eml` uploads stay refused as before.

## Upgrade

1. Reconcile the processor lists above in any overlay that overrides them.
2. Deploy Fred normally; the rolling restart applies the lists.

## Validation

Upload a `.msg` and an `.eml` into a team library: the preview shows a From / To /
Cc / Date / Subject header, the body and the attachment names, and the author is
the sender. An encrypted mail fails once, with a message saying so.

## Rollback

Normal rollback; no data migration. Ingested mails stay ordinary markdown
documents; new mail uploads are refused again.

## Limitations

Caps are fixed in code: 25 MB per mail, 10 document attachments read per mail.
Images and archives keep their names only. LibreOffice conversions now stop after
300 s. Recipients are stored but not filterable; Bcc is never stored.
