---
schema: 1
title: "Organization model catalogues, metadata complements and corpus reconstruction"
impact: minor
configuration: production
configuration_reason: "Optional managed catalogues require the same encryption key in trusted inference workloads, using existing chart extraEnvVars. File-configured sources retain their credential bindings."
---
## Applicability

Fresh Weaver installations using the current immutable migration chain. This does
not provide an upgrade from Swift or an older incompatible Weaver baseline.

## Prerequisites

Apply Control Plane migration 0054 through the normal initialization
command or deployment hook. Knowledge Flow's common worker must be running for
corpus reconstruction and retired-store cleanup.

## Configuration

For optional organization-managed catalogues, provision one random 32-byte key,
base64 encoded, as `MODEL_CATALOG_ENCRYPTION_KEY` in Control Plane, Agent Pod,
Knowledge Flow API and its common worker. Use an existing Secret reference in
`applications.<component>.extraEnvVars`, and the Agent Pod chart's `extraEnvVars`.
The charts reference this optional key in `fred-secrets` by default, reusing
`extraEnvVars`; override those entries for another Secret name. No plaintext key
belongs in chart values.
Retain this key with backups of the catalogue credentials. File source bindings
and declared inventories continue to work without it.

## Upgrade

Initialize the supported schema before starting the matching Control Plane and
roll out the matching Python workloads and generated frontend client. No catalogue
or reindex operation starts automatically. An organization Owner registers and
refreshes a named catalogue, then grants model permissions explicitly.

## Validation

Confirm the organization Owner sees separate catalogue tabs, URL and refresh;
other organizations cannot access them, and responses never return provider tokens.
Verify that catalogue tabs switch the list, the separate edit button exposes all
settings with immutable fields disabled, and YAML catalogues remain read-only.
Use Teams and users to restrict a model for one team or all personal spaces;
confirm that new admissions respect both that position and local restrictions.
An explicit enable must never bypass the organization's permitted model list.
Select an authorized model for agent design, then generate a draft from the agent
form. Prompt settings take precedence over the catalogue's creation model;
when neither is set, drafting follows the space default. Verify a local restriction can
block a dedicated choice. The form keeps the proposal editable before saving.
Set missing metadata, refresh, and verify provider facts retain priority. Confirm
reindexing shows progress and resumes after a failed operation. Search uses the
previous model while new indexing waits, then switches to the replacement
before the old vectors are deleted.

## Rollback

Take a normal database backup before applying migrations. Do not rewrite migration
checksums or run an older incompatible binary against this schema. Restoring an
installation requires its matching database backup, binaries and encryption key.
An unfinished reconstruction keeps the previous corpus active. Resume it with
the matching worker or choose another available embedding model and rebuild.

## Limitations

Reconstruction reuses published chunk segmentation; it does not rerun extraction
or OCR. A smaller model input limit can require another embedding model. Removing
a catalogue used for embedding makes search/indexing unavailable until an available
model is selected and the corpus rebuilt; the UI warns before deletion. The files
remain stored. Re-enter provider tokens if the encryption key is lost or changed.
