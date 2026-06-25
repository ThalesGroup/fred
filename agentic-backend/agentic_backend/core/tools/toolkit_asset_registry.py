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

"""Registry of :class:`ToolkitAssetProcessor` instances keyed by provider.

Parallel to :mod:`agentic_backend.core.tools.inprocess_toolkit_registry` (the tool-factory
registry): a module-level dict + lookup helper + a list helper. A future toolkit plugs in
by adding its processor here; the generic save hook then runs it automatically.

Only ``ppt_filler`` has a processor today. A provider with NO registered processor (e.g.
``kf_vector_search``) simply skips processing — its params are persisted unchanged.
"""

from __future__ import annotations

from typing import Dict, Optional

from agentic_backend.core.tools.toolkit_asset_processor import ToolkitAssetProcessor
from agentic_backend.integrations.ppt_filler.ppt_filler_processor import (
    PptFillerAssetProcessor,
)
from agentic_backend.integrations.ppt_filler.ppt_filler_params import (
    PPT_FILLER_PROVIDER,
)

_TOOLKIT_ASSET_PROCESSORS: Dict[str, ToolkitAssetProcessor] = {
    PPT_FILLER_PROVIDER: PptFillerAssetProcessor(),
}


def get_asset_processor(provider: str | None) -> Optional[ToolkitAssetProcessor]:
    """Return the processor registered for ``provider``, or ``None`` if there is none.

    Returns ``None`` (rather than raising) for an unregistered provider so the generic
    save hook can cheaply skip params that need no asset processing.
    """
    if not provider or not provider.strip():
        return None
    return _TOOLKIT_ASSET_PROCESSORS.get(provider.strip().lower())


def list_asset_processors() -> list[ToolkitAssetProcessor]:
    """Return all registered processors (UI/catalog metadata source)."""
    return list(_TOOLKIT_ASSET_PROCESSORS.values())


def asset_processor_metadata() -> dict[str, dict]:
    """Return UI/catalog-readable metadata per provider.

    Shape: ``{ provider: { "asset_required": bool, "accepted_file_types": [...] } }``.
    Surfaced so the frontend can gate Save and configure the upload control from
    declarative metadata rather than special-cased code.
    """
    return {
        provider: {
            "asset_required": processor.asset_required,
            "accepted_file_types": list(processor.accepted_file_types),
        }
        for provider, processor in _TOOLKIT_ASSET_PROCESSORS.items()
    }
