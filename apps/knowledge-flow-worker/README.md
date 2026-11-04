# Knowledge Flow worker

Install this application independently with `make dev`. Run all four Temporal roles with `make run`, or one with `make run-worker-role ROLE=common|fast|medium|rich`. Configure it through `CONFIG_FILE` and `ENV_FILE`; credentials remain environment references.

The worker owns extraction, processing profiles, generation writes and Temporal workflows. It has no incoming HTTP security configuration. The API reads published artifacts and search projections from its own application and image.

Production: `make docker-build`; optional PDF implementation: `docker build -f apps/knowledge-flow-worker/dockerfiles/Dockerfile-prod --build-arg INSTALL_PYMUPDF=true -t knowledge-flow-worker-pymupdf:local .` from the repository root. PyMuPDF selection changes only worker configuration and images. Keep its dependency license notices.

Roles `common`, `extraction-fast`, `extraction-medium`, `extraction-rich`, workflow/activity names, queues and processing profiles are unchanged. Drain active ingestion before changing processor configuration. Schema and deployment validation remain to be performed by the developer.

## Imported email facts

The existing `.eml`/`.msg` converter writes the main message's subject, sender and
sent date into `metadata.json` (`identity.title/author/created`), with To/Cc and
external references in `extensions.email`. It parses once for text and facts;
attached messages cannot replace their parent's facts. The manager copies only
these descriptive fields into server-supplied metadata before committing, and
restores them from the verified predecessor artifacts before indexing, including
when an extraction activity's return value was lost. Names, uploader, UUID and
placement remain server-owned. No structured Bcc field is emitted.

Headers are optional: missing/invalid dates stay null; naive dates use the shared
UTC convention and explicit offsets are preserved. Unicode is preserved, controls
and whitespace folded, strings truncated on UTF-8 boundaries (subject 2,048 bytes;
other strings 512). Each recipient list keeps the first 25 distinct normalized
values, with exact display-string deduplication. Empty strings become null (or no
list entry). These limits keep the structured facts below 64 KiB; they do not
remove occurrences in the body or original. Existing body/attachment limits and
encrypted-mail rejection are unchanged.

New processing and retries of failed attempts produce these facts. Old published
results remain unchanged; no backfill runs. The current Control Plane does not
allow replacing an original, editing these facts or reprocessing a successful
attempt. If those operations are added later, each newly published generation
must replace all its extracted values, including absences, without overwriting
user-edited catalog values. See the [operator note](../../deploy/release-notes/changes/weaver-email-metadata.md)
for deployment and validation boundaries.
