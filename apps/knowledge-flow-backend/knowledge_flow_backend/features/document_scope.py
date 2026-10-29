# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Document authority received only after the existing delegated authentication."""

from fastapi import Depends, FastAPI, Header, HTTPException
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_core.security.delegation import AssertedUser
from pydantic import ValidationError

from knowledge_flow_backend.security.weaver_admission import delegated_person


def document_access_context(
    person: AssertedUser = Depends(delegated_person),
    raw: str | None = Header(default=None, alias=DOCUMENT_CONTEXT_HEADER),
) -> DocumentAccessContext:
    # Optional at the framework boundary only, to preserve the explicit 403.
    if raw is None:
        raise HTTPException(status_code=403, detail="document_context_required")
    try:
        return DocumentAccessContext.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(status_code=400, detail="invalid_document_context") from None


def declare_document_context_openapi(app: FastAPI) -> None:
    """Describe the required JSON header without changing its 403/400 policy."""
    schema = app.openapi()
    context_schema = DocumentAccessContext.model_json_schema(ref_template="#/components/schemas/{model}")
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas.update(context_schema.pop("$defs", {}))
    schemas["DocumentScope"]["properties"]["selections"]["description"] = (
        "All clauses must match. An omitted or empty array adds no filter within the authorized space. No identifier-count cap is imposed here; HTTP server and proxy header limits still apply."
    )
    selection = schemas["DocumentSelection"]["properties"]
    selection["folder_ids"]["description"] = "Union of direct folder contents; not recursive. Omitted means no folders in this clause."
    selection["document_ids"]["description"] = "Explicit document UUIDs, unioned with this clause's folder contents. Omitted means no explicit documents. A clause with neither selects nothing."
    context_schema["description"] = "Server-bound space and document selection, accepted only from an authenticated delegated caller. Never inferred from model arguments."
    context_schema["properties"]["space_id"]["description"] = "Admitted turn's space UUID; KF checks the represented person's read permission."
    context_schema["properties"]["document_scope"]["description"] = "Intersection of selection clauses. Zero clauses add no filter; one empty clause selects nothing."
    schemas["DocumentAccessContext"] = context_schema
    schemas["KnowledgeFlowError"] = {
        "type": "object",
        "required": ["detail"],
        "properties": {"detail": {"type": "string", "description": "Error code or message. Do not assume all messages are stable machine-readable codes."}},
        "description": "Existing HTTP error envelope. Request-validation errors use HTTPValidationError instead.",
    }
    for model in schemas.values():
        if model.get("additionalProperties") is False:
            model["description"] = (model.get("description", "") + " Additional fields are rejected.").strip()
    for path in schema["paths"].values():
        for operation in path.values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "query" and parameter.get("name") in {"person", "run", "agent"}:
                    parameter["description"] = (
                        "Existing delegation grant identifier. Supply person, run and agent together for an admitted call. "
                        "Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations."
                    )
                if parameter.get("in") == "header" and parameter.get("name") == DOCUMENT_CONTEXT_HEADER:
                    parameter.pop("schema", None)
                    parameter.update(
                        required=True,
                        description=(
                            "One JSON object encoded directly as the header value (no base64 or URL encoding). "
                            "Required after delegated authentication: absent -> 403; invalid -> 400. "
                            "An explicit document_scope with no selections adds no filter to authorized published documents; "
                            "one empty selection admits no documents. Body and query cannot supply this context. "
                            "No Fred-specific byte cap; server/proxy limits can reject the request before these handlers."
                        ),
                        content={
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/DocumentAccessContext"},
                                "example": {"space_id": "00000000-0000-0000-0000-000000000001", "document_scope": {"selections": []}},
                            }
                        },
                    )

                    _describe_document_responses(operation)


def _describe_document_responses(operation: dict) -> None:
    """Document existing handlers only; this does not install an error policy."""
    tabular = "Tabular" in operation.get("tags", [])
    operation_id = operation["operationId"]
    descriptions = {
        "400": "Invalid JSON document context (invalid_document_context).",
        "401": "Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.",
        "403": "Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space.",
        "404": "Space not found (space_not_found).",
        "409": "Space pending deletion (space_pending_deletion).",
        "500": "Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.",
        "503": "Account status could not be checked. This is an unavailable decision, not a permission grant.",
    }
    if operation_id in {"get_document_markdown", "summarize_document", "extract_document"}:
        descriptions["404"] += " Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle."
    if operation_id in {"search_documents", "get_document_chunks"}:
        descriptions["503"] += " The document index may also be unavailable (corpus_not_ready)."
    if tabular:
        descriptions["400"] += " Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure."
        descriptions["403"] += " A requested document/dataset is outside the authorized selection."
        descriptions["404"] += " Required published dataset/catalog missing (dataset_not_found)."
        if operation_id != "list_tabular_documents":
            descriptions["503"] += " Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success."
            descriptions["504"] = "Tabular execution budget exceeded. Narrow datasets or query before retrying; cancellation of blocked I/O is best effort."
    responses = operation["responses"]
    for status, description in descriptions.items():
        response = {
            "description": description,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/KnowledgeFlowError"}}},
        }
        if status in {"403", "503"}:
            response["headers"] = {
                "X-Fred-Denial-Cause": {
                    "description": "Present for authorization/account errors only. Not emitted by every response with this status.",
                    "schema": {"type": "string", "enum": ["permission_refused", "account_suspended"] if status == "403" else ["account_status_unavailable"]},
                }
            }
        responses[status] = response
    responses["400"]["content"]["application/json"]["examples"] = {"invalid_context": {"value": {"detail": "invalid_document_context"}}}
    responses["403"]["content"]["application/json"]["examples"] = {"missing_context": {"value": {"detail": "document_context_required"}}}
    responses["422"]["description"] = "Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead."
