"""Startup diagnostics must precede ingestion and preserve unrelated import errors."""

import importlib
from types import SimpleNamespace

import pytest

from knowledge_flow_backend.application_context import validate_profile_input_processor_config
from knowledge_flow_backend.common.structures import ProcessingConfig
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor import optional_pymupdf

PREFIX = "knowledge_flow_backend.core.processors.input."
LITE = PREFIX + "lightweight_markdown_processor.lite2_pdf_to_md_processor.LitePdfMarkdownProcessor"
ADVANCED = PREFIX + "pdf_markdown_processor.pdf_markdown_processor.PdfMarkdownProcessor"


@pytest.mark.parametrize("profile", ["fast", "medium", "rich"])
@pytest.mark.parametrize("class_path", [LITE, ADVANCED])
def test_each_selectable_profile_requires_its_optional_dependencies(app_context, monkeypatch, profile, class_path):
    config = app_context.configuration.model_copy(deep=True)
    selected = config.processing.get_profile_config(profile)
    selected.input_processors = [ProcessingConfig.ProfileInputProcessorConfig(suffix=".pdf", class_path=class_path)]
    selected.pdf.extractor = "pymupdf"

    def missing(name):
        raise ModuleNotFoundError("No module named fitz", name="fitz")

    monkeypatch.setattr(optional_pymupdf, "import_module", missing)
    with pytest.raises(ImportError, match=f"processing.profiles.{profile}.*INSTALL_PYMUPDF=true"):
        validate_profile_input_processor_config(config)


@pytest.mark.parametrize("failure", [ImportError("broken binary"), ModuleNotFoundError("unrelated", name="another_package")])
def test_broken_installation_is_not_reported_as_missing_extra(monkeypatch, failure):
    def fail(name):
        raise failure

    monkeypatch.setattr(optional_pymupdf, "import_module", fail)
    with pytest.raises(type(failure)) as raised:
        optional_pymupdf.require_pymupdf("test selection")
    assert raised.value is failure


def test_installing_extra_does_not_select_it(monkeypatch):
    monkeypatch.setattr(optional_pymupdf, "import_module", lambda name: SimpleNamespace())
    optional_pymupdf.require_pymupdf("installed")
    assert ProcessingConfig.PdfPipelineConfig().extractor == "docling"


def test_optional_processor_modules_import_without_optional_dependencies(monkeypatch):
    def fail(name):
        pytest.fail(f"Eager optional import: {name}")

    monkeypatch.setattr(optional_pymupdf, "import_module", fail)
    for module in ("lightweight_markdown_processor.lite2_pdf_to_md_processor", "pdf_markdown_processor.pymupdf_processor"):
        importlib.reload(importlib.import_module(PREFIX + module))


def test_unknown_advanced_engine_is_rejected():
    from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor

    with pytest.raises(ValueError, match="Unknown PDF extractor"):
        PdfMarkdownProcessor()._build_extractor("typo")
