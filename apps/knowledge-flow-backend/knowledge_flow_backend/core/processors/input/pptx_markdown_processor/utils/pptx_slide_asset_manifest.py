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

"""Persists slide-level visual asset references for rich PPTX processing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PptxSlideAssetEntry:
    slide_number: int
    has_visual_evidence: bool
    slide_image_path: str


@dataclass
class PptxSlideAssetManifest:
    slides: list[PptxSlideAssetEntry] = field(default_factory=list)


def write_slide_asset_manifest(
    output_dir: Path,
    rendered_slides: dict[int, Path],
) -> Path:
    manifest = PptxSlideAssetManifest(
        slides=[
            PptxSlideAssetEntry(
                slide_number=slide_number,
                has_visual_evidence=True,
                slide_image_path=str(path.relative_to(output_dir)),
            )
            for slide_number, path in sorted(rendered_slides.items())
        ]
    )

    manifest_path = output_dir / "pptx_slide_assets.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path
