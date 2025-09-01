import logging
from typing import List, Optional, Dict, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Body
from pydantic import BaseModel

from app.features.statistic.service import StatisticService

logger = logging.getLogger(__name__)


# Models pour requêtes/réponses

class DeleteColumnRequest(BaseModel):
    column_name: str

class UpdateColumnRequest(BaseModel):
    column_name: str
    lambda_func: str  

class AddColumnRequest(BaseModel):
    new_column_name: str
    source_column_name: str
    lambda_func: str

class ABTestRequest(BaseModel):
    group_col: str
    metric_col: str
    alpha: float

class PlotHistogramRequest(BaseModel):
    column: str
    bins: int = 5

class PlotScatterRequest(BaseModel):
    x_col: str
    y_col: str

class TrainModelRequest(BaseModel):
    target_column: str
    feature_columns: List[str]
    model_type: Literal["linear_regression","random_forest"]
    model_params: Optional[Dict[str, Any]] = None

class PlotRequest(BaseModel):
    column: Optional[str]
    x_col: Optional[str]
    y_col: Optional[str]


class StatisticController:
    def __init__(self, router: APIRouter):
        self.service = StatisticService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):

        @router.get(
            "/stat/describe",
            tags=["Statistic"],
            summary="Describe dataset or specific columns"
        )
        async def describe(columns: Optional[List[str]] = Query(None, description="List of columns to describe")):
            try:
                return self.service.describe_data(columns)
            except Exception as e:
                logger.exception("Failed to describe data")
                raise HTTPException(status_code=500, detail=str(e))
            
        @router.delete(
            "/stat/delete_column",
            tags=["Statistic"],
            summary="Delete a column from the dataset"
        )
        async def delete_column(request: DeleteColumnRequest):
            try:
                self.service.delete_column(request.column_name)
                return {"status": "success", "message": f"Column '{request.column_name}' deleted."}
            except Exception as e:
                logger.exception("Failed to delete column")
                raise HTTPException(status_code=400, detail=str(e))

        @router.post(
            "/stat/update_column",
            tags=["Statistic"],
            summary="Update a column applying a transformation function"
        )
        async def update_column(request: UpdateColumnRequest):
            try:
                func_str = request.lambda_func
                self.service.update_column(request.column_name, func_str)
                return {"status": "success", "message": f"Column {request.column_name} updated with function: {func_str}."}
            except Exception as e:
                logger.exception("Failed to update column")
                raise HTTPException(status_code=400, detail=str(e))

        @router.post(
            "/stat/add_column",
            tags=["Statistic"],
            summary="Add a new column from existing column"
        )
        async def add_transformed_column(request: AddColumnRequest):
            try:
                self.service.add_transformed_column(request.new_column_name, request.source_column_name, request.lambda_func)
                return {"status": "success", "message": f"Column {request.source_column_name} transformed with {request.lambda_func} added to {request.new_column_name}."}
            except Exception as e:
                logger.exception("Failed to add column")
                raise HTTPException(status_code=400, detail=str(e))

        @router.post(
            "/stat/ab_test",
            tags=["Statistic"],
            summary="Perform A/B test between two groups"
        )
        async def ab_test(request: ABTestRequest):
            try:
                result = self.service.ab_test(request.group_col, request.metric_col, request.alpha)
                return result
            except Exception as e:
                logger.exception("A/B test failed")
                raise HTTPException(status_code=400, detail=str(e))

        @router.post(
            "/stat/train_model",
            tags=["Statistic"],
            summary="Train a ML model on dataset"
        )
        async def train_model(request: TrainModelRequest):
            try:
                result = self.service.train_model(
                    target_column=request.target_column,
                    feature_columns=request.feature_columns,
                    model_type=request.model_type,
                    model_params=request.model_params
                )
                return result
            except Exception as e:
                logger.exception("Model training failed")
                raise HTTPException(status_code=400, detail=str(e))

        @router.post("/stat/plot_histo", tags=["Statistic"])
        async def plot_histogram(request: PlotHistogramRequest):
            try:
                path = self.service.plot_histogram(request.column, request.bins)
                return {"status": "success", "path": path}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.post("/stat/plot_scatter", tags=["Statistic"])
        async def plot_scatter(request: PlotScatterRequest):
            try:
                path = self.service.plot_scatter(request.x_col, request.y_col)
                return {"status": "success", "path": path}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
            
    
