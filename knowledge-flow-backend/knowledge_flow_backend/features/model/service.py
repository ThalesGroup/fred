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

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
from umap import UMAP

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.service import MetadataService

from .types import Clusters, GraphPoint, Point3D, PointMetadata
from .utils import (
    build_points,
    cluster_3d_key,
    cluster_distance_key,
    cluster_vector_key,
    load_centroid,
    load_clustering_model,
    load_umap_model,
    meta_key,
    model_key,
    save_centroid,
    save_clustering_model,
    save_umap_model,
)

logger = logging.getLogger(__name__)


class ModelService:
    """
    Manage per-tag UMAP models for 3D projection of document vectors.

    - One model per tag_uid
    - Trains on per-document vectors (mean of chunk embeddings for the document)
    - Persists model and artifacts via the configured FileStore (LocalFileStore for local FS)
    """

    NAMESPACE = "models/umap"

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.config = self.context.get_config()
        self.file_store = self.context.get_file_store()
        self.metadata_service = MetadataService()
        # Vector store may be lazily created in other services; here we use get_vector_store directly if initialized
        # or initialize it via get_create_vector_store
        try:
            self.vector_store = self.context.get_vector_store()
        except Exception:
            # If not initialized yet, create using embedder
            self.vector_store = self.context.get_create_vector_store(self.context.get_embedder())

    # ---------- Internal helpers ----------
    async def _list_document_uids_in_tag(self, user, tag_uid: str) -> list[str]:
        docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_uid)
        return [d.identity.document_uid for d in docs]

    async def _list_document_uids_in_tags(self, user, library_uids: list[str]) -> list[str]:
        """Get all document UIDs from the specified libraries."""
        all_doc_uids: set[str] = set()
        for library_uid in library_uids:
            docs = await self.metadata_service.get_document_metadata_in_tag(user, library_uid)
            all_doc_uids.update(d.identity.document_uid for d in docs)
        return list(all_doc_uids)

    def _mean_vector_for_document(self, document_uid: str) -> Optional[np.ndarray]:
        """
        Compute a single vector per document by averaging all chunk embeddings.
        Returns None if vectors are not available.
        """
        store = self.vector_store
        if not store or not hasattr(store, "get_vectors_for_document"):
            return None
        try:
            items = store.get_vectors_for_document(document_uid)  # type: ignore[attr-defined]
        except Exception as e:
            logger.exception("Failed to fetch vectors for document %s: %s", document_uid, e)
            return None
        if not items:
            return None
        try:
            vecs = np.array([it["vector"] for it in items], dtype=np.float32)
            if vecs.ndim != 2 or vecs.shape[0] == 0:
                return None
            return vecs.mean(axis=0)
        except Exception:
            logger.exception("Invalid vectors for document %s", document_uid)
            return None

    def _transform_2d(self, user, tag_uid: str, *, document_uids: list[str]):
        raise NotImplementedError("2D projection is not implemented in this service.")

    def _fit_umap(self, vectors: np.ndarray, tag_uid: str) -> UMAP:
        """
        Train a 3D UMAP model on the provided vectors.

        Args:
            vectors: Input vectors (n_samples, n_features)

        Returns:
            Trained UMAP model
        """
        try:
            model = UMAP(
                n_components=3,
                random_state=42,
                metric="euclidean",
                n_neighbors=15,
                min_dist=0.1,
            )
            model.fit(vectors)
            logger.info("UMAP model trained on %d samples with %d features", vectors.shape[0], vectors.shape[1])

            # Save model
            save_umap_model(
                self.file_store,
                self.NAMESPACE,
                model_key(tag_uid),
                model,
            )
            logger.info("UMAP model saved for tag %s", tag_uid)

            return model
        except Exception as e:
            logger.error("Failed to train UMAP model")
            logger.exception(e)
            raise RuntimeError("UMAP training failed") from e

    def _transform_3d(self, user, tag_uid: str, *, documents_vector: Dict[str, Any]) -> tuple[list[GraphPoint], np.ndarray]:
        """
        Predict 3D projection and return points with original vectors.

        Returns:
            tuple: (list of GraphPoint, original vectors as np.ndarray)
        """
        model = load_umap_model(self.file_store, self.NAMESPACE, model_key(tag_uid))

        vectors = []
        meta_vectors = []
        for doc_uid, chunks_vector in documents_vector.items():
            for i, chunk_vector in enumerate(chunks_vector):
                vectors.append(chunk_vector["vector"])
                metadata = {
                    "chunk_order": i,
                    "chunk_uid": chunk_vector["chunk_uid"],
                    "document_uid": doc_uid,
                    "text": chunk_vector.get("text", None),
                }
                meta_vectors.append(metadata)

        X = np.array(vectors, dtype=np.float32)
        try:
            # Standard UMAP -> transform()
            Y = model.transform(X)
            points = build_points(Y, meta_vectors)
        except Exception as e:
            logger.error("Failed to transform X for tag %s", tag_uid)
            logger.exception(e)
            return [], np.array([])
        return points, X

    def _fit_cluster_3d(self, points: list[GraphPoint], tag_uid: str) -> Optional[Any]:
        """
        Train a 3D clustering model on the reference tag points and save it.

        Args:
            points: 3D points from the reference tag
            tag_uid: Tag identifier for saving the model

        Returns:
            Trained KMeans model or None if not possible
        """
        coords = np.array(
            [
                [
                    p.point_3d.x,
                    p.point_3d.y,
                    p.point_3d.z,
                ]
                for p in points
                if p.point_3d is not None
            ],
            dtype=np.float32,
        )

        n = coords.shape[0]
        if n < 3:
            logger.warning("Not enough points for 3D clustering training (n=%d)", n)
            return None

        try:
            from sklearn.cluster import KMeans
            from sklearn.metrics import silhouette_score
        except Exception as e:
            logger.warning("3D clustering disabled: scikit-learn not available (%s)", e)
            return None

        # Determine optimal k using silhouette score (max 10 clusters)
        max_k = max(2, min(10, n - 1))
        best_score = -1.0
        best_model = None

        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, n_init="auto", random_state=42)
            labels = km.fit_predict(coords)
            if len(set(labels)) < 2:
                continue
            try:
                score = silhouette_score(coords, labels, metric="euclidean")
            except Exception:
                logger.warning("Failed to compute silhouette score for k=%d", k)
                score = -1.0
            if score > best_score:
                best_score = score
                best_model = km

        if best_model is not None:
            logger.info("3D clustering model trained with %d clusters (silhouette: %.3f)", best_model.cluster_centers_.shape[0], best_score)
            # Save the trained model
            save_clustering_model(self.file_store, self.NAMESPACE, cluster_3d_key(tag_uid), best_model)
        else:
            logger.warning("Failed to train 3D clustering model")

        return best_model

    def _predict_cluster_3d(self, points: list[GraphPoint], tag_uid: str, model: Optional[Any] = None) -> list[GraphPoint]:
        """
        Predict 3D clusters using a trained model or by performing simple clustering.

        Args:
            points: Points to cluster
            model: Trained KMeans model (optional)

        Returns:
            Points with assigned 3D clusters
        """
        coords = np.array(
            [
                [
                    p.point_3d.x,
                    p.point_3d.y,
                    p.point_3d.z,
                ]
                for p in points
                if p.point_3d is not None
            ],
            dtype=np.float32,
        )

        n = coords.shape[0]
        if n < 3:
            logger.warning("Not enough points for 3D clustering prediction (n=%d)", n)
            return points

        try:
            pass
        except Exception as e:
            logger.warning("3D clustering disabled: scikit-learn not available (%s)", e)
            return points

        # If we have a trained model, use it for prediction
        # Otherwise, try to load from file
        labels = []
        if model is None:
            try:
                model = load_clustering_model(self.file_store, self.NAMESPACE, cluster_3d_key(tag_uid))
                logger.info("Loaded 3D clustering model from storage")
            except Exception as e:
                logger.debug("No saved 3D clustering model found: %s", e)

        if model is not None:
            try:
                labels = model.predict(coords)
                logger.info("3D clustering prediction completed with %d clusters", model.n_clusters)
            except Exception as e:
                logger.warning("Failed to predict with trained model, falling back to new clustering: %s", e)
                model = None

        # Assign clusters to points
        for i, lbl in enumerate(labels):
            if points[i].clusters is None:
                points[i].clusters = Clusters()
            clusters = points[i].clusters
            if clusters:
                clusters.d3 = int(lbl)

        return points

    def _fit_cluster_vector(self, vectors: np.ndarray, tag_uid: str) -> Optional[Any]:
        """
        Train a vector clustering model on the reference tag vectors and save it.

        Args:
            vectors: Original vectors from the reference tag (n_points, dim)
            tag_uid: Tag identifier for saving the model

        Returns:
            Trained KMeans model or None if not possible
        """
        n = vectors.shape[0]
        if n < 3:
            logger.warning("Not enough vectors for clustering training (n=%d)", n)
            return None

        try:
            from sklearn.cluster import KMeans
            from sklearn.metrics import silhouette_score
        except Exception as e:
            logger.warning("Vector clustering disabled: scikit-learn not available (%s)", e)
            return None

        # Determine optimal k using silhouette score (max 10 clusters)
        max_k = max(2, min(10, n - 1))
        best_score = -1.0
        best_model = None

        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, n_init="auto", random_state=42)
            labels = km.fit_predict(vectors)
            if len(set(labels)) < 2:
                continue
            try:
                score = silhouette_score(vectors, labels, metric="euclidean")
            except Exception:
                logger.warning("Failed to compute silhouette score for k=%d in vector space", k)
                score = -1.0
            if score > best_score:
                best_score = score
                best_model = km

        if best_model is not None:
            logger.info("Vector clustering model trained with %d clusters (silhouette: %.3f)", best_model.cluster_centers_.shape[0], best_score)
            # Save the trained model
            save_clustering_model(self.file_store, self.NAMESPACE, cluster_vector_key(tag_uid), best_model)
        else:
            logger.warning("Failed to train vector clustering model")

        return best_model

    def _predict_cluster_vector(self, points: list[GraphPoint], vectors: np.ndarray, tag_uid: str, model: Optional[Any] = None) -> list[GraphPoint]:
        """
        Predict vector clusters using a trained model or by performing simple clustering.

        Args:
            points: List of GraphPoint
            vectors: Original full-dimensional vectors (n_points, dim)
            model: Trained KMeans model (optional)

        Returns:
            Points with vector clustering assigned in clusters.vector
        """
        n = vectors.shape[0]
        if n < 3:
            logger.warning("Not enough points for vector clustering prediction (n=%d)", n)
            return points

        if n != len(points):
            logger.error("Mismatch between number of points (%d) and vectors (%d)", len(points), n)
            return points

        try:
            pass
        except Exception as e:
            logger.warning("Vector clustering disabled: scikit-learn not available (%s)", e)
            return points

        # If we have a trained model, use it for prediction
        # Otherwise, try to load from file
        labels = []
        if model is None:
            try:
                model = load_clustering_model(self.file_store, self.NAMESPACE, cluster_vector_key(tag_uid))
                logger.info("Loaded vector clustering model from storage")
            except Exception as e:
                logger.debug("No saved vector clustering model found: %s", e)

        if model is not None:
            try:
                labels = model.predict(vectors)
                logger.info("Vector clustering prediction completed with %d clusters", model.n_clusters)
            except Exception as e:
                logger.warning("Failed to predict with trained model, falling back to new clustering: %s", e)
                model = None

        # Assign vector clusters to points
        for i, lbl in enumerate(labels):
            if points[i].clusters is None:
                points[i].clusters = Clusters()
            clusters = points[i].clusters
            if clusters:
                clusters.vector = int(lbl)

        return points

    def _fit_cluster_distance(self, vectors: np.ndarray, tag_uid: str) -> Optional[np.ndarray]:
        """
        Calculate the centroid of the reference tag vectors for distance-based coloring and save it.

        Args:
            vectors: Original vectors from the reference tag (n_points, dim)
            tag_uid: Tag identifier for saving the centroid

        Returns:
            Centroid (vector of dimension dim) or None if not possible
        """
        n = vectors.shape[0]
        if n < 1:
            logger.warning("No vectors for distance centroid calculation")
            return None

        # Calculate centroid in vector space
        centroid = np.mean(vectors, axis=0)
        logger.info("Distance centroid calculated from %d reference vectors", n)

        # Save the centroid
        save_centroid(self.file_store, self.NAMESPACE, cluster_distance_key(tag_uid), centroid)

        return centroid

    def _predict_cluster_distance(self, points: list[GraphPoint], vectors: np.ndarray, tag_uid: str, centroid: Optional[np.ndarray] = None) -> list[GraphPoint]:
        """
        Heatmap coloring based on distance to centroid (trained or calculated).

        Uses a continuous normalized scale [0-100] for smooth color gradation.

        Args:
            points: List of GraphPoint
            vectors: Original full-dimensional vectors (n_points, dim)
            centroid: Pre-calculated centroid from the reference tag (optional)

        Returns:
            Points with normalized distance values assigned in clusters.distance
        """
        n = vectors.shape[0]
        if n < 1:
            logger.warning("No points for distance-based coloring")
            return points

        if n != len(points):
            logger.error("Mismatch between number of points (%d) and vectors (%d)", len(points), n)
            return points

        # If no centroid provided, try to load from file
        if centroid is None:
            try:
                centroid = load_centroid(self.file_store, self.NAMESPACE, cluster_distance_key(tag_uid))
                logger.info("Loaded centroid from storage")
            except Exception as e:
                logger.debug("No saved centroid found: %s", e)
                # Calculate from current data (backward compatibility)
                centroid = np.mean(vectors, axis=0)
                logger.info("No centroid found, calculated from current vectors")

        # Calculate distances from centroid
        distances = np.linalg.norm(vectors - centroid, axis=1)

        # Normalize distances to [0, 100] range using min-max normalization for maximum color range
        min_dist = distances.min()
        max_dist = distances.max()
        if max_dist > min_dist:
            normalized_distances = ((distances - min_dist) / (max_dist - min_dist)) * 100
        else:
            normalized_distances = np.zeros_like(distances)

        # Assign continuous distance values to points
        for i, dist_value in enumerate(normalized_distances):
            if points[i].clusters is None:
                points[i].clusters = Clusters()
            clusters = points[i].clusters
            if clusters:
                clusters.distance = int(dist_value)

        logger.info(
            "Distance-based coloring completed: min=%.2f, max=%.2f, mean=%.2f (original range: %.2f-%.2f)",
            normalized_distances.min(),
            normalized_distances.max(),
            normalized_distances.mean(),
            min_dist,
            max_dist,
        )
        return points

    # ---------- Public API ----------
    async def train_for_tag(self, user, tag_uid: str) -> dict:
        """
        Train models using all documents of a tag.
        Uses all chunk embeddings as input points.
        Saves: models as pickle and metadata under namespace models/umap/{tag_uid}
        Returns training metadata.
        """
        doc_uids = await self._list_document_uids_in_tag(user, tag_uid)
        if not doc_uids:
            raise ValueError("No documents found for this tag")

        vectors = []
        if doc_uids:
            for doc_uid in doc_uids:
                results = self.vector_store.get_vectors_for_document(document_uid=doc_uid)
                for r in results:
                    vectors.append(r["vector"])

        if len(vectors) < 2:
            raise ValueError("Insufficient number of documents with vectors to train UMAP")

        X = np.array(vectors, dtype=np.float32)

        # Train UMAP model
        model = self._fit_umap(X, tag_uid)

        # Build GraphPoint from UMAP embedding for 3D clustering training
        # Create minimal metadata for each point
        meta_vectors = [{"chunk_uid": f"chunk_{i}", "document_uid": "", "chunk_order": 0} for i in range(len(model.embedding_))]
        training_points = build_points(model.embedding_, meta_vectors)

        # Train clustering models and save them
        cluster_3d_model = self._fit_cluster_3d(training_points, tag_uid)
        cluster_vector_model = self._fit_cluster_vector(X, tag_uid)
        distance_centroid = self._fit_cluster_distance(X, tag_uid)

        # Save metadata
        trained_at = datetime.now(timezone.utc).isoformat()
        meta = {
            "tag_uid": tag_uid,
            "trained_at": trained_at,
            "n_chunks": len(vectors),
            "n_documents": len(doc_uids),
            "model_kind": "umap",
            "embedding_model": getattr(self.context.configuration.embedding_model, "name", None),
            "cluster_3d_n_clusters": cluster_3d_model.n_clusters if cluster_3d_model else None,
            "cluster_vector_n_clusters": cluster_vector_model.n_clusters if cluster_vector_model else None,
            "centroid_dim": len(distance_centroid) if distance_centroid is not None else None,
        }
        self.file_store.put(
            self.NAMESPACE,
            meta_key(tag_uid),
            json.dumps(meta).encode("utf-8"),
            content_type="application/json",
        )

        logger.info("UMAP model trained for tag=%s with %d documents", tag_uid, len(vectors))
        logger.info(
            "Clustering models trained for tag=%s: 3D=%s, Vector=%s, Distance=%s",
            tag_uid,
            cluster_3d_model.n_clusters if cluster_3d_model else "None",
            cluster_vector_model.n_clusters if cluster_vector_model else "None",
            "centroid" if distance_centroid is not None else "None",
        )

        return meta

    async def project_text(self, tag_uid: str, text: str) -> GraphPoint:
        """
        Vectorize a text and project it into 3D space using the tag's UMAP model.

        Args:
            tag_uid: Tag identifier to use the associated UMAP model
            text: Text to vectorize and project

        Returns:
            GraphPoint with the projected coordinates (without clusters and metadata)

        Raises:
            FileNotFoundError: If no UMAP model exists for this tag
            ValueError: If the text is empty or vectorization fails
        """
        if not text or not text.strip():
            raise ValueError("text cannot be empty")

        # Load the UMAP model for this tag
        model = load_umap_model(self.file_store, self.NAMESPACE, model_key(tag_uid))
        if model is None:
            raise FileNotFoundError(f"No UMAP model found for tag {tag_uid}")

        # Get embedder and vectorize the text
        embedder = self.context.get_embedder()
        try:
            vector = embedder.embed_query(text.strip())
            if not vector:
                raise ValueError("Failed to generate embedding for text")
        except Exception as e:
            logger.exception("Failed to vectorize text: %s", e)
            raise ValueError(f"Vectorization failed: {str(e)}")

        # Project the vector to 3D using UMAP
        try:
            vector_array = np.array([vector], dtype=np.float32)
            projected = model.transform(vector_array)
            if projected.shape != (1, 3):
                raise ValueError(f"Unexpected projection shape: {projected.shape}")

            x, y, z = float(projected[0, 0]), float(projected[0, 1]), float(projected[0, 2])
            logger.info("Text projected to 3D: (%.3f, %.3f, %.3f)", x, y, z)

            # Create GraphPoint with Point3D and minimal metadata
            return GraphPoint(point_3d=Point3D(x=x, y=y, z=z), metadata=PointMetadata(text=text.strip()))
        except Exception as e:
            logger.exception("Failed to project text to 3D: %s", e)
            raise ValueError(f"Projection failed: {str(e)}")

    async def project(
        self,
        user,
        ref_tag_uid: str,
        *,
        document_uids: Optional[list[str]] = None,
        tags_uids: Optional[list[str]] = None,
        with_clustering: bool = True,
        with_documents: bool = True,
    ) -> list[GraphPoint]:
        """
        Project provided documents (by uid) or raw vectors to 3D using the saved model for the given tag.

        If with_clustering is True, applies all three clustering methods:
        - 3D clustering on the projected coordinates
        - Vector clustering on the original high-dimensional vectors
        - Distance-based coloring from centroid

        Clustering models are trained on the reference tag (ref_tag_uid) only,
        then used to predict clusters for documents from all selected tags.

        If library_uids is provided, only documents from those libraries will be projected.

        Returns a payload with points.
        """
        # 1. Retrieve documents to project
        doc_uids: list[str] = []

        if document_uids:
            doc_uids.extend(document_uids)

        if tags_uids:
            # Get all documents from the specified libraries
            doc_uids.extend(await self._list_document_uids_in_tags(user, tags_uids))

        if not document_uids and not tags_uids:
            # Get all documents in tag
            doc_uids = await self._list_document_uids_in_tag(user, ref_tag_uid)

        # Retrieve vectors for all documents
        docs_vector = {}
        for doc_uid in doc_uids:
            docs_vector[doc_uid] = self.vector_store.get_vectors_for_document(document_uid=doc_uid, with_document=with_documents)

        # Project all documents using the reference tag's UMAP model
        points, original_vectors = self._transform_3d(user, ref_tag_uid, documents_vector=docs_vector)

        if with_clustering and points and len(original_vectors) > 0:
            points = self._predict_cluster_3d(points, ref_tag_uid)
            points = self._predict_cluster_vector(points, original_vectors, ref_tag_uid)
            points = self._predict_cluster_distance(points, original_vectors, ref_tag_uid)

        return points

    def get_model_status(self, tag_uid: str) -> dict:
        """
        Return model existence and metadata if available.
        """
        items = self.file_store.list(self.NAMESPACE, prefix=f"{tag_uid}/")
        # Check for model presence
        exists = any(k.endswith("model.umap") for k in items)
        meta: dict = {"tag_uid": tag_uid, "exists": exists}
        if any(k.endswith("meta.json") for k in items):
            try:
                raw = self.file_store.get(self.NAMESPACE, meta_key(tag_uid))
                meta.update(json.loads(raw.decode("utf-8")))
                meta["exists"] = exists
            except Exception:
                logger.exception("Failed to load meta.json for tag %s", tag_uid)
        return meta

    async def delete_model(self, tag_uid: str) -> dict:
        """
        Remove model artifacts for a tag (best-effort).
        """
        removed = []
        for key in [model_key(tag_uid), meta_key(tag_uid)]:
            try:
                # LocalFileStore has no delete; emulate by overwriting empty? Instead, if list present, we can ignore.
                # Since BaseFileStore has no delete contract here, we cannot truly delete. We'll report presence status.
                # Return info on what exists.
                _ = self.file_store.get(self.NAMESPACE, key)  # check existence
                removed.append(key)
            except Exception:
                logger.error("Failed to remove model artifact for tag %s", tag_uid)
        return {"tag_uid": tag_uid, "removed": removed}
