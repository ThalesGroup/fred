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

"""Contract checks for the shared map tool's point labels."""

from fred_sdk.contracts.context import GeoPart
from fred_sdk.support.builtins import (
    TOOL_REF_GEO_RENDER_POINTS,
    BuiltinToolBackend,
    get_builtin_tool_spec,
)
from fred_sdk.support.builtins.geo import render_geo_points


def test_direct_point_name_overrides_properties_name() -> None:
    result = render_geo_points(
        {
            "points": [
                {
                    "latitude": 43.1242,
                    "longitude": 5.928,
                    "name": "Toulon",
                    "properties": {"name": "Old label", "description": "Home port"},
                }
            ]
        }
    )

    part = result.ui_parts[0]
    assert isinstance(part, GeoPart)
    properties = part.geojson["features"][0]["properties"]
    assert properties == {"name": "Toulon", "description": "Home port"}
    assert result.blocks[0].text is not None and "Toulon" in result.blocks[0].text


def test_geo_uses_shared_local_builtin_contract() -> None:
    spec = get_builtin_tool_spec(TOOL_REF_GEO_RENDER_POINTS)
    assert spec is not None
    assert spec.backend == BuiltinToolBackend.LOCAL
    assert spec.output_part is GeoPart
    assert spec.local_handler is not None
    result = spec.local_handler({"points": [{"latitude": 1, "longitude": 2}]})
    assert isinstance(result.ui_parts[0], GeoPart)


def test_invalid_local_geo_call_returns_tool_error_without_part() -> None:
    spec = get_builtin_tool_spec(TOOL_REF_GEO_RENDER_POINTS)
    assert spec is not None

    result = spec.invoke_local({"points": [{"latitude": 91, "longitude": 2}]})

    assert result.is_error
    assert result.ui_parts == ()
    assert result.blocks[0].text is not None
    assert "points.0.latitude" in result.blocks[0].text


def test_points_remain_the_default_without_zone() -> None:
    result = render_geo_points(
        {
            "points": [
                {"name": "A", "latitude": 43.1, "longitude": 5.9},
                {"name": "B", "latitude": 43.2, "longitude": 6.0},
                {"name": "C", "latitude": 43.3, "longitude": 6.1},
            ]
        }
    )

    part = result.ui_parts[0]
    assert isinstance(part, GeoPart)
    assert [feature["geometry"]["type"] for feature in part.geojson["features"]] == [
        "Point"
    ] * 3


def test_requested_zone_closes_boundary_and_keeps_point_markers() -> None:
    result = render_geo_points(
        {
            "points": [
                {"name": "Toulon", "latitude": 43.1242, "longitude": 5.928},
                {"name": "At sea", "latitude": 43.08, "longitude": 5.95},
                {"name": "Hyères", "latitude": 43.119, "longitude": 6.132},
            ],
            "connect_as_zone": True,
        }
    )

    part = result.ui_parts[0]
    assert isinstance(part, GeoPart)
    features = part.geojson["features"]
    assert [feature["geometry"]["type"] for feature in features] == [
        "Point",
        "Point",
        "Point",
        "Polygon",
    ]
    assert features[3]["geometry"]["coordinates"] == [
        [[5.928, 43.1242], [5.95, 43.08], [6.132, 43.119], [5.928, 43.1242]]
    ]
    assert features[3]["properties"]["fillOpacity"] == 0.15
    assert result.blocks[0].text is not None
    assert "closed zone" in result.blocks[0].text


def test_zone_rejects_insufficient_distinct_coordinates_without_part() -> None:
    spec = get_builtin_tool_spec(TOOL_REF_GEO_RENDER_POINTS)
    assert spec is not None

    result = spec.invoke_local(
        {
            "points": [
                {"latitude": 43.1, "longitude": 5.9},
                {"latitude": 43.2, "longitude": 6.0},
                {"latitude": 43.1, "longitude": 5.9},
            ],
            "connect_as_zone": True,
        }
    )

    assert result.is_error
    assert result.ui_parts == ()
    assert result.blocks[0].text is not None
    assert "at least three distinct GPS coordinates" in result.blocks[0].text
