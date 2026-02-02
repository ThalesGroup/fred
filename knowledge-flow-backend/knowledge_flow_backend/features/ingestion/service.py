"""Backward-compatible import shim for ingestion service."""

from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

__all__ = ["IngestionService"]
