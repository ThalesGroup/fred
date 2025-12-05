from typing import Optional, List

from pydantic import BaseModel, Field


class TrainResponse(BaseModel):
    tag_id: str
    trained_at: str
    n_chunks: int
    n_documents: int
    model_kind: str
    embedding_model: Optional[str] = None


class StatusResponse(BaseModel):
    tag_id: str
    exists: bool
    trained_at: Optional[str] = None
    n_chunks: Optional[int] = None
    n_documents: Optional[int] = None
    model_kind: Optional[str] = None
    embedding_model: Optional[str] = None


class ProjectRequest(BaseModel):
    document_uids: Optional[List[str]] = Field(
        default=None,
        description='Documents UIDs list to project. If None, all chunks will be projected.'
    )
    with_clustering: Optional[bool] = Field(
        default=True,
        description='Whether to include clustering information in the projection.'
    )
    with_documents: Optional[bool] = Field(
        default=False,
        description='Whether to include documents text in the projection.'
    )

class Point2D(BaseModel):
    x: float
    y: float
    cluster: Optional[int] = None

class Point3D(BaseModel):
    x: float
    y: float
    z: float
    cluster: Optional[int] = None

class PointMetadata(BaseModel):
    chunk_order: Optional[int] = None
    chunk_uid: Optional[str] = None
    document_uid: Optional[str] = None
    text: Optional[str] = None

class GraphPoint(BaseModel):
    point_3d: Point3D
    point_2d: Optional[Point2D] = None
    cluster: Optional[str] = None
    metadata: Optional[PointMetadata] = None


class ProjectResponse(BaseModel):
    graph_points: List[GraphPoint]