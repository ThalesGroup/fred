from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAM_NAMES = {"gclid", "fbclid"}


def normalize_url(url: str, base_url: str | None = None) -> str:
    """
    Normalize one URL for crawl deduplication and scope checks.

    Why this exists:
    - crawler state uses normalized URLs as its uniqueness key, so relative links,
      fragments, and tracking parameters must collapse to one stable value.

    How to use:
    - pass an absolute URL or a relative URL with `base_url`.

    Example:
    - `normalize_url("/Docs?b=2&utm_x=1&a=1#top", "https://EXAMPLE.com")`
      returns `https://example.com/Docs?a=1&b=2`.
    """
    joined = urljoin(base_url, url) if base_url else url
    parts = urlsplit(joined)
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("URL must include a host")
    netloc = host
    if parts.port and not ((scheme == "http" and parts.port == 80) or (scheme == "https" and parts.port == 443)):
        netloc = f"{host}:{parts.port}"

    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_PARAM_NAMES or any(lowered.startswith(prefix) for prefix in TRACKING_PARAM_PREFIXES):
            continue
        query_pairs.append((key, value))
    query = urlencode(sorted(query_pairs), doseq=True)
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def url_host(url: str) -> str:
    """
    Return the lowercase hostname for a URL.

    Why this exists:
    - scope checks, rate limiting, and robots caches all key by host.

    How to use:
    - pass a normalized or absolute URL.
    """
    host = urlsplit(url).hostname
    if not host:
        raise ValueError("URL must include a host")
    return host.lower()


def is_allowed_scope(url: str, allowed_domains: list[str], restrict_to_domain: bool) -> bool:
    """
    Decide whether a URL may enter the frontier.

    Why this exists:
    - website crawls must not drift across unrelated domains unless the caller
      explicitly disables domain restriction.

    How to use:
    - pass a normalized URL and the source's allowed domains.
    """
    if not restrict_to_domain:
        return True
    host = url_host(url)
    allowed = {domain.lower() for domain in allowed_domains}
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed)
