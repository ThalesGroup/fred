from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl

from fred_core.processors.document_structures import DocumentMetadata


class LibraryProcessorDocument(BaseModel):
    """
    Payload for a single document when invoking a library-level processor.
    - preview_markdown is the full markdown content (preferred in stateless mode).
    - file_path is optional and only used for logging/title hints if provided.
    """

    preview_markdown: str = Field(..., description="Markdown preview content for the document.")
    metadata: DocumentMetadata
    file_path: Optional[str] = Field(default=None, description="Optional original path for reference/logs.")


class LibraryProcessorRequest(BaseModel):
    library_tag: Optional[str] = None
    documents: List[LibraryProcessorDocument]
    return_bundle_inline: bool = Field(default=True, description="If true, return bundle as base64 in response.")
    bundle_upload_url: Optional[HttpUrl] = Field(
        default=None, description="Optional presigned URL to upload the bundle instead of returning inline."
    )
    bundle_upload_headers: Dict[str, str] = Field(
        default_factory=dict, description="Optional headers to include when uploading the bundle."
    )


class LibraryProcessorBundle(BaseModel):
    status: str
    bundle_name: Optional[str] = None
    bundle_size_bytes: Optional[int] = None
    bundle_b64: Optional[str] = None
    upload_url: Optional[str] = None
    upload_status: Optional[str] = None
    error: Optional[str] = None
    library_tag: Optional[str] = None
    corpus_size: Optional[int] = None
    document_count: Optional[int] = None


class LibraryProcessorResponse(BaseModel):
    library_tag: Optional[str]
    bundle: LibraryProcessorBundle
    documents: List[DocumentMetadata]
