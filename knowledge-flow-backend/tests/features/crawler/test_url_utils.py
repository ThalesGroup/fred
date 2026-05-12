from knowledge_flow_backend.features.crawler.url_utils import is_allowed_scope, normalize_url


def test_normalize_url_removes_fragments_sorts_query_and_drops_tracking_params():
    normalized = normalize_url(
        "/Docs?utm_source=news&b=2&gclid=x&a=1#intro",
        "https://EXAMPLE.com:443/root/",
    )

    assert normalized == "https://example.com/Docs?a=1&b=2"


def test_scope_allows_subdomains_when_restricted():
    assert is_allowed_scope("https://docs.example.com/page", ["example.com"], True)
    assert not is_allowed_scope("https://example.org/page", ["example.com"], True)
    assert is_allowed_scope("https://example.org/page", ["example.com"], False)
