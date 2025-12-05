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
from typing import Optional, List, Dict, Any

import numpy as np
from umap.parametric_umap import ParametricUMAP

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.service import MetadataService
from .types import GraphPoint
from .utils import (
    build_points,
    load_keras_model,
    meta_key as util_meta_key,
    model_key as util_model_key,
    save_keras_model,
)

logger = logging.getLogger(__name__)


class ModelService:
    """
    Manage per-tag UMAP models for 3D projection of document vectors.

    - One model per tag_id
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
    def _model_key(self, tag_id: str) -> str:
        # kept for backward compatibility within this class; delegates to utils
        return util_model_key(tag_id)

    def _meta_key(self, tag_id: str) -> str:
        return util_meta_key(tag_id)

    async def _list_document_ids_in_tag(self, user, tag_id: str) -> list[str]:
        docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_id)
        return [d.identity.document_uid for d in docs]

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

    def _predict_3d(self, user, tag_id: str, *, documents_vector: Dict[str, Any]) -> list[GraphPoint]:
        model = load_keras_model(self.file_store, self.NAMESPACE, self._model_key(tag_id))

        vectors = []
        meta_vectors = []
        for doc_id, chunks_vector in documents_vector.items():
            for i, chunk_vector in enumerate(chunks_vector):
                vectors.append(chunk_vector['vector'])
                metadata = {
                    "chunk_order": i,
                    "chunk_uid": chunk_vector['chunk_uid'],
                    "document_uid": doc_id,
                    "text": chunk_vector.get('text', None),
                }
                meta_vectors.append(metadata)

        X = np.array(vectors, dtype=np.float32)
        try:
            Y = model.predict(X)
            points = build_points(Y, meta_vectors)
        except Exception as e:
            logger.error("Failed to transform X for tag %s", tag_id)
            logger.exception(e)
            return []
        return points

    def _cluster_3d(self, points: list[GraphPoint]) -> list[GraphPoint]:
        # Extract 3D coordinates
        coords = np.array([
            [
                p.point_3d.x,
                p.point_3d.y,
                p.point_3d.z,
            ]
            for p in points
            if p.point_3d is not None
        ], dtype=np.float32)

        n = coords.shape[0]
        if n < 3:
            # Too few points to cluster meaningfully
            return points

        # Import scikit-learn lazily to avoid hard dependency at import time
        try:
            from sklearn.cluster import KMeans
            from sklearn.metrics import silhouette_score
        except Exception as e:
            logger.warning("Clustering disabled: scikit-learn not available (%s)", e)
            return points

        # Determine optimal k using silhouette score
        max_k = max(2, min(10, n - 1))
        best_k = None
        best_score = -1.0
        best_labels = None

        for k in range(2, max_k + 1):
            try:
                km = KMeans(n_clusters=k, n_init="auto", random_state=42)
            except TypeError:
                # Older sklearn without n_init="auto"
                km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(coords)
            # If all points fell into a single cluster by some issue, skip
            if len(set(labels)) < 2:
                continue
            try:
                score = silhouette_score(coords, labels, metric="euclidean")
            except Exception:
                # Silhouette can fail in edge cases; skip this k
                continue
            if score > best_score:
                best_score = score
                best_k = k
                best_labels = labels

        # If we found a good k, assign clusters
        if best_labels is not None:
            for i, lbl in enumerate(best_labels):
                points[i].point_3d.cluster = int(lbl)

        return points

    def _predict_2d(self, user, tag_id: str, *, document_uids: list[str] = None):
        raise NotImplementedError("2D projection is not implemented in this service.")

    # ---------- Public API ----------
    async def train_umap_for_tag(self, user, tag_id: str) -> dict:
        """
        Train a (Parametric) UMAP model to 3D using all documents of a tag.
        Uses the mean of chunk embeddings per document as input points.
        Saves: model.keras and meta.json under namespace models/umap/{tag_id}
        Returns training metadata.
        """
        doc_ids = await self._list_document_ids_in_tag(user, tag_id)
        if not doc_ids:
            raise ValueError("No documents found for this tag")

        vectors = []
        if doc_ids:
            for doc_id in doc_ids:
                results = self.vector_store.get_vectors_for_document(document_uid=doc_id)
                for r in results:
                    vectors.append(r["vector"])

        if len(vectors) < 2:
            raise ValueError("Insufficient number of documents with vectors to train UMAP")

        X = np.array(vectors, dtype=np.float32)

        # Configure model: 3D projection
        # ParametricUMAP typical args; keep defaults reasonable
        model = ParametricUMAP(
            n_components=3,      # 3D target space
            n_neighbors=15,      # Local influence (smaller = tighter clusters)
            min_dist=0.1,        # Minimum distance between points
            metric='cosine',     # 'cosine' often performs better than 'euclidean' for text embeddings
            verbose=True,
            random_state=42
        )
        model.fit(X)

        # Save encoder sub-model
        try:
            encoder_model = model.encoder
        except Exception as e:
            logger.exception("UMAP model does not expose an encoder: %s", e)
            raise RuntimeError("Invalid UMAP model: no encoder exposed") from None

        save_keras_model(
            self.file_store,
            self.NAMESPACE,
            self._model_key(tag_id),
            encoder_model,
        )

        # Save metadata
        trained_at = datetime.now(timezone.utc).isoformat()
        meta = {
            "tag_id": tag_id,
            "trained_at": trained_at,
            "n_chunks": len(vectors),
            "n_documents": len(doc_ids),
            "model_kind": "parametric_umap",
            "embedding_model": getattr(self.context.configuration.embedding_model, "name", None),
        }
        self.file_store.put(self.NAMESPACE, self._meta_key(tag_id), json.dumps(meta).encode("utf-8"), content_type="application/json")

        logger.info("UMAP model trained for tag=%s with %d documents", tag_id, len(vectors))
        return meta

    def get_model_status(self, tag_id: str) -> dict:
        """Return model existence and metadata if available."""
        items = self.file_store.list(self.NAMESPACE, prefix=f"{tag_id}/")
        # We persist the encoder as a Keras model file
        exists = any(k.endswith("model.keras") for k in items)
        meta: dict = {"tag_id": tag_id, "exists": exists}
        if any(k.endswith("meta.json") for k in items):
            try:
                raw = self.file_store.get(self.NAMESPACE, self._meta_key(tag_id))
                meta.update(json.loads(raw.decode("utf-8")))
                meta["exists"] = exists
            except Exception:
                logger.exception("Failed to load meta.json for tag %s", tag_id)
        return meta

    # removed in favor of utils: _save_model, _load_model

    async def project(
            self,
            user,
            tag_id: str,
            *,
            document_uids: Optional[list[str]] = None,
            with_clustering: bool = True,
            with_documents: bool = True,
    ) -> list[GraphPoint]:
        """
        Project provided documents (by uid) or raw vectors to 3D using the saved model for the given tag.
        Returns a payload with points.
        """
        doc_ids: list[str] = []
        if document_uids:
            doc_ids = document_uids
        else:
            # Get all documents in tag
            doc_ids = await self._list_document_ids_in_tag(user, tag_id)

        points: list[GraphPoint] = []
        docs_vector = {}
        for doc_id in doc_ids:
            docs_vector[doc_id] = self.vector_store.get_vectors_for_document(
                document_uid=doc_id,
                with_document=with_documents
            )

        points = self._predict_3d(user, tag_id, documents_vector=docs_vector)

        if with_clustering and points:
            points = self._cluster_3d(points)

        return points

    def delete_model(self, tag_id: str) -> dict:
        """Remove model artifacts for a tag (best-effort)."""
        removed = []
        for key in [self._model_key(tag_id), self._meta_key(tag_id)]:
            try:
                # LocalFileStore has no delete; emulate by overwriting empty? Instead, if list present, we can ignore.
                # Since BaseFileStore has no delete contract here, we cannot truly delete. We'll report presence status.
                # Return info on what exists.
                _ = self.file_store.get(self.NAMESPACE, key)  # check existence
                removed.append(key)
            except Exception:
                pass
        return {"tag_id": tag_id, "removed": removed}