import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Literal

from app.features.statistic.service import StatisticService
from app.application_context import ApplicationContext

logger = logging.getLogger(__name__)

# Pydantic Models

class SetDatasetRequest(BaseModel):
    dataset_name : str

class DetectOutliersRequest(BaseModel):
    method: Literal["zscore", "iqr"] = "zscore"
    threshold: float = 3.0

class CorrelationsRequest(BaseModel):
    top_n: int = 5

class PlotHistogramRequest(BaseModel):
    column: str
    bins: int = 30

class PlotScatterRequest(BaseModel):
    x_col: str
    y_col: str

class TrainModelRequest(BaseModel):
    target: str
    features: List[str]
    model_type: Literal["linear", "random_forest"] = "linear"

class PredictRowRequest(BaseModel):
    row: Dict[str, Any]

class SaveModelRequest(BaseModel):
    name: str

class LoadModelRequest(BaseModel):
    name: str

import math

def clean_json(obj):
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None  # ou str(obj) si tu veux garder "NaN", "inf"
    return obj

# Controller Class

class StatisticController:
    def __init__(self, router: APIRouter):
        self.service = StatisticService()
        self.store = ApplicationContext.get_instance().get_csv_input_store()

        self._register_routes(router)

    def _register_routes(self, router: APIRouter):

        @router.get("/stat/list_datasets", tags=["Statistic"], summary="View the available datasets")
        async def list_datasets():
            try:
                return clean_json(f"available_datasets:{self.store.list_tables()}")
            except Exception as e:
                logger.exception("Failed to get head")
                raise HTTPException(500, str(e))
            
        @router.post("/stat/set_dataset", tags=["Statistic"], summary="Select a dataset")
        async def set_dataset(request: SetDatasetRequest):
            try:
                dataset = self.store.load_table(request.dataset_name)
                return self.service.set_dataset(dataset)
            except Exception as e:
                logger.exception(f"Failed to set the dataset as {request.dataset_name}")
                raise HTTPException(500, str(e))

        @router.get("/stat/head", tags=["Statistic"], summary="Preview the dataset")
        async def head(n: int = 5):
            try:
                return clean_json(self.service.head(n))
            except Exception as e:
                logger.exception("Failed to get head")
                raise HTTPException(500, str(e))

        @router.get("/stat/describe", tags=["Statistic"], summary="Describe the dataset")
        async def describe():
            try:
                return clean_json(self.service.describe_data())
            except Exception as e:
                logger.exception("Failed to describe dataset")
                raise HTTPException(500, str(e))

        @router.post("/stat/detect_outliers", tags=["Statistic"], summary="Detect outliers in numeric columns")
        async def detect_outliers(request: DetectOutliersRequest):
            try:
                return clean_json(self.service.detect_outliers(method=request.method, threshold=request.threshold))
            except Exception as e:
                logger.exception("Outlier detection failed")
                raise HTTPException(500, str(e))

        @router.get("/stat/correlations", tags=["Statistic"], summary="Get top correlations in the dataset")
        async def correlations(request: CorrelationsRequest):
            try:
                return clean_json(self.service.correlation_analysis(request.top_n))
            except Exception as e:
                logger.exception("Correlation analysis failed")
                raise HTTPException(500, str(e))

        @router.post("/stat/plot/histogram", tags=["Statistic"], summary="Plot histogram for a column")
        async def plot_histogram(request: PlotHistogramRequest):
            try:
                path = self.service.plot_histogram(column=request.column, bins=request.bins)
                return clean_json({"status": "success", "path": path})
            except Exception as e:
                raise HTTPException(400, str(e))

        @router.post("/stat/plot/scatter", tags=["Statistic"], summary="Plot scatter plot")
        async def plot_scatter(request: PlotScatterRequest):
            try:
                path = self.service.plot_scatter(request.x_col, request.y_col)
                return clean_json({"status": "success", "path": path})
            except Exception as e:
                raise HTTPException(400, str(e))

        @router.post("/stat/train", tags=["Statistic"], summary="Train a model")
        async def train_model(request: TrainModelRequest):
            try:
                training_results = self.service.train_model(request.target, request.features, model_type=request.model_type)
                return clean_json({"status": "success", "message": training_results})
            except Exception as e:
                logger.exception("Model training failed")
                raise HTTPException(400, str(e))

        @router.get("/stat/evaluate", tags=["Statistic"], summary="Evaluate last trained model")
        async def evaluate_model():
            try:
                return clean_json(self.service.evaluate_model())
            except Exception as e:
                logger.exception("Model evaluation failed")
                raise HTTPException(400, str(e))

        @router.post("/stat/predict_row", tags=["Statistic"], summary="Predict a single row of data")
        async def predict_row(request: PredictRowRequest):
            try:
                prediction = self.service.predict_from_row(request.row)
                return clean_json({"prediction": prediction})
            except Exception as e:
                logger.exception("Row prediction failed")
                raise HTTPException(400, str(e))

        @router.post("/stat/save_model", tags=["Statistic"], summary="Save trained model")
        async def save_model(request: SaveModelRequest):
            try:
                self.service.save_model(request.name)
                return {"status": "success", "message": f"Model saved as '{request.name}'."}
            except Exception as e:
                logger.exception("Model saving failed")
                raise HTTPException(400, str(e))
            
        @router.get("/stat/list_models", tags=["Statistic"], summary="List saved models")
        async def list_models():
            try:
                return clean_json({"models": self.service.list_models()})
            except Exception as e:
                logger.exception("Failed to list models")
                raise HTTPException(500, str(e))

        @router.post("/stat/load_model", tags=["Statistic"], summary="Load a previously saved model")
        async def load_model(request: LoadModelRequest):
            try:
                self.service.load_model(request.name)
                return clean_json({"status": "success", "message": f"Model '{request.name}' loaded."})
            except Exception as e:
                logger.exception("Model loading failed")
                raise HTTPException(400, str(e))
