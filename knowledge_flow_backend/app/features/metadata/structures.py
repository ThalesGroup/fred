
from typing import Any, Dict, List

from pydantic import BaseModel


class GetDocumentsMetadataResponse(BaseModel):
    """
    Response model for the endpoint that returns several documents' metadata.

    The 'documents' field is a list of flexible dictionaries,
    allowing for various document metadata structures.
    """

    status: str
    documents: List[Dict[str, Any]]


class DeleteDocumentMetadataResponse(BaseModel):
    """
    Response model for deleting a document's metadata.
    """

    status: str
    message: str


class GetDocumentMetadataResponse(BaseModel):
    """
    Response model for retrieving metadata for a single document.

    The 'metadata' field is a dictionary with arbitrary structure.
    """

    status: str
    metadata: Dict[str, Any]


class UpdateRetrievableRequest(BaseModel):
    """
    Request model used to update the 'retrievable' field of a document.
    """

    retrievable: bool


class UpdateDocumentMetadataResponse(BaseModel):
    """
    Response model for updating fields of a metadata.
    """

    status: str
    metadata: Dict[str, Any]

class UpdateDocumentMetadataRequest(BaseModel):
    description: str | None = None
    title: str | None = None
    domain: str | None = None
    tags: list[str] | None = None