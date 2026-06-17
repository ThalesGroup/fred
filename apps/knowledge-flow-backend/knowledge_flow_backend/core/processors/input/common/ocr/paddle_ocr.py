from pathlib import Path

from paddleocr import PaddleOCR


class PaddleOCRmodel:
    """
    Thin wrapper around PaddleOCR for text detection and recognition.

    Uses the lightweight PP-OCRv5 mobile models for Latin scripts.
    Bundled models under ``/app/models/`` are preferred; PaddleOCR
    falls back to auto-download when they are absent.
    Doc orientation, unwarping, and textline orientation are disabled.
    """

    def __init__(self) -> None:
        path_model_det = Path("/app/models/official_models/PP-OCRv5_mobile_det")
        if not path_model_det.exists():
            path_model_det = None

        path_model_rec = Path("/app/models/official_models/latin_PP-OCRv5_mobile_rec")
        if not path_model_rec.exists():
            path_model_rec = None

        self.ocr_model = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_recognition_model_dir=path_model_rec,
            text_detection_model_dir=path_model_det,
            text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
            text_detection_model_name="PP-OCRv5_mobile_det",
            lang="latin",
            enable_mkldnn=False,
        )
        self.backend_name = "PaddleOCR"

    def predict(self, image_paths):
        """Run OCR on a list of image paths and return raw PaddleOCR results."""
        return self.ocr_model.predict(image_paths)
