# app/core/models/vessel.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0
# -------------------------------------------------------------
# GeoJSON data structures for vessels and map features
# -------------------------------------------------------------

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VesselFeature(BaseModel):
    """Represents a single GeoJSON Feature for a vessel or port."""

    type: str = Field(default="Feature", description="GeoJSON feature type (always 'Feature')")
    geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Geometry object containing 'type' and 'coordinates' (e.g., Point).",
    )
    properties: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the feature, such as name, type, or attributes.",
    )


class VesselData(BaseModel):
    """Represents a GeoJSON FeatureCollection of vessels or geographic points."""

    type: str = Field(default="FeatureCollection", description="GeoJSON collection type.")
    features: List[VesselFeature] = Field(
        default_factory=list,
        description="List of individual GeoJSON features representing vessels or ports.",
    )
