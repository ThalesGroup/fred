---
schema: 1
title: "Expose extracted email facts in published document previews"
impact: none
configuration: none
configuration_reason: "Production worker profiles already route .eml and .msg; only the disposable test contract gains these formats."
no_action_reason: "Normal deployment of Control Plane, worker and frontend delivers optional generation metadata; no SQL migration, backfill or configuration change is required."
---
## Applicability

Weaver installations processing new `.eml` and `.msg` documents, in the library or
as conversation attachments. Port source: Swift #3317 at
`2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e`.

## Prerequisites

Use compatible Control Plane, Knowledge Flow worker and frontend images from this
release. Deploy Control Plane before enabling the frontend's conversation preview.
The ordinary Knowledge Flow backend remains compatible.

## Configuration

No production configuration or worker scheduling contract change. Production
fast/medium/rich profiles already include email. A deployment with an older
exported contract must follow the existing export/reload procedure to admit mail;
this release does not change already admitted profile snapshots. The regenerated
test fixture explicitly adds mail formats to support the new integration scenario.

## Upgrade

Deploy normally. New processing and retries of failed attempts publish subject,
sender, message date, To/Cc and message references in the existing metadata artifact.
The filename, import actor/date, UUID and access rules remain unchanged. The shared
preview offers an Email details tab. Conversation requests must include their
session and pass the current owner/space checks. No search/filter/thread feature
or structured Bcc field is added.

Previously published documents retain their artifacts and show no structured
email details until a new supported processing path produces them. There is no
backfill. This base refuses reprocessing an already successful attempt and original
replacement; do not promise a reprocess button or edit database rows to bypass it.
Future reprocessing must replace extracted facts with the new generation, including
nulls, without overwriting user edits.

## Validation

Targeted tests exercise the real converter, worker artifact serialization, Control
Plane publication and HTTP preview on disposable PostgreSQL/S3. Transport between
worker and Control Plane is simulated in this focused test; Temporal scheduling,
real embeddings, k3d and integration-platform UI remain separate validation.

On the developer-owned deployment, record image SHAs and the installed worker
contract. Upload the synthetic `.eml` and `.msg` fixtures to a library, then attach
them to a conversation. Open the existing preview and Email details tab; compare
subject/sender/date/To/Cc/references with the fixture and distinguish import date
and uploader. Confirm the text still includes supported attachment content and
nested mail facts do not replace the parent. Check an old published email, missing
headers, encrypted input, an unauthorized account/conversation and access after
revocation/deletion. No deployment or paid model call is run by this change.

## Rollback

Roll back the three images coherently using the normal procedure. Existing
artifacts remain valid and the original files are retained; older UI simply does
not expose the new details, and older Control Plane rejects attachment previews.
Drain processing when changing worker versions: an old extraction predecessor
without email facts remains supported, but may finish without those details.
No SQL history, generation pointer or published object should be rewritten.

## Limitations

Optional malformed headers are omitted/normalized by the producer, not grounds to
reject the whole email. Subject is capped at 2,048 UTF-8 bytes; other strings at
512, To/Cc at 25 distinct values each and structured facts at 64 KiB. Control Plane
rejects a nonconforming structured artifact before publication; total metadata
retains its existing 2 MiB limit. Header truncation is disclosed in the detail view.
No dedicated Bcc value is published; the body and original may still contain one.
The original extraction bounds, partial attachment extraction and encrypted-mail
rejection are unchanged. Deployment validation is still required before claiming
the journey in arc42.
