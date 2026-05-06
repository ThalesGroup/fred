"""
Helpers for deciding when Langfuse should be active in Fred.

Why this file exists:
- Langfuse activation was duplicated across multiple runtime paths.
- Some paths only checked the API keys, which let the SDK fall back to its
  default cloud host and spam transient DNS errors in offline deployments.
- Centralizing the rule keeps agentic runtime behavior consistent.
"""

from __future__ import annotations

import os

from langfuse import Langfuse


def _coerce_optional_string(value: str | None) -> str | None:
    """
    Normalize env values used by Langfuse configuration lookups.

    Why this function exists:
    - Fred env files often keep optional values present but empty.
    - Callers need one shared "missing or blank means disabled" rule.

    How to use it:
    - Pass a raw env value and check for `None` on return.

    Example:
    ```python
    host = _coerce_optional_string(os.getenv("LANGFUSE_BASE_URL"))
    ```
    """

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def get_langfuse_credentials() -> tuple[str, str, str] | None:
    """
    Return Langfuse host and credentials only when tracing is fully configured.

    Why this function exists:
    - Fred should only enable Langfuse when both credentials and an explicit
      host are present.
    - Requiring the host avoids accidental fallback to the default cloud
      endpoint in environments without outbound DNS/network access.

    How to use it:
    - Call this before creating a Langfuse client or callback handler.
    - Treat `None` as "Langfuse disabled for this process".

    Example:
    ```python
    config = get_langfuse_credentials()
    if config is None:
        return None
    host, public_key, secret_key = config
    ```
    """

    host = _coerce_optional_string(os.getenv("LANGFUSE_BASE_URL"))
    public_key = _coerce_optional_string(os.getenv("LANGFUSE_PUBLIC_KEY"))
    secret_key = _coerce_optional_string(os.getenv("LANGFUSE_SECRET_KEY"))
    if not host or not public_key or not secret_key:
        return None
    return host.rstrip("/"), public_key, secret_key


def build_langfuse_client() -> Langfuse | None:
    """
    Create a Langfuse client only when Fred explicitly enables tracing.

    Why this function exists:
    - Runtime entrypoints need a single safe way to create the SDK client.

    How to use it:
    - Use this from runtime bootstrap code instead of calling `Langfuse()`
      directly.

    Example:
    ```python
    client = build_langfuse_client()
    if client is not None:
        client.flush()
    ```
    """

    credentials = get_langfuse_credentials()
    if credentials is None:
        return None
    host, public_key, secret_key = credentials
    return Langfuse(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
    )
