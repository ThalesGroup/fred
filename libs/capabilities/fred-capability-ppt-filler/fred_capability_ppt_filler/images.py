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

"""Picture bytes preparation shared by the filler and the builder."""

from __future__ import annotations

import io
from typing import Tuple

from PIL import Image, UnidentifiedImageError

# Pillow ``format`` values python-pptx's ``add_picture`` can actually embed.
# Anything else (WEBP, ICO, ...) decodes in Pillow but is rejected by
# ``add_picture``, so it is transcoded to PNG in memory first.
PPTX_EMBEDDABLE_FORMATS = frozenset({"BMP", "GIF", "JPEG", "PNG", "TIFF", "WMF"})


# Checked on the header, before any decoding: a slide never needs more, and a
# small file can declare a bitmap of gigabytes. Pillow's process-wide limit
# stays as it is for the other code of the pod.
MAX_PICTURE_PIXELS = 40_000_000


class NotAnImageError(ValueError):
    """The bytes are not a usable raster image."""


class PictureTooLargeError(NotAnImageError):
    """The image declares more pixels than a slide picture may hold."""


def open_picture(image_bytes: bytes) -> Image.Image:
    """The image, header read only; raises :class:`NotAnImageError`."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Image.DecompressionBombError as exc:
        raise PictureTooLargeError("the picture is too large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise NotAnImageError(f"{type(exc).__name__}: {exc}") from exc
    width, height = image.size
    if width * height > MAX_PICTURE_PIXELS:
        image.close()
        raise PictureTooLargeError(
            f"the picture is too large ({width}x{height} pixels, at most "
            f"{MAX_PICTURE_PIXELS // 1_000_000} million)"
        )
    return image


def prepare_picture(image_bytes: bytes) -> Tuple[bytes, int, int]:
    """Validate ``image_bytes`` as an image and return ``(embeddable bytes, width, height)``."""
    try:
        with open_picture(image_bytes) as image:
            width, height = image.size
            if image.format not in PPTX_EMBEDDABLE_FORMATS:
                buffer = io.BytesIO()
                image.convert("RGBA").save(buffer, format="PNG")
                image_bytes = buffer.getvalue()
    except NotAnImageError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise NotAnImageError(f"{type(exc).__name__}: {exc}") from exc
    return image_bytes, width, height


def fit_inside_box(
    img_w: int, img_h: int, box_left: int, box_top: int, box_w: int, box_h: int
) -> Tuple[int, int, int, int]:
    """Scale ``(img_w, img_h)`` into the box preserving the aspect ratio, centred.

    Inputs and outputs are EMU; the pixel size only sets the aspect ratio.
    """
    if img_w <= 0 or img_h <= 0 or box_w <= 0 or box_h <= 0:
        return (box_left, box_top, box_w, box_h)
    ratio = img_w / img_h
    if box_w / box_h > ratio:
        height = box_h
        width = box_h * ratio
        top = box_top
        left = box_left + (box_w - width) / 2
    else:
        width = box_w
        height = box_w / ratio
        left = box_left
        top = box_top + (box_h - height) / 2
    return (round(left), round(top), round(width), round(height))
