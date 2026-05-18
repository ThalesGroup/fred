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

from types import SimpleNamespace

from knowledge_flow_backend.core.processors.input.common.image_describer import (
    VISION_DESCRIBE_PROMPT_V1,
    VisionImageDescriber,
    _normalize_image_data_url,
)


def test_normalize_image_data_url_keeps_existing_data_uri():
    data_uri = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"

    assert _normalize_image_data_url(data_uri) == data_uri


def test_normalize_image_data_url_wraps_raw_base64():
    raw_base64 = "iVBORw0KGgoAAAANSUhEUgAA"

    assert _normalize_image_data_url(raw_base64) == f"data:image/png;base64,{raw_base64}"


def test_vision_image_describer_accepts_existing_data_uri():
    captured: dict[str, str] = {}

    class FakeModel:
        def invoke(self, messages):
            image_url = messages[1].content[1]["image_url"]["url"]
            captured["image_url"] = image_url
            return SimpleNamespace(content="There is an image showing a test.")

    describer = VisionImageDescriber(FakeModel(), VISION_DESCRIBE_PROMPT_V1)
    data_uri = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"

    description = describer.describe(data_uri)

    assert description == "There is an image showing a test."
    assert captured["image_url"] == data_uri
