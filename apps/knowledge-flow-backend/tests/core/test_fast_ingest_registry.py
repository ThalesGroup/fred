from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_doc_processor import FastLiteDocProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_ppt_processor import FastLitePptProcessor
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


def test_fast_ingest_default_registry_covers_supported_attachment_types() -> None:
    controller = object.__new__(IngestionController)

    registry = controller._build_fast_text_registry()

    for ext in [
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".csv",
        ".txt",
        ".md",
        ".xlsx",
        ".xls",
        ".xlsm",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".ico",
    ]:
        assert ext in registry, f"missing fast-ingest processor for {ext}"


def test_fast_ingest_default_registry_maps_legacy_office_formats() -> None:
    """Legacy .doc/.ppt attachments must route to their LibreOffice-backed fast processors."""
    controller = object.__new__(IngestionController)

    registry = controller._build_fast_text_registry()

    assert registry[".doc"] is FastLiteDocProcessor
    assert registry[".ppt"] is FastLitePptProcessor
