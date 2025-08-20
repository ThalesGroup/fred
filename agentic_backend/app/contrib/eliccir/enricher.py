import re
from typing import List, Optional

from openai import BaseModel
from pydantic import Field
from datetime import datetime

class CirAutoTag(BaseModel):
    tag: str
    confidence: float = 0.5
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    hint: Optional[str] = None


class CirEvent(BaseModel):
    kind: str # 'commit','meeting','experiment','benchmark','failure'
    date: Optional[datetime] = None
    title: Optional[str] = None
    ref: Optional[str] = None
    snippet: Optional[str] = None


class CirEnrichment(BaseModel):
    tags: List[CirAutoTag] = Field(default_factory=list)
    events: List[CirEvent] = Field(default_factory=list)


_VERROU_PAT = re.compile(r"\b(verrou(?:x)?|incertitude(?:s)?|blocage(?:s)?)\b", re.I)
_EXP_PAT = re.compile(r"\b(expériment\w+|prototype|PoC|essai|benchmark|ablation)\b", re.I)
_FAIL_PAT = re.compile(r"\b(échec|ko|fail(?:ed)?|limite(?:s)?)\b", re.I)
_DATE_PAT = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")
_COMMIT_PAT = re.compile(r"\b(commit|merge|PR|pull request|issue #?\d+)\b", re.I)

def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
        return None

class CirEnricher:
    """
    Lightweight enrichment pass to be called *after preview extraction* and *before* vectorization.
    Input: plain text and base metadata. Output: additional tags and structured events.
    """
    def enrich_text(self, text: str) -> CirEnrichment:
        tags: List[CirAutoTag] = []
        events: List[CirEvent] = []


        for m in _VERROU_PAT.finditer(text):
            tags.append(CirAutoTag(tag="verrou", confidence=0.7, span_start=m.start(), span_end=m.end(), hint=m.group(0)))
        for m in _EXP_PAT.finditer(text):
            tags.append(CirAutoTag(tag="experiment", confidence=0.6, span_start=m.start(), span_end=m.end(), hint=m.group(0)))
        for m in _FAIL_PAT.finditer(text):
            tags.append(CirAutoTag(tag="failure", confidence=0.6, span_start=m.start(), span_end=m.end(), hint=m.group(0)))


        # crude event extraction from dates + nearby keywords
        for m in _DATE_PAT.finditer(text):
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            window = text[start:end]
            kind = "experiment" if _EXP_PAT.search(window) else ("failure" if _FAIL_PAT.search(window) else ("commit" if _COMMIT_PAT.search(window) else "event"))
            events.append(CirEvent(kind=kind, date=_parse_date(m.group(1)), snippet=window))


        return CirEnrichment(tags=tags, events=events)