"""The wire contract for team-wiki 409s: a stale-base write's body always
validates against WikiConflictResponse, and a 409 for any other reason
(duplicate title, has-children, ...) carries `detail` only, so a client can
tell the two apart from the body rather than trusting every 409 alike."""

from __future__ import annotations

import json

import pytest
from control_plane_backend.team_wiki.api import register_exception_handlers, router
from control_plane_backend.team_wiki.schemas import WikiConflictResponse
from control_plane_backend.team_wiki.service import WikiConflictError, WikiRequestError
from fastapi import FastAPI


def _handlers() -> dict[type[Exception], object]:
    app = FastAPI()
    register_exception_handlers(app)
    return app.exception_handlers  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_stale_write_409_validates_against_the_canonical_model() -> None:
    handler = _handlers()[WikiConflictError]
    response = await handler(None, WikiConflictError("rev-current", "current text"))  # type: ignore[misc]

    assert response.status_code == 409
    body = json.loads(response.body)
    # Round-trips through the model consumers actually import — a body that
    # merely happened to look right would still fail this.
    parsed = WikiConflictResponse(**body)
    assert parsed.current_revision_id == "rev-current"
    assert parsed.current_content_md == "current text"


@pytest.mark.asyncio
async def test_duplicate_title_409_carries_no_revision_fields() -> None:
    handler = _handlers()[WikiRequestError]
    exc = WikiRequestError(
        "A page with this title already exists at the same level.", http_status=409
    )
    response = await handler(None, exc)  # type: ignore[misc]

    assert response.status_code == 409
    body = json.loads(response.body)
    assert body == {"detail": str(exc)}
    assert "current_revision_id" not in body
    assert "current_content_md" not in body


def test_openapi_schema_exposes_the_conflict_model_on_the_write_routes() -> None:
    # A bare app carrying only this router — not control_plane_backend.main's
    # create_app(), which wires live-infra clients (OpenSearch, Postgres, ...)
    # that offline tests must not touch.
    app = FastAPI()
    app.include_router(router, prefix="/control-plane/v1")
    schema = app.openapi()
    assert "WikiConflictResponse" in schema["components"]["schemas"]

    for path, method in [
        ("/control-plane/v1/teams/{team_id}/wiki/pages/{page_id}/content", "put"),
        ("/control-plane/v1/teams/{team_id}/wiki/rules", "put"),
        ("/control-plane/v1/teams/{team_id}/wiki/proposals/edit", "post"),
        (
            "/control-plane/v1/teams/{team_id}/wiki/proposals/{proposal_id}/publish",
            "post",
        ),
    ]:
        response_409 = schema["paths"][path][method]["responses"]["409"]
        ref = response_409["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("WikiConflictResponse"), f"{method.upper()} {path}"

    # The duplicate-title-only routes must NOT claim the revision-conflict shape.
    create_409 = schema["paths"]["/control-plane/v1/teams/{team_id}/wiki/pages"][
        "post"
    ]["responses"]["409"]
    assert "content" not in create_409
