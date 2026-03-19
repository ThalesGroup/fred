from __future__ import annotations

from agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.shared.language import (
    bilingual_queries,
    detect_language,
)


def test_language_detection_prefers_french() -> None:
    text = "Table des risques et mesures de mitigation"
    assert detect_language([text]) == "fr"


def test_bilingual_query_ordering() -> None:
    queries = bilingual_queries(
        primary_language="fr",
        english_queries=["risk table"],
        french_queries=["table des risques"],
    )
    assert queries[0] == "table des risques"
