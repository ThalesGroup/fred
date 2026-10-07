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

"""The built-in template's stored analysis stays current."""

import json
import re

from fred_capability_ppt_filler.builder import builtin
from fred_capability_ppt_filler.builder.analysis import ANALYSIS_VERSION
from fred_capability_ppt_filler.builder.tools import _args_schema, _description

_REGENERATE = "run `make builtin-inventory` in the package"


def _stored() -> dict:
    return json.loads(builtin.INVENTORY_PATH.read_text(encoding="utf-8"))


def test_stored_inventory_matches_the_analysis_version():
    version = _stored()["inventory"]["analysis_version"]
    assert version == ANALYSIS_VERSION, _REGENERATE


def test_stored_inventory_is_what_the_pipeline_produces_for_the_shipped_deck():
    # Covers an edited deck (hash) and a changed heuristic left un-bumped.
    assert _stored() == builtin.generate_inventory(), _REGENERATE


def test_builtin_template_loads_both_halves():
    content, inventory = builtin.builtin_template()
    assert content == builtin.TEMPLATE_PATH.read_bytes()
    assert any(p.included and p.reusable for p in inventory.patterns)


def test_builtin_deck_reads_its_example_slides():
    """Each example slide stands for its layout, with its own signals."""
    _, inventory = builtin.builtin_template()
    by_name = {p.name: p for p in inventory.patterns if p.included}
    cover = by_name["Fred Title"]
    assert (cover.source, cover.source_index, cover.kind) == ("slide", 1, "cover")
    figures, process = by_name["Fred Key Figures"], by_name["Fred Process"]
    assert figures.kind == "figures" and figures.groups[0].count == 3
    assert process.kind == "process" and process.groups[0].count == 4
    assert by_name["Fred Quote"].kind == "quote"
    assert by_name["Fred Content with Image"].kind == "image_text"
    assert by_name["Fred Two Content"].kind == "two_columns"
    assert not by_name["Fred Comparison"].groups


def test_builtin_rooms_read_as_words_then_chars():
    """Every room the model reads on the shipped deck leads with a word budget."""
    _, inventory = builtin.builtin_template()
    text = _description(inventory, "template_slide", 2) + json.dumps(
        _args_schema(inventory).model_json_schema(), ensure_ascii=False
    )
    rooms = re.findall(r"(\S+ \S+) \(≈(\d+) chars(?: × (\d+) lines)?\)", text)
    assert rooms
    for words, chars, lines in rooms:
        budget = 1 if words in ("1 word", "short word") else int(words[1:].split()[0])
        # Never more words than the chars hold at the 7-chars-per-word rule.
        assert budget <= max(1, (int(chars) + 1) // 7 * int(lines or 1)), words
    # No room left quoted in chars only (table cells aside).
    assert not re.search(r"(?<!\()≈\d+ chars(?! per cell)", text)
