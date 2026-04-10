from knowledge_flow_backend.features.content.content_controller import (
    build_content_disposition_header,
)


def test_build_content_disposition_header_keeps_unicode_filename_via_filename_star() -> None:
    header = build_content_disposition_header("inline", "Rapport d’avril 2026.pdf")

    assert header.startswith('inline; filename="Rapport d?avril 2026.pdf"; ')
    assert "filename*=UTF-8''Rapport%20d%E2%80%99avril%202026.pdf" in header
    header.encode("latin-1")
