from __future__ import annotations

import logging
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fred_core import KeycloakUser, get_current_user
from fred_core.processors import (
    LibraryDocumentInput,
    LibraryProcessorRequest,
    LibraryProcessorResponse,
)

from cir.cir_library_output_processor import CirLibraryOutputProcessor
from .config import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CIR Output Library Processor Service", version="0.1.0")
processor = CirLibraryOutputProcessor()
settings = get_settings()


def _require_user():
    if settings.security_enabled:
        return get_current_user

    async def _noop_user() -> None:
        return None

    return _noop_user


@app.get("/healthz", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


@app.post("/library/process", response_model=LibraryProcessorResponse, tags=["library"])
def process_library(
    body: LibraryProcessorRequest,
    user: KeycloakUser | None = Depends(_require_user()),
) -> LibraryProcessorResponse:
    """
    Build a HippoRAG graph/corpus for a library. Auth required.
    """
    logger.info(
        "HippoRAG process_library invoked by %s",
        getattr(user, "preferred_username", "anonymous"),
    )
    inputs: List[LibraryDocumentInput] = []
    for doc in body.documents:
        try:
            meta = doc.metadata
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse metadata payload: %s", exc)
            raise HTTPException(
                status_code=400, detail=f"Invalid metadata payload: {exc}"
            ) from exc
        inputs.append(
            LibraryDocumentInput(
                file_path=doc.file_path or "",
                metadata=meta,
                preview_markdown=doc.preview_markdown,
            )
        )

    try:
        updated, bundle_info = processor.process_library(
            inputs, library_tag=body.library_tag, request=body
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("HippoRAG processing failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return LibraryProcessorResponse(
        library_tag=body.library_tag,
        bundle=bundle_info,
        documents=updated,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
