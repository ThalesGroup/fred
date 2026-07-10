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

"""
Platform-side asset-slot enforcement (#1974, RFC AGENT-CAPABILITY-RFC.md §3.4).

Why this module exists:
- the platform enforces `AssetSlot` cardinality and extension per slot BEFORE
  any capability code runs, with generic, uniformly-worded messages — so
  `validate_config` only ever owns content validation
- one enforcement function keeps the wording identical for every capability
  and every slot (the "uniform 422" rule); callers map
  `AssetSlotViolationError` to an HTTP 422

How to use:
- `enforce_asset_slots(manifest, uploads)` with `uploads` keyed by slot key,
  right before `capability.validate_config(...)`
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fred_sdk.contracts.capability import CapabilityManifest, UploadedFile

from .errors import AssetSlotViolationError


def _cardinality_phrase(min_count: int, max_count: int | None) -> str:
    """One uniform phrase per cardinality shape — never capability-specific."""

    if max_count is None:
        return f"at least {min_count}"
    if min_count == max_count:
        return f"exactly {min_count}"
    return f"between {min_count} and {max_count}"


def enforce_asset_slots(
    manifest: CapabilityManifest,
    uploads: Mapping[str, Sequence[UploadedFile]],
) -> None:
    """
    Enforce per-slot cardinality and file extension (RFC §3.4).

    Raises `AssetSlotViolationError` with a generic, uniformly-worded message
    on the first violation. Runs BEFORE capability code, so a broken upload
    never reaches `validate_config`.
    """

    declared = {slot.key: slot for slot in manifest.assets}
    for key in uploads:
        if key not in declared:
            raise AssetSlotViolationError(
                f"Asset slot '{key}': capability '{manifest.id}' declares no "
                "such upload slot."
            )
    for slot in manifest.assets:
        files = list(uploads.get(slot.key, ()))
        count = len(files)
        if count < slot.min_count or (
            slot.max_count is not None and count > slot.max_count
        ):
            raise AssetSlotViolationError(
                f"Asset slot '{slot.key}': expected "
                f"{_cardinality_phrase(slot.min_count, slot.max_count)} "
                f"file(s), got {count}."
            )
        accepted = tuple(ext.lower() for ext in slot.accepted_types)
        if not accepted:
            continue
        for upload in files:
            if not upload.filename.lower().endswith(accepted):
                raise AssetSlotViolationError(
                    f"Asset slot '{slot.key}': file '{upload.filename}' has an "
                    f"unsupported type; accepted: {', '.join(slot.accepted_types)}."
                )
