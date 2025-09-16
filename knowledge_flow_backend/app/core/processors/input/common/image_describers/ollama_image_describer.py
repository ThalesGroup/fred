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

import json

import requests

from app.config.ollama_settings import OllamaSettings
from app.core.processors.input.common.base_image_describer import BaseImageDescriber


class OllamaImageDescriber(BaseImageDescriber):
    def __init__(self, settings: OllamaSettings | None = None):
        self.settings = settings or OllamaSettings()
        if not self.settings.api_url or not self.settings.vision_model_name:
            raise ValueError("OLLAMA API URL or model name not configured.")

    def describe(self, image_base64: str) -> str:
        payload = {
            "model": self.settings.vision_model_name,
            "prompt": """
                Describe the image.
                Start with this sentence: "There is an image showing".
                First describe the main content of the image.
                Then, go into more detail about the image.
                Be precise, especially if the image is complex.
                Include any relevant context or information that can be inferred from the image.
                If the image is a schema or diagram, describe its components and their relationships.
                If the image is a chart or graph, describe the data it represents.
                If the image is a photograph, describe the scene, objects, and people in it.
                If the image is a screenshot, describe the interface and any visible elements.
                If the image is a logo or icon, describe briefly its design and any text it contains.
                Do not include any code or markdown formatting.
                Do not include any image URLs or references.
            """,
            "images": [image_base64],
        }
        url = f"{self.settings.api_url}/api/generate"
        # TODO: set the timeout as a variable
        response = requests.post(url, json=payload, timeout=120)

        description = ""
        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode("utf-8"))
                description += data.get("response", "")
        return description
