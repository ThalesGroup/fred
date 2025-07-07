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

# knowledge_flow_app/input_processors/openai_image_describer.py

import base64
import logging
import requests
from knowledge_flow_app.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_app.config.embedding_openai_settings import EmbeddingOpenAISettings

logger = logging.getLogger(__name__)


class OpenaiImageDescriber(BaseImageDescriber):
    def __init__(self):
        self.settings = EmbeddingOpenAISettings()

    def describe(self, image_base64: str) -> str:
        try:
            base64.b64decode(image_base64)

            headers = {
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            }

            data = {
                "model": "gpt-4-vision-preview",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": ("Describe the image in detail. Start with 'There is an image showing...' and include structure, relationships, and context."),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 512,
            }

            # TODO: set the timeout as a variable
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logger.error(f"OpenAI image description failed: {e}")
            return "Image description not available."
