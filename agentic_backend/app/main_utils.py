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

import sys
import logging
from pydantic import ValidationError

logger = logging.getLogger(__name__)

def validate_settings_or_exit(settings_class):
    try:
        settings = settings_class()
        logger.info(f"{settings_class.__name__} loaded successfully.")
        return settings
    except ValidationError as e:
        logger.critical(f"{settings_class.__name__} is misconfigured:")
        for error in e.errors():
            field = error.get("loc")[0]
            alias = settings_class.model_fields[field].alias
            msg = error.get("msg")
            logger.critical(f"  - Missing or invalid env var: {alias} ({msg})")
        sys.exit(1)
