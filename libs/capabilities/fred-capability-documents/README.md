# fred-capability-documents

Fred agent capabilities over the Knowledge Flow document ports. One package,
one `fred.capabilities` entry point per capability, each admin-gated and
independently grantable by a team admin.

## Capabilities

- **`document_summarize`** — on-demand summary of one document
  (`RuntimeServices.document_summarize`).
- **`document_similarity`** — targeted document-to-document comparison
  (`RuntimeServices.document_similarity`).
- **`document_label_search`** — exhaustive, paginated resolution of a
  business label to documents (`RuntimeServices.document_tree`).
- **`document_verbatim`** — verbatim, paginated read of one document
  (`RuntimeServices.document_markdown`).
- **`document_extract`** — exhaustive extraction from one document
  (`RuntimeServices.document_extraction`).

`document_read_common.py` holds what the reading pair and the error shaping
share. The capabilities reach the platform only through the typed fred-sdk
ports — no URL, credential or client lives here.

## Registration

Installing this package *is* the registration: the fred-agents pod
auto-discovers each capability at boot via the `fred.capabilities` entry
points declared in `pyproject.toml`. Nothing else to wire.

Authoring guide: `docs/swift/capabilities/AUTHORING.md`.
