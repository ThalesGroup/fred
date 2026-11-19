# fred-capability-documents

Fred agent capabilities over the Knowledge Flow document ports. One package,
one `fred.capabilities` entry point per capability, each admin-gated and
independently grantable by a team admin.

## Capabilities

- **`document_summarize`** — on-demand summary of one document
  (`RuntimeServices.document_summarize`).
- **`document_similarity`** — targeted document-to-document comparison
  (`RuntimeServices.document_similarity`).
- **`document_verbatim`** — paginated read of one document's converted text
  (`RuntimeServices.document_markdown`).
- **`document_extract`** — criterion-based extraction from one document
  (`RuntimeServices.document_extraction`).

Extraction processes text windows and deduplicates matches. A failed window
fails the request through the existing error path; it is never a successful
no-match result. Input above 2,000,000 characters uses head and tail only,
with a warning even when no matches are found. Model extraction can omit items;
deduplication does not preserve occurrence counts.

`document_read_common.py` holds pagination and shared document-tool errors. The capabilities reach the platform only through the typed fred-sdk
ports — no URL, credential or client lives here.

## Registration

Installing this package *is* the registration: the fred-agents pod
auto-discovers each capability at boot via the `fred.capabilities` entry
points declared in `pyproject.toml`. Nothing else to wire.

Agent contracts: [fred-sdk](../../fred-sdk/README.md).
