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

"""Guard the fail-fast default that prevents silent rebac hangs.

A None timeout on the OpenFGA client means a stalled call hangs forever with no
error and no log — which is exactly what made a KF outage hard to diagnose. This
test pins a bounded default so regressions are caught offline.
"""

from fred_core.security.structure import OpenFgaRebacConfig


def test_openfga_timeout_defaults_to_bounded_value() -> None:
    config = OpenFgaRebacConfig(api_url="http://openfga:8080")  # pyright: ignore[reportArgumentType]
    assert config.timeout_millisec is not None, (
        "OpenFGA timeout must default to a bounded value so a stalled call fails fast "
        "instead of hanging the request indefinitely."
    )
    assert 0 < config.timeout_millisec <= 30000
