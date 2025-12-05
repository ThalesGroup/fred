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
from .types import TrainResponse, StatusResponse, ProjectResponse, ProjectRequest

logger = logging.getLogger(__name__)


class ModelController:
    def __init__(self, router: APIRouter):
        self.service = ModelService()

        @router.post(
            "/models/umap/{tag_id}/train",
            tags=["Models"],
            response_model=TrainResponse,
            summary="Entraîner un modèle UMAP paramétrique (ou fallback) en 3D pour un tag",
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
                raise HTTPException(status_code=500, detail="Erreur interne lors de l'entraînement du modèle")

        @router.get(
            "/models/umap/{tag_id}",
            tags=["Models"],
            response_model=StatusResponse,
            summary="Obtenir le statut d'un modèle UMAP pour un tag",
        )
        def model_status(tag_id: str, user: KeycloakUser = Depends(get_current_user)) -> StatusResponse:
            # user kept for parity and future permission checks
            try:
                meta = self.service.get_model_status(tag_id)
                return StatusResponse(**meta)
            except Exception as e:
                logger.exception("Failed to get UMAP model status: %s", e)
                raise HTTPException(status_code=500, detail="Erreur lors de la récupération du statut du modèle")

        @router.post(
            "/models/umap/{tag_id}/project",
            tags=["Models"],
            response_model=ProjectResponse,
            summary="Projeter des documents ou vecteurs en 3D avec le modèle UMAP du tag",
        )
        async def project(
                tag_id: str,
                req: ProjectRequest,
                user: KeycloakUser = Depends(get_current_user)
        ) -> ProjectResponse:
            try:
                graph_points = await self.service.project(
                    user,
                    tag_id,
                    document_uids=req.document_uids,
                    with_clustering=req.with_clustering
                )
                return ProjectResponse(graph_points=graph_points)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.exception("Failed to project with UMAP model: %s", e)
                raise HTTPException(status_code=500, detail="Erreur lors de la projection")

        @router.delete(
            "/models/umap/{tag_id}",
            tags=["Models"],
            summary="Supprimer le modèle UMAP et ses artefacts pour un tag",
        )
        def delete_model(tag_id: str, user: KeycloakUser = Depends(get_current_user)) -> dict:
            try:
                return self.service.delete_model(tag_id)
            except Exception as e:
                logger.exception("Failed to delete UMAP model: %s", e)
                raise HTTPException(status_code=500, detail="Erreur lors de la suppression du modèle")