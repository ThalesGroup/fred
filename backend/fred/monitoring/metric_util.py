# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
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
metric_util.py

Utility functions for metric processing.

Includes:
- flatten_numeric_fields: Recursively flattens numeric fields in nested objects or dicts,
  producing a flat dictionary of field paths to numeric values.
"""

import logging
from typing import Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def flatten_numeric_fields(prefix: str, obj: Any) -> Dict[str, float]:
    """
    Recursively flattens numeric fields in a nested Pydantic model or dict.

    Args:
        prefix (str): Prefix for field paths.
        obj (Any): The object to flatten.

    Returns:
        Dict[str, float]: Mapping of flattened field paths to numeric values.
    """
    flat: Dict[str, float] = {}

    if isinstance(obj, BaseModel):
        data = obj.model_dump(exclude_none=True)
    elif isinstance(obj, dict):
        data = obj
    else:
        return flat

    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, (int, float)):
            flat[full_key] = float(v)
        elif isinstance(v, (dict, BaseModel)):
            flat.update(flatten_numeric_fields(full_key, v))

    return flat
