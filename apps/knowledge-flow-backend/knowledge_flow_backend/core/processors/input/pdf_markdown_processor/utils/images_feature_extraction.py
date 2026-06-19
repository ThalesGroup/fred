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

import cv2
import numpy as np
from shapely import box, unary_union


def calcul_pourcentage_area(img_shape, rec_boxes) -> float:
    """
    Compute the percentage of the image covered by OCR bounding boxes.

    Boxes are merged with a union before computing area, so overlapping
    regions are not double-counted.

    Args:
        img_shape: Image shape tuple (height, width, ...).
        rec_boxes: List of boxes as [xmin, ymin, xmax, ymax].

    Returns:
        Coverage percentage in [0, 100].
    """
    h, w = img_shape[0], img_shape[1]
    total_pixels = h * w

    polygons = []
    for box_result in rec_boxes:
        poly = box(box_result[0], box_result[1], box_result[2], box_result[3])
        if not poly.is_valid:
            # Fix degenerate geometries before union
            poly = poly.buffer(0)
        polygons.append(poly)

    if polygons:
        merged_polygon = unary_union(polygons)
        total_text_area = merged_polygon.area
    else:
        total_text_area = 0.0

    coverage_percentage = (total_text_area / total_pixels) * 100
    return round(coverage_percentage, 2)


def calcul_canny(img_array, rec_boxes, canny_low=100, canny_high=200) -> float:
    """
    Compute the edge density of image regions outside OCR bounding boxes.

    The idea: text-heavy images have most of their edges *inside* bounding
    boxes; a high outside-edge density signals a diagram, chart, or photo
    that OCR cannot capture, and should be sent to the VLM instead.

    Args:
        img_array: Image as a NumPy array (BGR or grayscale).
        rec_boxes: List of OCR boxes as [xmin, ymin, xmax, ymax].
        canny_low: Lower hysteresis threshold for Canny.
        canny_high: Upper hysteresis threshold for Canny.

    Returns:
        Edge density percentage in [0, 100] over non-text pixels.
    """
    h, w = img_array.shape[0], img_array.shape[1]

    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_array

    edges = cv2.Canny(gray, canny_low, canny_high)

    # Build a mask of pixels that are outside every OCR bounding box
    outside_mask = np.ones((h, w), dtype=np.uint8)

    for rec_box in rec_boxes:
        xmin, ymin, xmax, ymax = rec_box[0], rec_box[1], rec_box[2], rec_box[3]
        # Clamp to image bounds before zeroing the mask
        xmin, xmax = max(0, xmin), min(w, xmax)
        ymin, ymax = max(0, ymin), min(h, ymax)
        outside_mask[ymin:ymax, xmin:xmax] = 0

    non_text_pixels_count = np.sum(outside_mask == 1)

    if non_text_pixels_count == 0:
        return 0.0

    outside_edges = edges[outside_mask == 1]
    edge_pixels_count = np.sum(outside_edges == 255)

    edge_density = (edge_pixels_count / non_text_pixels_count) * 100

    return round(edge_density, 2)
