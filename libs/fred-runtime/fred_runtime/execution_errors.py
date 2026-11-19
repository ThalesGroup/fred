# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""The narrow opt-out from support-reference redaction, for pod-internal use."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

T = TypeVar("T")


def localize(sentences: Mapping[str, T], language: str | None) -> T:
    """Pick fixed wording in the user's language, English otherwise.

    `sentences` maps a primary language subtag to a sentence (or a set of
    sentences) and always has `en`; `language` is the runtime context's UI
    hint (`fr`, `fr-FR`, None).
    """

    key = (language or "").strip().lower().replace("_", "-").split("-")[0]
    return sentences.get(key, sentences["en"])


def sanitize_identifier(value: str, limit: int = 64) -> str:
    """Bound an untrusted id before it lands in a sentence a user reads."""

    printable = "".join(c if c.isprintable() else " " for c in str(value))
    collapsed = " ".join(printable.split())
    if not collapsed:
        return "(unnamed)"
    return collapsed[:limit] + "…" if len(collapsed) > limit else collapsed


class UserFacingExecutionError(RuntimeError):
    """An execution error carrying a sentence the user is meant to read.

    An execution error is otherwise redacted to a support reference, because a
    stringified exception may carry a token, an upstream body or a URL. A
    subclass passes fixed `sentences`, keyed as `localize` reads them; each
    `{field}` is filled with its value put through `sanitize_identifier`. The
    exception's own text stays internal, and is neither surfaced nor logged.
    """

    def __init__(
        self,
        sentences: Mapping[str, str],
        internal_message: str | None = None,
        /,
        **fields: str,
    ) -> None:
        safe = {name: sanitize_identifier(value) for name, value in fields.items()}
        self.sentences = {key: text.format(**safe) for key, text in sentences.items()}
        super().__init__(internal_message or self.sentences["en"])

    def user_message(self, language: str | None) -> str:
        return localize(self.sentences, language)
