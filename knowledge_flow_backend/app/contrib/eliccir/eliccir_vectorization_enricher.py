# Copyright Thales 2025 - Apache 2.0
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class CirAutoTag:
    tag: str
    confidence: float = 0.6
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    hint: Optional[str] = None


@dataclass
class CirEvent:
    kind: str  # 'experiment' | 'failure' | 'commit' | 'event'
    date: Optional[datetime] = None
    snippet: Optional[str] = None


class CirEnrichment:
    def __init__(self, tags: List[CirAutoTag], events: List[CirEvent]):
        self.tags = tags
        self.events = events


# --- crude French patterns (fast to run, easy to tune) ---
_VERROU_PAT = re.compile(r"\b(verrou(?:x)?|incertitude(?:s)?|blocage(?:s)?)\b", re.I)
_EXP_PAT = re.compile(r"\b(expériment\w+|prototype|poc|essai|benchmark|ablation|mesure(?:s)?)\b", re.I)
_FAIL_PAT = re.compile(r"\b(échec|ko|fail(?:ed)?|incident|limite(?:s)?)\b", re.I)
_COMMIT_PAT = re.compile(r"\b(commit|merge|pull request|PR|issue #?\d+)\b", re.I)
_DATE_PAT = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")


def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


class CirEnricher:
    """
    Lightweight text enricher to run AFTER preview extraction and BEFORE vectorization.
    Produces:
      - tags: 'verrou' | 'experiment' | 'failure'
      - events: [{kind, date?, snippet}]
    """

    CIR_TAGS_PRIORITY = ("verrou", "experiment", "failure")

    def enrich_text(self, text: str, *, max_events: int = 8) -> CirEnrichment:
        tags: List[CirAutoTag] = []
        events: List[CirEvent] = []

        for m in _VERROU_PAT.finditer(text):
            tags.append(CirAutoTag("verrou", 0.7, m.start(), m.end(), m.group(0)))
        for m in _EXP_PAT.finditer(text):
            tags.append(CirAutoTag("experiment", 0.6, m.start(), m.end(), m.group(0)))
        for m in _FAIL_PAT.finditer(text):
            tags.append(CirAutoTag("failure", 0.6, m.start(), m.end(), m.group(0)))

        # crude events via dates + local context
        for m in _DATE_PAT.finditer(text):
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            window = text[start:end]
            kind = "experiment" if _EXP_PAT.search(window) else "failure" if _FAIL_PAT.search(window) else "commit" if _COMMIT_PAT.search(window) else "event"
            events.append(CirEvent(kind=kind, date=_parse_date(m.group(1)), snippet=window))
            if len(events) >= max_events:
                break

        return CirEnrichment(tags, events)


def merge_tags(existing: List[str] | None, new_tags: List[str]) -> List[str]:
    seen = set(existing or [])
    for t in new_tags:
        if t not in seen:
            seen.add(t)
    # keep CIR tags first for ergonomics
    ordered = [t for t in ("verrou", "experiment", "failure") if t in seen]
    ordered += [t for t in seen if t not in {"verrou", "experiment", "failure"}]
    return ordered
