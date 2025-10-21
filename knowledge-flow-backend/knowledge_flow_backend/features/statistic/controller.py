import logging
from fastapi import APIRouter, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.statistic.utils import clean_json
from knowledge_flow_backend.features.statistic.structures import (
    SetDatasetRequest,
    DetectOutliersRequest,
    PlotHistogramRequest,
    PlotScatterRequest,
    TrainModelRequest,
    PredictRowRequest,
    SaveModelRequest,
    LoadModelRequest,
    DetectOutliersMLRequest,
    PCARequest,
)
from knowledge_flow_backend.features.statistic.service import StatisticService
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.utils import sanitize_sql_name

logger = logging.getLogger(__name__)


class StatisticController:
    def __init__(self, router: APIRouter):
        self.service = StatisticService()
        self.store = ApplicationContext.get_instance().get_csv_input_store()

        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get("/stat/list_datasets", tags=["Statistic"], summary="View the available datasets", operation_id="list_datasets")
        async def list_datasets(_: KeycloakUser = Depends(get_current_user)):
            try:
                return f"available_datasets:{self.store.list_tables()}"
            except Exception as e:
                logger.exception("Failed to get head")
                raise HTTPException(500, str(e))

        @router.post("/stat/set_dataset", tags=["Statistic"], summary="Select a dataset", operation_id="set_dataset")
        async def set_dataset(request: SetDatasetRequest, _: KeycloakUser = Depends(get_current_user)):
            try:
                dataset = self.store.load_table(sanitize_sql_name(request.dataset_name))
                self.service.set_dataset(dataset)
                return f"{request.dataset_name} is loaded."
            except Exception as e:
                logger.exception(f"Failed to set the dataset as {request.dataset_name}")
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