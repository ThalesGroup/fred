from __future__ import annotations

import re
from typing import Iterable


_FRENCH_MARKERS = {
    "le",
    "la",
    "les",
    "des",
    "risque",
    "risques",
    "mesure",
    "mesures",
    "mitigation",
    "traitement",
    "responsable",
    "proprietaire",
    "echeance",
    "date",
    "plan",
    "document",
    "dva",
}

_ENGLISH_MARKERS = {
    "risk",
    "risks",
    "mitigation",
    "treatment",
    "owner",
    "target",
    "date",
    "plan",
    "document",
    "dva",
}


def detect_language(texts: Iterable[str | None]) -> str:
    """
    Naive FR/EN detector for DVA passages.
    Returns "fr" or "en".
    """
    french_hits = 0
    english_hits = 0
    for text in texts:
        if not text:
            continue
        tokens = set(re.findall(r"[a-zA-Zéèêàùûîôç]+", text.lower()))
        french_hits += len(tokens & _FRENCH_MARKERS)
        english_hits += len(tokens & _ENGLISH_MARKERS)
    if french_hits >= english_hits:
        return "fr"
    return "en"


def bilingual_queries(
    *,
    primary_language: str,
    english_queries: Iterable[str],
    french_queries: Iterable[str],
) -> list[str]:
    """
    Return queries ordered with primary language first, then the fallback language.
    """
    primary = [
        q for q in (english_queries if primary_language == "en" else french_queries)
    ]
    fallback = [
        q for q in (french_queries if primary_language == "en" else english_queries)
    ]
    return [q for q in primary + fallback if q]
