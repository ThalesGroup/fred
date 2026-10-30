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

"""Word template engine.

- :func:`build_map` / :func:`render_map` / :func:`parts` / :func:`render_part`:
  the document map with stable addresses;
- :func:`apply_batch` / :func:`replay`: the operations (``set_text``,
  ``replace_text``, ``write``, ``insert_after``, ``repeat``, ``remove``,
  ``move``) and
  the operation log;
- ``capability.WordTemplateCapability``: the Fred capability,
  imported from its module so the Word core stays usable without Fred.
"""

from fred_capability_word_template.docmap import (
    DocMap,
    MapElement,
    MapPart,
    build_map,
    parts,
    render_map,
    render_part,
    render_parts,
)
from fred_capability_word_template.operations import (
    BatchError,
    InsertAfter,
    Move,
    Operation,
    Remove,
    Repeat,
    ReplaceText,
    SetText,
    Write,
    apply_batch,
    parse_operation,
    replay,
)

__all__ = [
    "BatchError",
    "DocMap",
    "InsertAfter",
    "MapElement",
    "MapPart",
    "Move",
    "Operation",
    "Remove",
    "Repeat",
    "ReplaceText",
    "SetText",
    "Write",
    "apply_batch",
    "build_map",
    "parse_operation",
    "parts",
    "render_map",
    "render_part",
    "render_parts",
    "replay",
]
