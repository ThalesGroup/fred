# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
from pathlib import Path
from typing import FrozenSet

from fred_core.common.lru_cache import ThreadSafeLRUCache
from fred_core.security.structure import KeycloakUser

logger = logging.getLogger(__name__)


_WHITELIST_PATH = Path(__file__).with_name("users.txt")
_WHITELIST_CACHE = ThreadSafeLRUCache[str, tuple[float, FrozenSet[str]]](max_size=1)
_WHITELIST_CACHE_KEY = str(_WHITELIST_PATH)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _parse_whitelist(raw: str) -> FrozenSet[str]:
    users: set[str] = set()
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        users.add(_normalize_email(cleaned))
    return frozenset(users)


def _load_whitelist() -> tuple[bool, FrozenSet[str]]:
    """
    Returns (active, users).
    Active only if users.txt exists and contains at least one valid entry.
    Missing/unreadable => inactive.
    """
    try:
        mtime = _WHITELIST_PATH.stat().st_mtime
    except FileNotFoundError:
        _WHITELIST_CACHE.delete(_WHITELIST_CACHE_KEY)
        return False, frozenset()

    if not os.access(_WHITELIST_PATH, os.R_OK):
        logger.warning(
            "Whitelist file is not readable: %s (whitelist disabled)", _WHITELIST_PATH
        )
        _WHITELIST_CACHE.delete(_WHITELIST_CACHE_KEY)
        return False, frozenset()

    cached = _WHITELIST_CACHE.get(_WHITELIST_CACHE_KEY)
    if cached and cached[0] == mtime:
        users = cached[1]
        return bool(users), users

    try:
        raw = _WHITELIST_PATH.read_text(encoding="utf-8")
    except Exception:
        logger.exception(
            "Failed to read whitelist file: %s (whitelist disabled)", _WHITELIST_PATH
        )
        _WHITELIST_CACHE.delete(_WHITELIST_CACHE_KEY)
        return False, frozenset()

    users = _parse_whitelist(raw)
    _WHITELIST_CACHE.set(_WHITELIST_CACHE_KEY, (mtime, users))
    return bool(users), users


def retrieve_authorized_users() -> FrozenSet[str]:
    """Return the parsed whitelist (may be empty if inactive)."""
    return _load_whitelist()[1]


def is_whitelist_active() -> bool:
    return _load_whitelist()[0]


def is_email_whitelisted(email: str | None) -> bool:
    normalized = _normalize_email(email or "")
    if not normalized:
        return False
    return normalized in retrieve_authorized_users()


def is_user_whitelisted(user: KeycloakUser) -> bool:
    return is_email_whitelisted(user.email)
