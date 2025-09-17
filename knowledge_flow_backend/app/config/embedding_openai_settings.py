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

import logging
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class EmbeddingOpenAISettings(BaseSettings):
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    openai_api_base: str = Field(default="https://api.openai.com/v1", validation_alias="OPENAI_API_BASE")
    openai_model_name: str = Field(default="text-embedding-ada-002", validation_alias="OPENAI_MODEL_NAME")
    openai_api_version: Optional[str] = Field(default=None, validation_alias="OPENAI_API_VERSION")  # Azure needs version, OpenAI doesn't really

    model_config = {
        "extra": "ignore"  # allows unrelated variables in .env or os.environ
    }
