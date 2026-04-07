import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fred_core import KeycloakUser, get_current_user
from fred_core.common import OwnerFilter

from knowledge_flow_backend.features.statistic.service import StatisticService
from knowledge_flow_backend.features.statistic.structures import (
    DetectOutliersMLRequest,
    DetectOutliersRequest,
    LoadModelRequest,
    PCARequest,
    PlotHistogramRequest,
    PlotScatterRequest,
    PredictRowRequest,
    SaveModelRequest,
    SetDatasetRequest,
    TrainModelRequest,
)
from knowledge_flow_backend.features.statistic.utils import clean_json
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tag.structure import MissingTeamIdError

logger = logging.getLogger(__name__)


class StatisticController:
    def __init__(self, router: APIRouter):
        """
        Initialize the statistic controller with dataset-centric tabular access.

        Why this exists:
        - Statistic endpoints still work on pandas DataFrames, but datasets now
          come from authorized tabular artifacts instead of a global SQL store.

        How to use:
        - Instantiate once during API startup with the shared router.
        """

        self.service = StatisticService()
        self.tabular_service = TabularService()

        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get("/stat/list_datasets", tags=["Statistic"], summary="View the available datasets", operation_id="list_datasets")
        async def list_datasets(
            document_library_tags_ids: Annotated[
                list[str] | None,
                Query(description="Optional library tag IDs used to keep datasets inside selected libraries."),
            ] = None,
            owner_filter: Annotated[
                OwnerFilter | None,
                Query(description="Optional ownership scope: 'personal' or 'team'."),
            ] = None,
            team_id: Annotated[
                str | None,
                Query(description="Team ID, required when owner_filter is 'team'."),
            ] = None,
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Return the authorized dataset identifiers available to statistic tools.

            Why this exists:
            - Statistic workflows must only load datasets the current user can
              read through the document-level ReBAC rules.
            - Team/personal and library scope must match the active tabular
              area before a dataset is loaded into worker memory.

            How to use:
            - Call before `/stat/set_dataset` and pass one returned
              `document_uid`.
            - Reuse the same scope parameters as the tabular dataset listing
              endpoint when the caller is bound to one active area.
            """

            try:
                datasets = await self.tabular_service.list_datasets(
                    user,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
                return f"available_datasets:{[dataset.document_uid for dataset in datasets]}"
            except MissingTeamIdError as e:
                raise HTTPException(400, str(e))
            except Exception as e:
                logger.exception("Failed to list statistic datasets")
                raise HTTPException(500, str(e))

        @router.post("/stat/set_dataset", tags=["Statistic"], summary="Select a dataset", operation_id="set_dataset")
        async def set_dataset(request: SetDatasetRequest, user: KeycloakUser = Depends(get_current_user)):
            """
            Load one authorized dataset into the in-memory statistic service.

            Why this exists:
            - Statistical analysis remains stateful per API worker and expects a
              pandas DataFrame to be loaded before running analyses.
            - The selected dataset must stay inside the same team/personal and
              library scope as the caller's active area.

            How to use:
            - Send the dataset `document_uid` returned by `/stat/list_datasets`.
            """

            try:
                dataset = await self.tabular_service.read_dataset_frame(
                    user,
                    request.document_uid,
                    document_library_tags_ids=request.document_library_tags_ids,
                    owner_filter=request.owner_filter,
                    team_id=request.team_id,
                )
                self.service.set_dataset(dataset)
                return f"{request.document_uid} is loaded."
            except MissingTeamIdError as e:
                raise HTTPException(400, str(e))
            except Exception as e:
                logger.exception("Failed to set the dataset as %s", request.document_uid)
                raise HTTPException(500, str(e))

        @router.get("/stat/head", tags=["Statistic"], summary="Preview the dataset", operation_id="head")
        async def head(n: int = 5, _: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json(self.service.head(n))
            except Exception as e:
                logger.exception("Failed to get head")
                raise HTTPException(500, str(e))

        @router.get("/stat/describe", tags=["Statistic"], summary="Describe the dataset", operation_id="describe")
        async def describe(_: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json(self.service.describe_data())
            except Exception as e:
                logger.exception("Failed to describe dataset")
                raise HTTPException(500, str(e))

        @router.post("/stat/detect_outliers", tags=["Statistic"], summary="Detect outliers values in numeric columns", operation_id="detect_outliers")
        async def detect_outliers(request: DetectOutliersRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json(self.service.detect_outliers(method=request.method, threshold=request.threshold))
            except Exception as e:
                logger.exception("Outlier detection failed")
                raise HTTPException(500, str(e))

        @router.get("/stat/correlations", tags=["Statistic"], summary="Get top correlations in the dataset", operation_id="correlations")
        async def correlations(_: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json(self.service.correlation_analysis())
            except Exception as e:
                logger.exception("Correlation analysis failed")
                raise HTTPException(500, str(e))

        @router.post("/stat/plot/histogram", tags=["Statistic"], summary="Plot histogram for a column", operation_id="plot_histogram")
        async def plot_histogram(request: PlotHistogramRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                path = self.service.plot_histogram(column=request.column, bins=request.bins)
                return clean_json({"status": "success", "path": path})
            except Exception as e:
                raise HTTPException(400, str(e))

        @router.post("/stat/plot/scatter", tags=["Statistic"], summary="Plot scatter plot", operation_id="plot_scatter")
        async def plot_scatter(request: PlotScatterRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                path = self.service.plot_scatter(request.x_col, request.y_col)
                return clean_json({"status": "success", "path": path})
            except Exception as e:
                raise HTTPException(400, str(e))

        @router.post("/stat/train", tags=["Statistic"], summary="Train a model", operation_id="train_model")
        async def train_model(request: TrainModelRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                training_results = self.service.train_model(request.target, request.features, model_type=request.model_type)
                return clean_json({"status": "success", "message": training_results})
            except Exception as e:
                logger.exception("Model training failed")
                raise HTTPException(400, str(e))

        @router.get("/stat/evaluate", tags=["Statistic"], summary="Evaluate last trained model", operation_id="evaluate_model")
        async def evaluate_model(_: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json(self.service.evaluate_model())
            except Exception as e:
                logger.exception("Model evaluation failed")
                raise HTTPException(400, str(e))

        @router.post("/stat/predict_row", tags=["Statistic"], summary="Predict a single row of data", operation_id="predict_row")
        async def predict_row(request: PredictRowRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                prediction = self.service.predict_from_row(request.row)
                return clean_json({"prediction": prediction})
            except Exception as e:
                logger.exception("Row prediction failed")
                raise HTTPException(400, str(e))

        @router.post("/stat/save_model", tags=["Statistic"], summary="Save trained model", operation_id="save_model")
        async def save_model(request: SaveModelRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                self.service.save_model(request.name)
                return {"status": "success", "message": f"Model saved as '{request.name}'."}
            except Exception as e:
                logger.exception("Model saving failed")
                raise HTTPException(400, str(e))

        @router.get("/stat/list_models", tags=["Statistic"], summary="List saved models", operation_id="list_models")
        async def list_models(_: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json({"models": self.service.list_models()})
            except Exception as e:
                logger.exception("Failed to list models")
                raise HTTPException(500, str(e))

        @router.post("/stat/load_model", tags=["Statistic"], summary="Load a previously saved model", operation_id="load_model")
        async def load_model(request: LoadModelRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                self.service.load_model(request.name)
                return clean_json({"status": "success", "message": f"Model '{request.name}' loaded."})
            except Exception as e:
                logger.exception("Model loading failed")
                raise HTTPException(400, str(e))

        @router.get("/stat/test_distribution", tags=["Statistic"], summary="Test if column fits normal, uniform or exponential distribution", operation_id="test_distribution")
        async def test_distribution(column: str, _: KeycloakUser = Depends(get_current_user)):
            try:
                return clean_json(self.service.test_distribution(column))
            except Exception as e:
                logger.exception("Distribution test failed")
                raise HTTPException(400, str(e))

        @router.post("/stat/detect_outliers_ml", tags=["Statistic"], summary="Detect outliers using ML method", operation_id="detect_outliers_ml")
        async def detect_outliers_ml(request: DetectOutliersMLRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                outliers = self.service.detect_outliers_ml(features=request.features, method=request.method)
                return clean_json({"outliers": outliers})
            except Exception as e:
                logger.exception("ML-based outlier detection failed")
                raise HTTPException(400, str(e))

        @router.post("/stat/pca", tags=["Statistic"], summary="Run PCA on selected features", operation_id="run_pca")
        async def run_pca(request: PCARequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                result = self.service.run_pca(request.features, request.n_components)
                return clean_json(result)
            except Exception as e:
                logger.exception("PCA execution failed")
                raise HTTPException(400, str(e))
