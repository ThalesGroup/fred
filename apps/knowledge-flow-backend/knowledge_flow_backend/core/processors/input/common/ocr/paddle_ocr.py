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

from pathlib import Path

from paddleocr import PaddleOCR

from knowledge_flow_backend.application_context import get_configuration


class PaddleOCRmodel:
    """
    Thin wrapper around PaddleOCR for text detection and recognition.

    Uses the lightweight PP-OCRv5 mobile models for Latin scripts.
    Bundled models under ``<path_base_model>/models/`` are preferred; PaddleOCR
    falls back to auto-download when they are absent.
    Doc orientation, unwarping, and textline orientation are disabled.
    """

    MODELS_SUBDIR = Path("models") / "official_models"

    def __init__(self) -> None:
        base_models_dir = Path(get_configuration().processing.path_base_model) / self.MODELS_SUBDIR

        path_model_det = base_models_dir / "PP-OCRv6_tiny_det_onnx"
        if not path_model_det.exists():
            path_model_det = None

        path_model_rec = base_models_dir / "latin_PP-OCRv5_mobile_rec_onnx"
        if not path_model_rec.exists():
            path_model_rec = None

        self.ocr_model = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_recognition_model_dir=path_model_rec,
            text_detection_model_dir=path_model_det,
            text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
            text_detection_model_name="PP-OCRv6_tiny_det",
            enable_hpi=True,
            engine="onnxruntime",
        )
        self.backend_name = "PaddleOCR"

    def predict(self, image_paths):
        """Run OCR on a list of image paths and return raw PaddleOCR results."""
        return self.ocr_model.predict(image_paths)
