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

from __future__ import annotations

from pathlib import Path

import yaml

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)


def load_conversation_policy_catalog(path: str | Path) -> ConversationPolicyCatalog:
    catalog_path = Path(path)
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"Conversation policy catalog file is empty: {catalog_path}")
    if not isinstance(payload, dict):
        raise ValueError(
            f"Conversation policy catalog must be a YAML mapping object: {catalog_path}"
        )
    return ConversationPolicyCatalog.model_validate(payload)
