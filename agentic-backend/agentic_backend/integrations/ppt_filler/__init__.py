"""Pure, offline core of the PPT Filler toolkit.

Public surface for downstream issues (params model, analyze endpoint, fill tool):

- :func:`~agentic_backend.integrations.ppt_filler.parser.parse` and its Pydantic models
  (:class:`KeyField`, :class:`SlideSchema`, :class:`TemplateError`, :class:`ParseResult`).
- The shared text-frame traversal
  (:func:`~agentic_backend.integrations.ppt_filler.traversal.list_keys_on_slide` and
  :func:`~agentic_backend.integrations.ppt_filler.traversal.replace_keys_on_slide`) used
  by both the parser and the future filler.
"""

from agentic_backend.integrations.ppt_filler.parser import (
    CODE_DESCRIBED_BUT_NOT_IN_SLIDE,
    CODE_KEY_WITHOUT_DESCRIPTION,
    KeyField,
    ParseResult,
    SlideSchema,
    TemplateError,
    parse,
)
from agentic_backend.integrations.ppt_filler.traversal import (
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
