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

"""Pure, offline core of the PPT Filler capability.

Public surface for downstream issues (analyze endpoint, fill tool):

- :func:`~fred_capability_ppt_filler.parser.parse` and its Pydantic models
  (:class:`KeyField`, :class:`SlideSchema`, :class:`TemplateError`, :class:`ParseResult`).
- The shared text-frame traversal
  (:func:`~fred_capability_ppt_filler.traversal.list_keys_on_slide` and
  :func:`~fred_capability_ppt_filler.traversal.replace_keys_on_slide`) used
  by both the parser and the future filler.
"""

from fred_capability_ppt_filler.parser import (
    CODE_DESCRIBED_BUT_NOT_IN_SLIDE,
    CODE_KEY_WITHOUT_DESCRIPTION,
    KeyField,
    ParseResult,
    SlideSchema,
    TemplateError,
    parse,
)
from fred_capability_ppt_filler.traversal import (
    KEY_PATTERN,
    list_keys_on_slide,
    replace_keys_on_slide,
)

__all__ = [
    "CODE_DESCRIBED_BUT_NOT_IN_SLIDE",
    "CODE_KEY_WITHOUT_DESCRIPTION",
    "KEY_PATTERN",
    "KeyField",
    "ParseResult",
    "SlideSchema",
    "TemplateError",
    "list_keys_on_slide",
    "parse",
    "replace_keys_on_slide",
]
