"""
Offline unit tests for fred_core.security.whitelist_access_control.access_control.

Strategy:
- _normalize_email and _parse_whitelist are pure — test directly.
- _load_whitelist reads a hardcoded path; monkeypatch the module-level
  _WHITELIST_PATH to point at a tmp_path file for integration of the full
  read/cache/parse pipeline.
- is_email_whitelisted / is_user_whitelisted use the same pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fred_core.security.whitelist_access_control.access_control as _wl_module
from fred_core.security.structure import KeycloakUser
from fred_core.security.whitelist_access_control.access_control import (
    _normalize_email,
    _parse_whitelist,
    is_email_whitelisted,
    is_user_whitelisted,
)


# ---------------------------------------------------------------------------
# _normalize_email
# ---------------------------------------------------------------------------


class TestNormalizeEmail:
    def test_lowercases(self) -> None:
        assert _normalize_email("User@Example.COM") == "user@example.com"

    def test_strips_whitespace(self) -> None:
        assert _normalize_email("  user@example.com  ") == "user@example.com"

    def test_empty_string(self) -> None:
        assert _normalize_email("") == ""


# ---------------------------------------------------------------------------
# _parse_whitelist
# ---------------------------------------------------------------------------


class TestParseWhitelist:
    def test_single_email(self) -> None:
        result = _parse_whitelist("alice@example.com\n")
        assert "alice@example.com" in result

    def test_multiple_emails(self) -> None:
        result = _parse_whitelist("alice@example.com\nbob@example.com\n")
        assert result == frozenset({"alice@example.com", "bob@example.com"})

    def test_comment_lines_ignored(self) -> None:
        result = _parse_whitelist("# this is a comment\nalice@example.com\n")
        assert "alice@example.com" in result
        assert len(result) == 1

    def test_blank_lines_ignored(self) -> None:
        result = _parse_whitelist("\n\nalice@example.com\n\n")
        assert result == frozenset({"alice@example.com"})

    def test_emails_normalized_to_lowercase(self) -> None:
        result = _parse_whitelist("ALICE@EXAMPLE.COM\n")
        assert "alice@example.com" in result

    def test_empty_content_returns_empty(self) -> None:
        assert _parse_whitelist("") == frozenset()

    def test_only_comments_returns_empty(self) -> None:
        assert _parse_whitelist("# comment\n# another\n") == frozenset()


# ---------------------------------------------------------------------------
# _load_whitelist / is_email_whitelisted via monkeypatched path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_whitelist_cache(monkeypatch, tmp_path):
    """
    Point _WHITELIST_PATH at a temp file and clear the LRU cache before each test.
    The cache key is str(_WHITELIST_PATH), so patching the path also invalidates
    any stale cached entry from other tests.
    """
    whitelist_file = tmp_path / "users.txt"
    monkeypatch.setattr(_wl_module, "_WHITELIST_PATH", whitelist_file)
    monkeypatch.setattr(
        _wl_module, "_WHITELIST_CACHE_KEY", str(whitelist_file)
    )
    _wl_module._WHITELIST_CACHE.clear()
    yield
    _wl_module._WHITELIST_CACHE.clear()


class TestIsEmailWhitelisted:
    def test_missing_file_returns_false(self) -> None:
        # tmp file was not created — whitelist is inactive
        assert is_email_whitelisted("alice@example.com") is False

    def test_listed_email_returns_true(self, tmp_path) -> None:
        _wl_module._WHITELIST_PATH.write_text("alice@example.com\n", encoding="utf-8")
        assert is_email_whitelisted("alice@example.com") is True

    def test_unlisted_email_returns_false(self, tmp_path) -> None:
        _wl_module._WHITELIST_PATH.write_text("alice@example.com\n", encoding="utf-8")
        assert is_email_whitelisted("bob@example.com") is False

    def test_case_insensitive_match(self, tmp_path) -> None:
        _wl_module._WHITELIST_PATH.write_text("alice@example.com\n", encoding="utf-8")
        assert is_email_whitelisted("ALICE@EXAMPLE.COM") is True

    def test_none_email_returns_false(self) -> None:
        assert is_email_whitelisted(None) is False

    def test_empty_string_email_returns_false(self) -> None:
        assert is_email_whitelisted("") is False


class TestIsUserWhitelisted:
    def test_whitelisted_user(self, tmp_path) -> None:
        _wl_module._WHITELIST_PATH.write_text("alice@example.com\n", encoding="utf-8")
        user = KeycloakUser(
            uid="u1", username="alice", email="alice@example.com", roles=[]
        )
        assert is_user_whitelisted(user) is True

    def test_non_whitelisted_user(self, tmp_path) -> None:
        _wl_module._WHITELIST_PATH.write_text("alice@example.com\n", encoding="utf-8")
        user = KeycloakUser(
            uid="u2", username="bob", email="bob@example.com", roles=[]
        )
        assert is_user_whitelisted(user) is False
