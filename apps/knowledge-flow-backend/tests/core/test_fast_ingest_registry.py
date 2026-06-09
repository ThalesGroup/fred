from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


def test_fast_ingest_default_registry_covers_supported_attachment_types() -> None:
    controller = object.__new__(IngestionController)

    registry = controller._build_fast_text_registry()

    for ext in [
        ".pdf",
        ".docx",
        ".pptx",
        ".csv",
        ".txt",
        ".md",
        ".jsonl",
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
