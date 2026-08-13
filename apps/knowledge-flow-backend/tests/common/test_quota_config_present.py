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

"""Storage quota enforcement must not be silently disabled by a config file.

`AppConfig` defaults both quota limits to `None`, which `_evaluate_quota` reads
as "unlimited" — a deliberate escape hatch for deployments that run without a
quota. The failure mode is that the escape hatch triggers by *omission*: the
control-plane displays the meter from its own configuration, so a
knowledge-flow config file that forgot the keys produced a UI reading
"2.8 GB / 5 GB" while a 2.8 GB upload on top of it was accepted without a word.
That is exactly what `configuration_prod.yaml` did — it never carried the two
keys its control-plane counterpart has always had.

These pin the server-facing config files. `configuration_worker.yaml` is
excluded on purpose (the Temporal worker serves no upload route, so it never
evaluates a quota) and so is `configuration_test.yaml` (tests set their own
limits inline).
"""

from pathlib import Path

import pytest
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
SERVER_CONFIGS = ["configuration.yaml", "configuration_prod.yaml"]
QUOTA_KEYS = ["default_team_max_resources_storage_size", "personal_max_resources_storage_size"]


@pytest.mark.parametrize("filename", SERVER_CONFIGS)
@pytest.mark.parametrize("key", QUOTA_KEYS)
def test_server_config_declares_a_storage_quota(filename: str, key: str) -> None:
    app_section = yaml.safe_load((CONFIG_DIR / filename).read_text())["app"]

    assert key in app_section, f"{filename} does not set app.{key}; storage quota enforcement is off in any deployment using it, while the control-plane still shows users a limit."
    assert isinstance(app_section[key], int) and app_section[key] > 0, f"{filename}: app.{key} must be a positive byte count"
