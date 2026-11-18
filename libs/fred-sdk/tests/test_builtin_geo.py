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
