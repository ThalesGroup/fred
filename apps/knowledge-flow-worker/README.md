# Knowledge Flow worker

Install this application independently with `make dev`. Run all four Temporal roles with `make run`, or one with `make run-worker-role ROLE=common|fast|medium|rich`. Configure it through `CONFIG_FILE` and `ENV_FILE`; credentials remain environment references.

The worker owns extraction, processing profiles, generation writes and Temporal workflows. The API reads published artifacts and search projections from its own application and image.

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

## Corpus reconstruction

The common worker runs the `ReindexCorpus` Temporal workflow. Each activity reads
one published chunk artifact and records progress after batches of at most 64
chunks. A failed operation can resume from its SQL checkpoint. The existing
cleanup worker removes retired stores after Control Plane activates the replacement.
See the
[Control Plane operation](../control-plane/README.md#rebuild-an-organizations-vector-corpus)
and its shared `MODEL_CATALOG_ENCRYPTION_KEY` provisioning for managed catalogues.

## Local chat dictation

Set `WHISPER_DICTATION_API_KEY` in the Control Plane and in the worker that serves
the `common` role. A configured worker listens at its `app.address` and `app.port`
(`127.0.0.1:8112` for local development). It verifies this key on its private
transcription endpoint and uses the installed Whisper model. Clips are processed
in memory for the duration of the request.

For a Helm deployment, enable the common worker's internal ClusterIP `service`,
set its `configuration.app.address` to `0.0.0.0`, and inject the key into both
deployments from the same Secret using `extraEnvVars`. Keep port 8112 private to
the Control Plane. Add the `whisper-local` source and binding from the
[host configuration](../control-plane/config/configuration_prod.yaml) to the
Control Plane's `configuration.platform`. Set both API roots to the internal
worker service, for example `http://knowledge-flow-worker:8112/v1`. Organization
assignment and model selection are described under [Chat dictation](../control-plane/README.md#chat-dictation).
