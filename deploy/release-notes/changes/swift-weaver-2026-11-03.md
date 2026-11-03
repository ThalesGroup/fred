---
schema: 1
title: "Integrate Swift extraction and conversation fixes into Weaver"
impact: minor
configuration: production
configuration_reason: "Worker processing profiles add .msg and .eml processors; the bundled Helm profiles use the Weaver worker package. Frontend builds now use the repository Node 24 baseline."
---
## Applicability

Weaver deployments upgrading from the Rust control-plane reconstruction. This
change does not provide a migration from Swift's Python control plane.

## Prerequisites

Use the Node version in `.nvmrc` for frontend builds. Rebuild Python components
from their updated lockfiles, including Temporal 1.35.0 and worker pypdf 6.21.4.

## Configuration

The bundled worker and Helm processing profiles register `.msg` and `.eml` with
`knowledge_flow_worker.core.processors.input.email_processor.email_markdown_processor.EmailMarkdownProcessor`.
Add the same entries to custom worker profiles to enable mail extraction there.
The shared agent tool-call limit is now 100 per turn.

## Upgrade

Deploy the updated images using the normal Weaver procedure. No new SQLx or
Alembic migration is introduced. The Rust control plane retains document
admission, placement and publication ownership.

Regenerate the worker contract from the updated worker image and the effective
deployment configuration, using
`python -m knowledge_flow_worker.features.scheduler.export_contract --configuration <worker-configuration.yaml>`.
Install that export at the Control Plane's configured `worker_contract_file` and
reload it through the normal deployment procedure. Updating processor YAML or
worker images alone does not update an already loaded contract. Existing
processing records retain their captured profile settings.

## Validation

Import an unencrypted email and inspect its headers, body and supported attached
content. Check DOCX rejection and lightweight PPTX speaker-note/chart extraction.
Malformed input must fail permanently; memory pressure and transient I/O failures
must retain the existing worker retry policy and attempt limits. Navigate
away during a chat turn and return; inspect pending messages, Stop, human-input
holds and terminal status. Check that an authorized history read is still required
when reopening a conversation. Inspect structured MCP failure logs without exposing
private upstream errors to agents.

## Rollback

Restore the preceding images, processing configuration and matching worker contract together. Remove mail
processor entries from custom profiles before running a worker that lacks them.
Browser-memory pending messages do not survive a reload.

## Limitations

Global skill-policy/catalog evolution (#3342), generated/configurable conversation
titles (#3351), and authenticated DOCX author names (#3422) are deferred. Existing
Weaver skill behavior, titles and export-author behavior remain. Swift's removed
local Mistral catalog and retired Python services are not restored. Mail header
content from [#3317](https://github.com/ThalesGroup/fred/pull/3317) is extracted
into Markdown; structured email catalog fields remain follow-up work.
Background execution and indicators are browser-tab behavior, not durable queue
recovery across reloads or browser closure.

## Deferred Weaver implementation

The detailed [Weaver porting handoff](../../../WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md)
records the source commits, current owners, proposed implementation steps and
acceptance checks for each deferred or partial feature.

- [#3342](https://github.com/ThalesGroup/fred/pull/3342): design Rust-owned skill
  policy and trusted delivery to admitted turns before porting the catalog,
  invocation rules and load tracing together.
- [#3351](https://github.com/ThalesGroup/fred/pull/3351): add governed title-model
  selection and usage accounting, then title generation/events with manual-rename
  race protection.
- [#3422](https://github.com/ThalesGroup/fred/pull/3422): obtain export-author names
  from a trusted profile owner; Weaver's asserted identity has no profile names.
- [#3321](https://github.com/ThalesGroup/fred/pull/3321): register Mistral Large 4
  through the current Rust model catalog if needed; the deleted local catalog is
  not restored.

The merge records the upstream ancestry of deferred PRs. A later Swift merge
will not automatically reapply them; use these PR references for explicit ports.
The mail parser and fast-extraction helper are available in the worker, but this
does not restore Swift's retired synchronous chat-ingestion API. Any direct-chat
email support must use Weaver's current attachment admission and extraction flow;
the focused processor tests do not establish that integrated journey.

For [#3197](https://github.com/ThalesGroup/fred/pull/3197), internal MCP diagnostics
are retained while public errors keep Weaver's sanitization policy, including
the existing curated SQL 400 exception. Exposing raw upstream error bodies is
deliberately excluded, not deferred implementation work.
