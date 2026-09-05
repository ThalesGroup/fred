# === Business labels (descriptive, no access-control meaning) ===
#
# Pure normalization for label values. Kept pure so the contract (dedupe,
# trimming) is unit-testable without the metadata store or ApplicationContext.
# Assignment itself (add/remove) is no longer a Python list transform — it's
# a row insert/delete against `document_labels`, idempotent via the table's
# own primary key (see MetadataService.mutate_document_labels).


def normalize_labels(labels: list[str]) -> list[str]:
    """Trim, drop empties, and de-duplicate labels while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in labels:
        label = (raw or "").strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out
