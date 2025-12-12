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

import logging

from fastapi import APIRouter, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user

from .service import ModelService
from .types import ProjectRequest, ProjectResponse, StatusResponse, TrainResponse

logger = logging.getLogger(__name__)


class ModelController:
    def __init__(self, router: APIRouter):
        self.service = ModelService()

        @router.post(
            "/models/umap/{tag_id}/train",
            tags=["Models"],
            response_model=TrainResponse,
            summary="Train a parametric (or fallback) UMAP model in 3D for a tag",
        )
        async def train_umap(tag_id: str, user: KeycloakUser = Depends(get_current_user)) -> TrainResponse:
            try:
                meta = await self.service.train_umap_for_tag(user, tag_id)
                return TrainResponse(**meta)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except RuntimeError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except Exception as e:
                logger.exception("Unexpected error while training UMAP: %s", e)
                raise HTTPException(status_code=500, detail="Internal error while training the model")

        @router.get(
            "/models/umap/{tag_id}",
            tags=["Models"],
            response_model=StatusResponse,
            summary="Get the status of a UMAP model for a tag",
        )
        def model_status(tag_id: str, user: KeycloakUser = Depends(get_current_user)) -> StatusResponse:
            # user kept for parity and future permission checks
            try:
                meta = self.service.get_model_status(tag_id)
                return StatusResponse(**meta)
            except Exception as e:
                logger.exception("Failed to get UMAP model status: %s", e)
                raise HTTPException(status_code=500, detail="Error while retrieving the model status")

        @router.post(
            "/models/umap/{tag_id}/project",
            tags=["Models"],
            response_model=ProjectResponse,
            summary="Project documents or vectors into 3D using the tag's UMAP model",
        )
        async def project(tag_id: str, req: ProjectRequest, user: KeycloakUser = Depends(get_current_user)) -> ProjectResponse:
            try:
                with_clustering = req.with_clustering or False
                graph_points = await self.service.project(user, tag_id, document_uids=req.document_uids, with_clustering=with_clustering)
                return ProjectResponse(graph_points=graph_points)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Failed to project with UMAP model: %s", e)
                raise HTTPException(status_code=500, detail="Error during projection")

        @router.delete(
            "/models/umap/{tag_id}",
            tags=["Models"],
            summary="Delete the UMAP model and its artifacts for a tag",
        )
        def delete_model(tag_id: str, user: KeycloakUser = Depends(get_current_user)) -> dict:
            try:
                return self.service.delete_model(tag_id)
            except Exception as e:
                logger.exception("Failed to delete UMAP model: %s", e)
                raise HTTPException(status_code=500, detail="Error while deleting the model")
