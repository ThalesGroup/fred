# Copyright Thales 2026
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

"""Build the native geo tool result without requiring an application tool invoker."""

from __future__ import annotations

from fred_sdk.contracts.context import (
    GeoPart,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)

from .catalog import TOOL_REF_GEO_RENDER_POINTS, GeoRenderPointsToolArgs


def render_geo_points(payload: dict[str, object]) -> ToolInvocationResult:
    """Convert point coordinates into the typed GeoPart consumed by chat renderers."""
    args = GeoRenderPointsToolArgs.model_validate(payload)
    title = args.title.strip() or "Map results"
    popup_property = (args.popup_property or "").strip() or None

    features: list[dict[str, object]] = []
    point_labels: list[str] = []
    for point in args.points:
        name = (point.name or "").strip() or None
        if name is not None:
            point_labels.append(name)

        properties = dict(point.properties)
        if name is not None:
            properties["name"] = name

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [point.longitude, point.latitude],
                },
                "properties": properties,
            }
        )

    if args.connect_as_zone:
        ring = [[point.longitude, point.latitude] for point in args.points]
        if ring[-1] != ring[0]:
            ring.append(ring[0])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"name": "Zone", "fillOpacity": 0.15},
            }
        )

    summary = f"{title}: displaying {len(args.points)} point(s) on the map"
    if args.connect_as_zone:
        summary += " with a closed zone"
    if point_labels:
        preview = ", ".join(point_labels[:3])
        if len(point_labels) > 3:
            preview += ", ..."
        summary += f" ({preview})"
    summary += "."
    return ToolInvocationResult(
        tool_ref=TOOL_REF_GEO_RENDER_POINTS,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=summary),),
        ui_parts=(
            GeoPart(
                geojson={"type": "FeatureCollection", "features": features},
                popup_property=popup_property,
                fit_bounds=args.fit_bounds,
            ),
        ),
    )
