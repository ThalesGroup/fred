# SPDX-License-Identifier: Apache-2.0
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import regex
from fred_pod.security.platform_access import (
    PlatformAccessPolicy,
)

Fact = str | list[str]
Reason = Literal["matched", "not_matching", "missing", "incompatible", "timeout"]


def path_key(path: list[str]) -> str:
    return json.dumps(path, ensure_ascii=True, separators=(",", ":"))


def normalize_attribute(value: object) -> Fact | None:
    if isinstance(value, str):
        return value if 0 < len(value) <= 1024 else None
    if (
        isinstance(value, list)
        and 0 < len(value) <= 32
        and all(isinstance(item, str) and 0 < len(item) <= 1024 for item in value)
    ):
        return list(value)
    return None


def extract_claims(
    payload: Mapping[str, object],
) -> tuple[dict[str, Fact], frozenset[str]]:
    facts: dict[str, Fact] = {}
    invalid: set[str] = set()
    visited = 0

    def visit(value: object, path: list[str]) -> None:
        nonlocal visited
        if visited >= 1024 or len(facts) + len(invalid) >= 256:
            return
        visited += 1
        if isinstance(value, Mapping) and len(path) < 16:
            if path:
                invalid.add(path_key(path))
            for key, child in value.items():
                if visited >= 1024 or len(facts) + len(invalid) >= 256:
                    break
                if isinstance(key, str) and key.strip() and len(key) <= 256:
                    visit(child, [*path, key])
            return
        key = path_key(path)
        normalized = normalize_attribute(value)
        if normalized is None:
            invalid.add(key)
        else:
            facts[key] = normalized

    visit(payload, [])
    return facts, frozenset(invalid)


@lru_cache(maxsize=32)
def _compile(pattern: str, case_sensitive: bool) -> regex.Pattern:
    return regex.compile(
        pattern, flags=0 if case_sensitive else regex.IGNORECASE | regex.FULLCASE
    )


@dataclass(frozen=True)
class Evaluation:
    matched: bool
    reasons: list[Reason]


def evaluate(
    policy: PlatformAccessPolicy | None,
    facts: Mapping[str, object],
    invalid: frozenset[str] = frozenset(),
) -> Evaluation:
    if policy is None:
        return Evaluation(False, [])
    deadline = time.monotonic() + 0.025
    reasons: list[Reason] = []
    timed_out = False
    for condition in policy.conditions:
        key = path_key(condition.claim)
        value = normalize_attribute(facts.get(key))
        if value is None:
            reasons.append("incompatible" if key in invalid else "missing")
            continue
        values = [value] if isinstance(value, str) else value
        operand = (
            condition.value if condition.case_sensitive else condition.value.casefold()
        )
        try:
            if condition.operator == "regex":
                matcher = _compile(condition.value, condition.case_sensitive)
                matches = []
                for item in values:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    matches.append(bool(matcher.fullmatch(item, timeout=remaining)))
                matched = any(matches)
            else:
                items = (
                    values
                    if condition.case_sensitive
                    else [item.casefold() for item in values]
                )
                if condition.operator in ("equals", "not_equals"):
                    matches = [item == operand for item in items]
                else:
                    matches = [operand in item for item in items]
                matched = (
                    not any(matches)
                    if condition.operator in ("not_equals", "not_contains")
                    else any(matches)
                )
            reasons.append("matched" if matched else "not_matching")
        except TimeoutError:
            reasons.append("timeout")
            timed_out = True
    results = [reason == "matched" for reason in reasons]
    matched = all(results) if policy.combination == "all" else any(results)
    return Evaluation(matched and not timed_out, reasons)
