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
from .types import (
    ProjectRequest,
    ProjectResponse,
    ProjectTextRequest,
    ProjectTextResponse,
    StatusResponse,
    TrainResponse,
)

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
                meta = await self.service.train_for_tag(user, tag_id)
                return TrainResponse(**meta)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except RuntimeError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except Exception as e:
                logger.exception("Unexpected error while training UMAP: %s", e)
                raise HTTPException(status_code=500, detail="Internal error while training the model")

        @router.get(
            "/models/umap/{tag_uid}",
            tags=["Models"],
            response_model=StatusResponse,
            summary="Get the status of a UMAP model for a tag",
        )
        def model_status(tag_uid: str, user: KeycloakUser = Depends(get_current_user)) -> StatusResponse:
            # user kept for parity and future permission checks
            try:
                meta = self.service.get_model_status(tag_uid)
                return StatusResponse(**meta)
            except Exception as e:
                logger.exception("Failed to get UMAP model status: %s", e)
                raise HTTPException(status_code=500, detail="Error while retrieving the model status")

        @router.post(
            "/models/umap/{ref_tag_uid}/project",
            tags=["Models"],
            response_model=ProjectResponse,
            summary="Project documents or tags into other dimension using reduction models",
        )
        async def project(ref_tag_uid: str, req: ProjectRequest, user: KeycloakUser = Depends(get_current_user)) -> ProjectResponse:
            try:
                with_clustering = req.with_clustering or False
                graph_points = await self.service.project(
                    user,
                    ref_tag_uid,
                    document_uids=req.document_uids,
                    tags_uids=req.tag_uids,
                    with_clustering=with_clustering,
                )
                return ProjectResponse(graph_points=graph_points)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Failed to project with UMAP model: %s", e)
                raise HTTPException(status_code=500, detail="Error during projection")

        @router.delete(
            "/models/umap/{ref_tag_uid}",
            tags=["Models"],
            summary="Delete the UMAP model and its artifacts for a tag",
        )
        async def delete_model(ref_tag_uid: str, user: KeycloakUser = Depends(get_current_user)) -> dict:
            try:
                return await self.service.delete_model(ref_tag_uid)
            except Exception as e:
                logger.exception("Failed to delete UMAP model: %s", e)
                raise HTTPException(status_code=500, detail="Error while deleting the model")

        @router.post(
            "/models/umap/{ref_tag_uid}/project-text",
            tags=["Models"],
            response_model=ProjectTextResponse,
            summary="Project a text into 3D space using the tag's UMAP model",
        )
        async def project_text(ref_tag_uid: str, req: ProjectTextRequest, user: KeycloakUser = Depends(get_current_user)) -> ProjectTextResponse:
            try:
                graph_point = await self.service.project_text(ref_tag_uid, req.text)
                return ProjectTextResponse(graph_point=graph_point)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Failed to project text: %s", e)
                raise HTTPException(status_code=500, detail="Error during text projection")
