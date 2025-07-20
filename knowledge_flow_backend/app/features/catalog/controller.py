from app.common.structures import DocumentSourceConfig, PullSourceConfig
from fastapi import APIRouter, HTTPException, Query
from typing import List, Literal, Optional
from app.core.stores.metadata.base_catalog_store import PullFileEntry
from app.features.catalog.service import CatalogService, PullSourceNotFoundError
from pydantic import BaseModel

class DocumentSourceInfo(BaseModel):
    tag: str
    type: Literal["push", "pull"]
    provider: Optional[str] = None  # only for pull
    description: str
    catalog_supported: Optional[bool] = False

def provider_supports_catalog(provider: Optional[str]) -> bool:
    return provider in {"local_path"}

class CatalogController:
    
    
    def __init__(self, router: APIRouter):
        self.service = CatalogService()

        @router.get("/pull/catalog/files",
            tags=["Library Pull"],
            response_model=List[PullFileEntry],
            summary="List cataloged files (pull sources only)",
            description="Only works for sources of type `pull`. Use `/documents/sources` to discover available tags.")
        def list_catalog_files(
            source_tag: str = Query(..., description="The source tag for the cataloged files"),
            offset: int = Query(0, ge=0, description="Number of entries to skip"),
            limit: int = Query(100, gt=0, le=1000, description="Max number of entries to return"),
        ):
            try:
                return self.service.list_files(source_tag, offset=offset, limit=limit)
            except PullSourceNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.post("/pull/catalog/rescan/{source_tag}",
             tags=["Library Pull"],
             summary="Rescan a pull-mode source and update its catalog",
             description="Only supported for sources with `type: pull` and a compatible `provider`. Returns 404 if the source tag is unknown or not a pull-mode source.")

        def rescan_catalog_source(source_tag: str):
            try:
                files_found = self.service.rescan_source(source_tag)
                return {"status": "success", "files_found": files_found}
            except PullSourceNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except NotImplementedError as e:
                raise HTTPException(status_code=501, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Scan failed: {e}")

        @router.get("/documents/sources", 
                    tags=["Library Sources"], 
                    response_model=List[DocumentSourceInfo],
                    summary="List the configured document sources",
                    description=(
                        "Returns all configured document sources (push or pull).\n"
                        "Pull-mode sources may support catalog operations depending on the provider."
                    ))
        def list_document_sources():
            sources: dict[str, DocumentSourceConfig] = self.service.get_document_sources()

            result = []
            for tag, config in sources.items():
                entry = {
                    "tag": tag,
                    "type": config.type,
                    "description": config.description or "",
                    "provider": None,
                    "catalog_supported": False,
                }

                if config.type == "pull":
                    entry["provider"] = config.provider
                    entry["catalog_supported"] = provider_supports_catalog(config.provider)

                result.append(entry)

            return sorted(result, key=lambda x: x["tag"])
