import importlib

server_mcp = importlib.import_module(
    "agentic_backend.academy.08_ecoadviser.geo_distance_service.server_mcp"
)
NominatimClient = server_mcp.NominatimClient


def test_query_variants_cover_multi_part_streets(monkeypatch) -> None:
    """Ensure the geocoder generates generic fallbacks for multi-part Lyon streets."""
    monkeypatch.delenv("ECO_GEO_CITY_KEYWORDS", raising=False)

    client = NominatimClient()
    variants = client._enumerate_query_variants("44 boulevard Marius Vivier Merle, Lyon")
    normalized = [value for value, _ in variants]

    assert any("boulevard vivier-merle" in option.lower() for option in normalized)


def test_query_variants_strip_accents_and_punctuation(monkeypatch) -> None:
    """Ensure diacritics/hyphens/apostrophes are simplified for POI lookups."""
    monkeypatch.delenv("ECO_GEO_CITY_KEYWORDS", raising=False)

    client = NominatimClient()
    variants = client._enumerate_query_variants("Hôtel-Dieu de Lyon, 1 Place de l'Hôpital, 69002 Lyon, France")
    normalized = [value.lower() for value, _ in variants]
    reasons = [reason for _, reason in variants]

    assert any("hotel dieu de lyon" in option for option in normalized)
    assert "primary_component" in reasons
