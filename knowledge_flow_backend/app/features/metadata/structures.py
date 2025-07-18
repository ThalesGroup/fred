# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from typing import Any, Dict, List

from app.common.structures import DocumentMetadata
from pydantic import BaseModel


class GetDocumentsMetadataResponse(BaseModel):
    """
    Response model for the endpoint that returns several documents' metadata.

    The 'documents' field is a list of flexible dictionaries,
    allowing for various document metadata structures.
    """

    status: str
    documents: List[DocumentMetadata]



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
    metadata: DocumentMetadata


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
    metadata: DocumentMetadata

class UpdateDocumentMetadataRequest(BaseModel):
    description: str | None = None
    title: str | None = None
    domain: str | None = None
    tags: list[str] | None = None