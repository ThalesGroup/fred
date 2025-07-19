from fastapi import APIRouter, HTTPException, Query
from typing import List
from app.core.stores.metadata.base_catalog_store import PullFileEntry
from app.features.catalog.service import CatalogService, PullSourceNotFoundError

class CatalogController:
    def __init__(self, router: APIRouter):
        self.service = CatalogService()

        @router.get("/catalog/files", tags=["Catalog"], response_model=List[PullFileEntry])
        def list_catalog_files(
            source_tag: str = Query(..., description="The source tag for the cataloged files"),
            offset: int = Query(0, ge=0, description="Number of entries to skip"),
            limit: int = Query(100, gt=0, le=1000, description="Max number of entries to return"),
        ):
            try:
                return self.service.list_files(source_tag, offset=offset, limit=limit)
            except PullSourceNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.post("/catalog/rescan/{source_tag}", tags=["Catalog"], summary="Rescan a pull source and update catalog")
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
