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
import pickle
from typing import Any, Iterable, List, Sequence

import numpy as np

from knowledge_flow_backend.features.model.types import GraphPoint, Point3D, PointMetadata

logger = logging.getLogger(__name__)


# ---- Keys helpers ----
def model_key(tag_id: str) -> str:
    return f"{tag_id}/model.umap"


def meta_key(tag_id: str) -> str:
    return f"{tag_id}/meta.json"


# ---- Model persistence helpers ----
def save_umap_model(file_store: Any, namespace: str, storage_key: str, model: Any) -> None:
    """Persist a (U)MAP model into the configured file store under the given key."""
    try:
        model_bytes = pickle.dumps(model)
        file_store.put(
            namespace,
            storage_key,
            model_bytes,
            content_type="application/octet-stream",
        )
        logger.info("UMAP model saved to %s/%s", namespace, storage_key)
    except Exception:
        logger.exception("Failed to save UMAP model to %s/%s", namespace, storage_key)
        raise


def load_umap_model(file_store: Any, namespace: str, storage_key: str) -> Any:
    """Load a (U)MAP model from the file store.

    Raises FileNotFoundError if no bytes are found, or forwards underlying load errors.
    """
    model_bytes = file_store.get(namespace, storage_key)
    if not model_bytes:
        raise FileNotFoundError(f"No model found in the store for: {storage_key}")

    try:
        model = pickle.loads(model_bytes)
        logger.info("UMAP model loaded from %s/%s", namespace, storage_key)
        return model
    except Exception:
        logger.exception("Failed to load UMAP model from %s/%s", namespace, storage_key)
        raise


# ---- Projection payload helper ----
def build_points(projected: np.ndarray | Sequence[Sequence[float]], meta_vectors: Iterable[dict]) -> list[GraphPoint]:
    """Build the points payload matching the controller's ProjectResponse schema.

    projected: array-like of shape (n_samples, 3)
    meta_vectors: iterable of metadata dictionaries aligned with projected rows
    """
    graph_points: List[GraphPoint] = []
    Y = np.asarray(projected, dtype=np.float32)
    meta_list = meta_vectors if isinstance(meta_vectors, list) else list(meta_vectors)
    for i, p in enumerate(Y):
        point_3d = Point3D(
            x=float(p[0]),
            y=float(p[1]),
            z=float(p[2]),
            cluster=None,
        )
        point_metadata = PointMetadata(**meta_list[i])
        graph_point = GraphPoint(
            point_3d=point_3d,
            metadata=point_metadata,
        )
        graph_points.append(graph_point)
    return graph_points
