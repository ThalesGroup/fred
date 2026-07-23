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

from pathlib import Path
from typing import List

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.image_classification_engine_options import OnnxRuntimeImageClassificationEngineOptions
from docling.datamodel.object_detection_engine_options import OnnxRuntimeObjectDetectionEngineOptions
from docling.datamodel.picture_classification_options import DocumentPictureClassifierOptions
from docling.datamodel.pipeline_options import (
    LayoutObjectDetectionOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.base import ImageRefMode

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.base_pdf_extractor import BasePdfExtractor
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.image_transcription import ImageTranscription


class DoclingPdfExtractor(BasePdfExtractor):
    MODELS_SUBDIR = "models"

    def __init__(self, num_threads: int = 4) -> None:
        """`num_threads` sizes docling's internal OMP/accelerator pool for this extraction.

        Passed in explicitly (not read from ApplicationContext here) so this extractor stays
        usable standalone, e.g. from the procbench benchmark harness with no live ApplicationContext.
        """
        self._num_threads = num_threads

    def extract(self, file_path: Path, work_dir: str) -> tuple[str, List[ImageTranscription]]:
        """Convert a PDF file to Markdown and extract its embedded images.

        Each picture found in the document is saved as a PNG file inside `work_dir`
        and wrapped in an ImageTranscription object for downstream processing.
        """
        doc = self._build_document_converter().convert(str(file_path)).document

        images_transcription = []
        for i, pic in enumerate(doc.pictures):
            img = pic.get_image(doc)
            if img is None or pic.image is None:
                continue
            image_path = Path(work_dir) / f"img{i}.png"
            img.save(image_path)
            # Update the in-document URI so the Markdown export references the saved file
            pic.image.uri = image_path
            images_transcription.append(ImageTranscription(image_path=image_path))

        md_text = doc.export_to_markdown(image_mode=ImageRefMode.REFERENCED)
        del doc

        return md_text, images_transcription

    def _build_document_converter(self) -> DocumentConverter:
        """Build a DocumentConverter with local ONNX models when available, or fall back to
        automatic model download when the expected paths do not exist."""
        models_dir = Path(get_configuration().processing.path_base_model) / self.MODELS_SUBDIR
        ocr_model_dir = models_dir / "official_models"

        opts = PdfPipelineOptions()
        opts.generate_picture_images = True
        opts.do_ocr = True
        opts.do_table_structure = True
        opts.table_structure_options = TableStructureOptions(mode=TableFormerMode.FAST)
        opts.table_structure_options.do_cell_matching = False
        opts.layout_batch_size = 16
        opts.accelerator_options = AcceleratorOptions(num_threads=self._num_threads)

        opts.artifacts_path = models_dir
        opts.layout_options = LayoutObjectDetectionOptions.from_preset(
            "layout_heron_default",
            engine_options=OnnxRuntimeObjectDetectionEngineOptions(),
        )

        opts.picture_classification_options = DocumentPictureClassifierOptions(engine_options=OnnxRuntimeImageClassificationEngineOptions())

        # cls disabled: orientation classification is not needed for latin documents
        opts.ocr_options = RapidOcrOptions(
            use_cls=False,
            cls_model_path=str(ocr_model_dir / "PP-OCRv6_tiny_det_onnx" / "inference.onnx"),
            rec_model_path=str(ocr_model_dir / "latin_PP-OCRv5_mobile_rec_onnx" / "inference.onnx"),
            det_model_path=str(ocr_model_dir / "PP-OCRv6_tiny_det_onnx" / "inference.onnx"),
            rec_keys_path=str(ocr_model_dir / "latin_PP-OCRv5_mobile_rec_onnx" / "dict.txt"),
        )

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=opts,
                    backend=PyPdfiumDocumentBackend,
                )
            }
        )
