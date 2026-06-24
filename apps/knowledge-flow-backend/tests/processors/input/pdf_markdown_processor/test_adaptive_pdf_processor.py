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

"""
Unit tests for Issue #1191 — Adaptive PDF Extraction Strategy.

Coverage
--------
PdfDocumentAnalyzer
  - _select_sample_indices: boundary conditions (small/large page counts)
  - _classify: all three nature categories
  - analyze: graceful handling of unreadable files
  - analyze: correct routing for a real (text-native) PDF fixture

AdaptivePdfMarkdownProcessor
  - TEXT_NATIVE document → OCR and table structure both disabled
  - SCANNED document → OCR enabled + force_full_page_ocr=True
  - COMPLEX_LAYOUT document → OCR disabled + table structure enabled
  - Analysis failure → falls back to base config, does not raise
  - Full convert_file_to_markdown path is delegated to PdfMarkdownProcessor
    with the adapted config (monkey-patched DocumentConverter)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.adaptive_pdf_processor import (
    AdaptivePdfMarkdownProcessor,
    _build_complex_layout_config,
    _build_scanned_config,
    _build_text_native_config,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_document_analyzer import (
    PdfAnalysisResult,
    PdfDocumentAnalyzer,
    PdfNature,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_pdf() -> Path:
    return Path(__file__).parent / "assets" / "sample.pdf"


@pytest.fixture
def base_pdf_config() -> ProcessingConfig.PdfPipelineConfig:
    return ProcessingConfig.PdfPipelineConfig(
        backend="docling_parse",
        images_scale=1.5,
        generate_picture_images=False,
        generate_page_images=False,
        generate_table_images=False,
        do_table_structure=False,
        do_ocr=False,
        ocr_backend="openvino",
        force_full_page_ocr=False,
    )


@pytest.fixture
def adaptive_processor() -> AdaptivePdfMarkdownProcessor:
    return AdaptivePdfMarkdownProcessor()


# ---------------------------------------------------------------------------
# PdfDocumentAnalyzer — _select_sample_indices
# ---------------------------------------------------------------------------


class TestSelectSampleIndices:
    def setup_method(self):
        self.analyzer = PdfDocumentAnalyzer()

    def test_fewer_pages_than_sample_limit(self):
        indices = self.analyzer._select_sample_indices(3)
        assert indices == [0, 1, 2]

    def test_exact_sample_limit(self):
        indices = self.analyzer._select_sample_indices(5)
        assert len(indices) == 5
        assert indices[0] == 0

    def test_more_pages_than_sample_limit(self):
        indices = self.analyzer._select_sample_indices(100)
        assert len(indices) <= self.analyzer.sample_pages
        assert 0 in indices
        assert 99 in indices  # last page always included

    def test_single_page(self):
        assert self.analyzer._select_sample_indices(1) == [0]

    def test_no_duplicate_indices(self):
        for page_count in [1, 4, 5, 10, 50, 200]:
            indices = self.analyzer._select_sample_indices(page_count)
            assert len(indices) == len(set(indices)), f"Duplicates for page_count={page_count}"


# ---------------------------------------------------------------------------
# PdfDocumentAnalyzer — _classify
# ---------------------------------------------------------------------------


class TestClassify:
    def setup_method(self):
        self.analyzer = PdfDocumentAnalyzer()

    def test_no_embedded_text_is_scanned(self):
        nature = self.analyzer._classify(avg_chars=0.0, unique_font_count=0, has_embedded_text=False)
        assert nature == PdfNature.SCANNED

    def test_very_low_chars_is_scanned(self):
        nature = self.analyzer._classify(
            avg_chars=10.0,
            unique_font_count=0,
            has_embedded_text=True,
        )
        assert nature == PdfNature.SCANNED

    def test_chars_below_threshold_is_scanned(self):
        nature = self.analyzer._classify(
            avg_chars=float(self.analyzer.chars_per_page_scanned_threshold - 1),
            unique_font_count=10,
            has_embedded_text=True,
        )
        assert nature == PdfNature.SCANNED

    def test_rich_fonts_is_complex_layout(self):
        nature = self.analyzer._classify(
            avg_chars=500.0,
            unique_font_count=self.analyzer.font_count_complex_threshold,
            has_embedded_text=True,
        )
        assert nature == PdfNature.COMPLEX_LAYOUT

    def test_simple_text_is_text_native(self):
        nature = self.analyzer._classify(
            avg_chars=500.0,
            unique_font_count=self.analyzer.font_count_complex_threshold - 1,
            has_embedded_text=True,
        )
        assert nature == PdfNature.TEXT_NATIVE

    def test_threshold_boundary_scanned(self):
        """Chars exactly at the threshold should be TEXT_NATIVE (strictly less than means SCANNED)."""
        threshold = self.analyzer.chars_per_page_scanned_threshold
        nature_at = self.analyzer._classify(
            avg_chars=float(threshold),
            unique_font_count=0,
            has_embedded_text=True,
        )
        nature_below = self.analyzer._classify(
            avg_chars=float(threshold - 1),
            unique_font_count=0,
            has_embedded_text=True,
        )
        assert nature_at == PdfNature.TEXT_NATIVE
        assert nature_below == PdfNature.SCANNED


# ---------------------------------------------------------------------------
# PdfDocumentAnalyzer — analyze (unit, with mocked pypdf)
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_analyze_raises_on_missing_file(self, tmp_path: Path):
        analyzer = PdfDocumentAnalyzer()
        with pytest.raises(ValueError, match="Cannot open"):
            analyzer.analyze(tmp_path / "nonexistent.pdf")

    def test_analyze_raises_on_empty_pdf(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import pypdf

        monkeypatch.setattr(
            pypdf,
            "PdfReader",
            lambda path, strict=False: SimpleNamespace(pages=[]),
        )
        analyzer = PdfDocumentAnalyzer()
        with pytest.raises(ValueError, match="has no pages"):
            analyzer.analyze(tmp_path / "empty.pdf")

    def test_analyze_returns_scanned_for_no_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import pypdf

        fake_page = SimpleNamespace(
            extract_text=lambda: "",
            get=lambda key: None,
        )
        monkeypatch.setattr(
            pypdf,
            "PdfReader",
            lambda path, strict=False: SimpleNamespace(pages=[fake_page, fake_page]),
        )
        analyzer = PdfDocumentAnalyzer()
        result = analyzer.analyze(tmp_path / "scanned.pdf")
        assert result.nature == PdfNature.SCANNED
        assert result.has_embedded_text is False
        assert result.page_count == 2

    def test_analyze_returns_text_native_for_rich_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import pypdf

        fake_page = SimpleNamespace(
            extract_text=lambda: "A" * 600,
            get=lambda key: None,
        )
        monkeypatch.setattr(
            pypdf,
            "PdfReader",
            lambda path, strict=False: SimpleNamespace(pages=[fake_page]),
        )
        analyzer = PdfDocumentAnalyzer()
        result = analyzer.analyze(tmp_path / "text.pdf")
        assert result.nature == PdfNature.TEXT_NATIVE
        assert result.has_embedded_text is True

    def test_analyze_real_pdf(self, sample_pdf: Path):
        """
        Smoke test against the real sample.pdf fixture.

        The sample PDF is a born-digital file — the analyzer should not classify
        it as SCANNED.
        """
        analyzer = PdfDocumentAnalyzer()
        result = analyzer.analyze(sample_pdf)
        assert result.page_count >= 1
        assert result.nature in (PdfNature.TEXT_NATIVE, PdfNature.COMPLEX_LAYOUT)
        assert result.has_embedded_text is True


# ---------------------------------------------------------------------------
# Config builder helpers
# ---------------------------------------------------------------------------


class TestConfigBuilders:
    def test_text_native_disables_ocr_and_table_structure(self, base_pdf_config: ProcessingConfig.PdfPipelineConfig):
        cfg = _build_text_native_config(base_pdf_config)
        assert cfg.do_ocr is False
        assert cfg.do_table_structure is False
        assert cfg.backend == base_pdf_config.backend

    def test_complex_layout_enables_table_structure_only(self, base_pdf_config: ProcessingConfig.PdfPipelineConfig):
        cfg = _build_complex_layout_config(base_pdf_config)
        assert cfg.do_ocr is False
        assert cfg.do_table_structure is True

    def test_scanned_enables_ocr_and_force_full_page(self, base_pdf_config: ProcessingConfig.PdfPipelineConfig):
        cfg = _build_scanned_config(base_pdf_config)
        assert cfg.do_ocr is True
        assert cfg.force_full_page_ocr is True
        assert cfg.do_table_structure is True

    def test_builders_do_not_mutate_base(self, base_pdf_config: ProcessingConfig.PdfPipelineConfig):
        _build_scanned_config(base_pdf_config)
        _build_complex_layout_config(base_pdf_config)
        _build_text_native_config(base_pdf_config)
        assert base_pdf_config.do_ocr is False
        assert base_pdf_config.do_table_structure is False


# ---------------------------------------------------------------------------
# AdaptivePdfMarkdownProcessor — _adapt_config
# ---------------------------------------------------------------------------


class TestAdaptConfig:
    def _make_analysis(self, nature: PdfNature) -> PdfAnalysisResult:
        return PdfAnalysisResult(
            nature=nature,
            avg_chars_per_page=500.0,
            unique_font_count=4,
            page_count=5,
            has_embedded_text=True,
        )

    def test_text_native_routing(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        base_pdf_config: ProcessingConfig.PdfPipelineConfig,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: self._make_analysis(PdfNature.TEXT_NATIVE),
        )
        cfg = adaptive_processor._adapt_config(
            Path("doc.pdf"),
            IngestionProcessingProfile.medium,
            base_pdf_config,
        )
        assert cfg.do_ocr is False
        assert cfg.do_table_structure is False

    def test_scanned_routing(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        base_pdf_config: ProcessingConfig.PdfPipelineConfig,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: self._make_analysis(PdfNature.SCANNED),
        )
        cfg = adaptive_processor._adapt_config(
            Path("scanned.pdf"),
            IngestionProcessingProfile.medium,
            base_pdf_config,
        )
        assert cfg.do_ocr is True
        assert cfg.force_full_page_ocr is True
        assert cfg.do_table_structure is True

    def test_complex_layout_routing(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        base_pdf_config: ProcessingConfig.PdfPipelineConfig,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: self._make_analysis(PdfNature.COMPLEX_LAYOUT),
        )
        cfg = adaptive_processor._adapt_config(
            Path("complex.pdf"),
            IngestionProcessingProfile.rich,
            base_pdf_config,
        )
        assert cfg.do_ocr is False
        assert cfg.do_table_structure is True

    def test_analysis_failure_returns_base_config(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        base_pdf_config: ProcessingConfig.PdfPipelineConfig,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: (_ for _ in ()).throw(RuntimeError("disk error")),
        )
        cfg = adaptive_processor._adapt_config(
            Path("broken.pdf"),
            IngestionProcessingProfile.medium,
            base_pdf_config,
        )
        assert cfg is base_pdf_config


# ---------------------------------------------------------------------------
# AdaptivePdfMarkdownProcessor — convert_file_to_markdown (integration path)
# ---------------------------------------------------------------------------


class TestAdaptiveConvertFileToMarkdown:
    """
    Verify that AdaptivePdfMarkdownProcessor passes the adapted config to the
    parent's DocumentConverter, not the original base config.
    """

    def test_scanned_pdf_reaches_docling_with_ocr_enabled(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        sample_pdf: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        class FakeDocument:
            pictures = []
            tables = []

            def export_to_markdown(self, image_mode=None, image_placeholder=None) -> str:
                return "# Scanned document\n"

        class FakeConverter:
            def __init__(self, *, format_options):
                captured["format_options"] = format_options

            def convert(self, file_path):
                return SimpleNamespace(document=FakeDocument())

        base_pdf_config = ProcessingConfig.PdfPipelineConfig(
            backend="docling_parse",
            do_ocr=False,
            do_table_structure=False,
            force_full_page_ocr=False,
        )
        monkeypatch.setattr(
            adaptive_processor,
            "_resolve_effective_options",
            lambda: (IngestionProcessingProfile.medium, False, base_pdf_config),
        )
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: PdfAnalysisResult(
                nature=PdfNature.SCANNED,
                avg_chars_per_page=5.0,
                unique_font_count=0,
                page_count=3,
                has_embedded_text=False,
            ),
        )
        monkeypatch.setattr(
            "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.DocumentConverter",
            FakeConverter,
        )
        monkeypatch.setattr(
            "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
            lambda: SimpleNamespace(vision_model=None, ocr_model=None),
        )

        result = adaptive_processor.convert_file_to_markdown(sample_pdf, tmp_path, "doc-adaptive-1")

        assert Path(result["md_file"]).exists()
        from docling.datamodel.base_models import InputFormat

        pipeline_opts = captured["format_options"][InputFormat.PDF].pipeline_options
        assert pipeline_opts.do_ocr is True

    def test_text_native_pdf_reaches_docling_with_ocr_disabled(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        sample_pdf: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        class FakeDocument:
            pictures = []
            tables = []

            def export_to_markdown(self, image_mode=None, image_placeholder=None) -> str:
                return "# Text native document\n"

        class FakeConverter:
            def __init__(self, *, format_options):
                captured["format_options"] = format_options

            def convert(self, file_path):
                return SimpleNamespace(document=FakeDocument())

        base_pdf_config = ProcessingConfig.PdfPipelineConfig(
            backend="docling_parse",
            do_ocr=True,
            do_table_structure=True,
            force_full_page_ocr=True,
        )
        monkeypatch.setattr(
            adaptive_processor,
            "_resolve_effective_options",
            lambda: (IngestionProcessingProfile.fast, False, base_pdf_config),
        )
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: PdfAnalysisResult(
                nature=PdfNature.TEXT_NATIVE,
                avg_chars_per_page=800.0,
                unique_font_count=2,
                page_count=10,
                has_embedded_text=True,
            ),
        )
        monkeypatch.setattr(
            "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.DocumentConverter",
            FakeConverter,
        )
        monkeypatch.setattr(
            "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
            lambda: SimpleNamespace(vision_model=None, ocr_model=None),
        )

        adaptive_processor.convert_file_to_markdown(sample_pdf, tmp_path, "doc-adaptive-2")

        from docling.datamodel.base_models import InputFormat

        pipeline_opts = captured["format_options"][InputFormat.PDF].pipeline_options
        assert pipeline_opts.do_ocr is False

    def test_base_config_restored_after_convert(
        self,
        adaptive_processor: AdaptivePdfMarkdownProcessor,
        sample_pdf: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """
        Ensure _resolve_effective_options is restored even when DocumentConverter
        raises an exception, preventing state leakage between calls.
        """
        base_pdf_config = ProcessingConfig.PdfPipelineConfig(backend="docling_parse")

        original_resolve = adaptive_processor._resolve_effective_options

        monkeypatch.setattr(
            adaptive_processor,
            "_resolve_effective_options",
            lambda: (IngestionProcessingProfile.medium, False, base_pdf_config),
        )
        monkeypatch.setattr(
            adaptive_processor._analyzer,
            "analyze",
            lambda p: PdfAnalysisResult(
                nature=PdfNature.TEXT_NATIVE,
                avg_chars_per_page=500.0,
                unique_font_count=2,
                page_count=1,
                has_embedded_text=True,
            ),
        )
        monkeypatch.setattr(
            "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.DocumentConverter",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("converter error")),
        )
        monkeypatch.setattr(
            "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
            lambda: SimpleNamespace(vision_model=None, ocr_model=None),
        )

        with pytest.raises(Exception):
            adaptive_processor.convert_file_to_markdown(sample_pdf, tmp_path, "doc-adaptive-3")

        # After the exception the method-level override must have been removed
        assert adaptive_processor._resolve_effective_options is not None
