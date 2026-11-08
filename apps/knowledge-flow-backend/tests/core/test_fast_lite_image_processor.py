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


import base64
import io
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageStat

from knowledge_flow_backend.core.processors.input.common.image_describer import (
    IMAGE_DESCRIPTION_UNAVAILABLE,
    VISION_ATTACHMENT_PROMPT_V1,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor import (
    DESCRIPTION_LIMITS,
    DESCRIPTION_MAX_CHARS,
    DESCRIPTION_TRUNCATED,
    NO_DESCRIPTION,
    VISION_MAX_EDGE_PX,
    FastLiteImageProcessor,
)

_MODULE = "knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor"
_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _use_vision(monkeypatch, description: str = "A red square.") -> list[str]:
    """Fake vision model: returns the data URLs it was sent."""
    sent: list[str] = []

    class Describer:
        def describe(self, data_url: str) -> str:
            sent.append(data_url)
            return description

    def build(_config, system_prompt=None):
        assert system_prompt == VISION_ATTACHMENT_PROMPT_V1
        return Describer()

    monkeypatch.setattr(f"{_MODULE}.get_configuration", lambda: SimpleNamespace(vision_model=object()))
    monkeypatch.setattr(f"{_MODULE}.build_image_describer", build)
    return sent


def _image_bytes(size: tuple[int, int], fmt: str, mode: str = "RGB", exif_orientation: int = 0) -> bytes:
    exif = Image.Exif()
    if exif_orientation:
        exif[0x0112] = exif_orientation
    buffer = io.BytesIO()
    Image.new(mode, size, "red").save(buffer, format=fmt, exif=exif.tobytes())
    return buffer.getvalue()


def _png_url(size: tuple[int, int] = (40, 30)) -> str:
    return "data:image/png;base64," + base64.b64encode(_image_bytes(size, "PNG")).decode()


def _decoded(data_url: str) -> Image.Image:
    assert data_url.startswith("data:image/png;base64,")
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))


def test_fast_lite_image_processor_uses_filename_fallback_without_vision(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "Screenshot_login_page.png"
    image_path.write_bytes(_ONE_PIXEL_PNG)

    monkeypatch.setattr(f"{_MODULE}.get_configuration", lambda: SimpleNamespace(vision_model=None))

    result = FastLiteImageProcessor().extract(image_path)

    assert result.document_name == "Screenshot_login_page.png"
    assert result.page_count == 1
    assert "Screenshot login page" in result.text
    assert "session-scoped retrieval" in result.text
    assert result.text.endswith(NO_DESCRIPTION)


def test_fast_lite_image_processor_appends_vision_summary_when_available(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(_ONE_PIXEL_PNG)
    _use_vision(monkeypatch, "There is an image showing a login form and a submit button.")

    text = FastLiteImageProcessor().extract(image_path).text

    assert "login form and a submit button" in text
    # Limits note sits between the header and the description, so truncation never cuts it.
    assert text.index("Image attachment:") < text.index(DESCRIPTION_LIMITS) < text.index("Vision summary:")
    assert NO_DESCRIPTION not in text


def test_failed_vision_says_content_unknown_in_one_log_line(tmp_path: Path, monkeypatch, caplog) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(_ONE_PIXEL_PNG)
    _use_vision(monkeypatch, IMAGE_DESCRIPTION_UNAVAILABLE)

    with caplog.at_level(logging.INFO, logger=_MODULE):
        text = FastLiteImageProcessor().extract(image_path).text

    assert text.endswith(NO_DESCRIPTION)
    assert "Vision summary:" not in text and DESCRIPTION_LIMITS not in text
    assert [record.getMessage() for record in caplog.records] == ["[FAST TEXT][IMAGE] No visual description for chart.png: the vision model gave none"]


@pytest.mark.parametrize(
    ("name", "data", "size", "mode"),
    [
        ("photo.jpg", _image_bytes((4000, 2000), "JPEG"), (VISION_MAX_EDGE_PX, VISION_MAX_EDGE_PX // 2), "RGB"),
        ("icon.png", _image_bytes((40, 30), "PNG", "RGBA"), (40, 30), "RGBA"),  # never upscaled
        ("capture.webp", _image_bytes((200, 100), "WEBP"), (200, 100), "RGB"),
        ("render.png", _image_bytes((VISION_MAX_EDGE_PX + 2, 400), "PNG"), (VISION_MAX_EDGE_PX + 2, 400), "RGB"),  # not resampled
        # EXIF orientation survives the early downscale, large or small.
        ("large.jpg", _image_bytes((3200, 1600), "JPEG", exif_orientation=6), (VISION_MAX_EDGE_PX // 2, VISION_MAX_EDGE_PX), "RGB"),
        ("small.jpg", _image_bytes((200, 100), "JPEG", exif_orientation=6), (100, 200), "RGB"),
    ],
)
def test_image_is_sent_as_a_bounded_png(tmp_path: Path, monkeypatch, name: str, data: bytes, size: tuple[int, int], mode: str) -> None:
    image_path = tmp_path / name
    image_path.write_bytes(data)
    sent = _use_vision(monkeypatch)

    text = FastLiteImageProcessor().extract(image_path).text

    image = _decoded(sent[0])
    assert (image.format, image.size, image.mode) == ("PNG", size, mode)
    assert "Vision summary:\nA red square." in text


def test_sixteen_bit_grayscale_keeps_its_tones(tmp_path: Path, monkeypatch) -> None:
    gradient = Image.linear_gradient("L").resize((256, 256)).convert("I").point(lambda value: value * 257).convert("I;16")
    image_path = tmp_path / "xray.png"
    gradient.save(image_path, format="PNG")
    sent = _use_vision(monkeypatch)

    FastLiteImageProcessor().extract(image_path)

    assert 100 < ImageStat.Stat(_decoded(sent[0]).convert("L")).mean[0] < 155


@pytest.mark.parametrize(
    ("name", "data", "log"),
    [
        ("broken.png", b"not an image at all", "broken.png not described: UnidentifiedImageError"),
        ("scan.png", _image_bytes((50, 50), "TIFF"), "scan.png not described: UnidentifiedImageError"),  # not a chat format
        ("poster.png", _image_bytes((9000, 9000), "PNG", "1"), "poster.png not described: 9000x9000 px"),  # refused before decoding
    ],
)
def test_image_that_cannot_be_prepared_is_not_sent_to_vision(tmp_path: Path, monkeypatch, caplog, name: str, data: bytes, log: str | None) -> None:
    image_path = tmp_path / name
    image_path.write_bytes(data)
    sent = _use_vision(monkeypatch)

    with caplog.at_level(logging.INFO, logger=_MODULE):
        text = FastLiteImageProcessor().extract(image_path).text

    assert sent == [] and text.endswith(NO_DESCRIPTION)
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [] if log is None else len(messages) == 1 and log in messages[0]


def test_long_description_is_cut_with_a_marker_inside_the_budget(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(_ONE_PIXEL_PNG)
    _use_vision(monkeypatch, "word " * 3000)

    text = FastLiteImageProcessor().extract(image_path).text

    assert text.endswith(DESCRIPTION_TRUNCATED)
    assert len(text.split("Vision summary:\n", 1)[1]) == DESCRIPTION_MAX_CHARS
