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

"""The built-in Fred template used when an agent has none (design.md D9).

A designed deck shipped as package data with its stored analysis, so "no
template" goes through the customer render path. Regenerate the analysis with
``make builtin-inventory`` (``python -m fred_capability_ppt_filler.builder.builtin``).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.models import TemplateInventory

ASSETS = Path(__file__).resolve().parent / "assets"
TEMPLATE_PATH = ASSETS / "fred_template.pptx"
INVENTORY_PATH = ASSETS / "fred_template.inventory.json"


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@lru_cache(maxsize=1)
def builtin_template() -> Tuple[bytes, TemplateInventory]:
    """The built-in template's bytes and stored inventory, read once per process."""
    stored = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    inventory = TemplateInventory.model_validate(stored["inventory"])
    return TEMPLATE_PATH.read_bytes(), inventory


def generate_inventory() -> dict:
    """The stored document: the rules analysis plus the asset hash it describes.
    Rules only, so regenerating is deterministic and needs no model."""
    content = TEMPLATE_PATH.read_bytes()
    result = analyze_template(content)
    if result.inventory is None:
        raise SystemExit(f"Built-in template analysis failed: {result.errors}")
    return {
        "template_sha256": sha256_of(content),
        "inventory": result.inventory.model_dump(mode="json"),
    }


if __name__ == "__main__":
    INVENTORY_PATH.write_text(
        json.dumps(generate_inventory(), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {INVENTORY_PATH}")
