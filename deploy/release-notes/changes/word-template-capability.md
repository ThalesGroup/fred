---
schema: 1
title: "Prepare Word libraries and edit documents from chat"
impact: minor
configuration: production
configuration_reason: "The agent pod's existing capability preparation worker and Knowledge Flow connection must be configured; text analysis uses the organization's admitted model and Knowledge Flow credential bindings."
---

## Applicability

Fresh Weaver installations including `fred-capability-word-template`. Editors can
select a library of up to eight Word templates for an agent. Organization Owners
manage common libraries separately for each logical pod. Documents support chat
editing, approval for structural changes, undo, images, PDF preview and DOCX export.

## Prerequisites

The existing Temporal preparation worker, Control Plane original storage and
Knowledge Flow connection must be available. Knowledge Flow must attest the
organization's admitted text model through its existing inference credential
bindings. PDF preview uses the image's LibreOffice installation.

## Configuration

Register the pod's workload identity in Control Plane's existing capability
preparation worker configuration. No global model or new capability-specific
worker identity is configured. Enable Word for the intended organization/spaces.

## Upgrade

Only fresh installations are supported. Apply the immutable Control Plane migration
chain, including Word original slots and marketplace library ownership. Run the
usual pod migration command, `python -m fred_runtime migrate`; Word owns its
`cap_word_template_alembic_version` history, headed by `w9b2c3d4e5f6`.

Each file uses the existing CP receipt, quota, Temporal delivery and cleanup
lifecycle. Organization replacements retain the effective predecessor until the
new file is prepared. Word marketplace snapshots include the library originals.

## Validation

Check the migration inventory and component quality checks. Operational reception
still requires uploading a library, observing preparation, creating a document,
editing and exporting it, then replacing/removing originals. Source compilation
alone does not establish a deployed end-to-end result.

## Rollback

Do not downgrade capability tables to recover a deployment: that deletes session
documents, logs and images. Use the installation's normal recovery procedure with
an appropriate data backup.

## Limitations

Session images and snapshots remain in the capability database. Prepared originals
use the pod's object namespace. As with PowerPoint, an object write whose outcome
is unknown prevents cleanup confirmation until resolved; retirement never claims
that uncertain writes have been erased. Chat Word attachments remain ordinary
retrieval sources, separate from template libraries.
