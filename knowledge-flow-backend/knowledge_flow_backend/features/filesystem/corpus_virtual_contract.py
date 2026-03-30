from __future__ import annotations

import re
from collections import Counter

from knowledge_flow_backend.common.document_structures import DocumentMetadata

CORPUS_LIBRARIES = "libraries"
CORPUS_DOCUMENTS = "documents"
DISPLAY_ID_SUFFIX_RE = re.compile(r"^(?P<label>.*)\s\[(?P<stable_id>[^\[\]/]+)\]$")


def corpus_display_label(raw_label: str | None, *, fallback: str) -> str:
    """
    Build a readable filesystem-safe label for one corpus entry.

    Why this exists:
    - legacy corpus storage uses opaque ids
    - the virtual corpus tree should expose business-readable names instead

    How to use:
    - pass the best human label available plus a stable-id fallback
    - use the result only for visible corpus path segments

    Example:
    - `corpus_display_label("Sales/Offers", fallback="tag-1")`
      returns `"Sales > Offers"`
    """

    collapsed = re.sub(r"\s+", " ", (raw_label or "").strip())
    cleaned = collapsed.replace("/", " > ").strip(" >")
    return cleaned or fallback


def friendly_corpus_segment(label: str | None, stable_id: str) -> str:
    """
    Render one readable corpus segment with a recoverable stable id suffix.

    Why this exists:
    - readable labels alone are not unique enough for path navigation
    - the suffix keeps path resolution stable without changing stored documents

    How to use:
    - call when exposing visible corpus labels
    - recover the suffix later with `extract_stable_id_from_display_segment(...)`

    Example:
    - `friendly_corpus_segment("Bid library", "1234")`
      returns `"Bid library [1234]"`
    """

    return f"{corpus_display_label(label, fallback=stable_id)} [{stable_id}]"


def extract_stable_id_from_display_segment(segment: str) -> str | None:
    """
    Extract the stable id suffix from one friendly corpus segment.

    Why this exists:
    - visible corpus paths may contain a trailing stable-id suffix
    - resolution helpers need to recover the underlying tag/document id

    How to use:
    - pass one visible segment such as `"Policies > HR [tag-1]"`

    Example:
    - `extract_stable_id_from_display_segment("report.pdf [doc-1]")`
      returns `"doc-1"`
    """

    match = DISPLAY_ID_SUFFIX_RE.match(segment.strip())
    if match is None:
        return None
    stable_id = match.group("stable_id").strip()
    return stable_id or None


def split_corpus_folder_path(full_path: str | None) -> tuple[str, ...]:
    """
    Split one canonical library path into virtual folder segments.

    Why this exists:
    - library tags store their hierarchy as one path string
    - the virtual corpus tree needs concrete folder segments to navigate

    How to use:
    - pass a tag full path such as `"CIR/TSN"`

    Example:
    - `split_corpus_folder_path("CIR/TSN")` returns `("CIR", "TSN")`
    """

    return tuple(seg.strip() for seg in (full_path or "").split("/") if seg.strip())


def corpus_tree_document_segments(
    docs: list[DocumentMetadata],
    *,
    sibling_folder_names: set[str],
) -> dict[str, str]:
    """
    Build visible document segments for one corpus folder.

    Why this exists:
    - folders should show plain document names whenever there is no ambiguity
    - collisions with sibling folder names or duplicate document names need a stable suffix

    How to use:
    - pass the documents that appear in one folder plus that folder's child names
    - use the returned mapping for listing and resolution within the same folder

    Example:
    - `corpus_tree_document_segments([doc], sibling_folder_names={"Archive"})`
    """

    base_names = {doc.document_uid: corpus_display_label(doc.document_name, fallback=doc.document_uid) for doc in docs}
    duplicate_counts = Counter(base_names.values())
    segments: dict[str, str] = {}
    for doc in docs:
        base_name = base_names[doc.document_uid]
        if duplicate_counts[base_name] > 1 or base_name in sibling_folder_names:
            segments[doc.document_uid] = friendly_corpus_segment(doc.document_name, doc.document_uid)
        else:
            segments[doc.document_uid] = base_name
    return segments
