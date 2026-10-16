# Copyright Thales 2026
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

"""What a deck says about its own story: the speaker notes (takeaway first,
then where the figures come from) and an illustrative chart's caption, in the
plan's language. Kept apart from :mod:`story`, whose checks need the assigner."""

from __future__ import annotations

import re
from typing import Optional

from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.plan import DeckPlan, PlanChart, SlidePlan

FIGURES_UNVERIFIED = "figures_unverified"
WIDE_RANGE_CHART = "wide_range_chart"

_FRENCH = frozenset(
    "le la les des du un une et est sont pour dans sur avec par au aux ce cette nous "
    "notre nos plus qui que en".split()
)
_ENGLISH = frozenset(
    "the a an and is are for in on with by of to this our we more which that".split()
)


def plan_language(plan: DeckPlan) -> str:
    """``fr`` or ``en``, from the plan's own words."""
    words = re.findall(
        r"[a-zà-ÿ']+",
        " ".join(
            " ".join(filter(None, [s.takeaway, s.title, s.subtitle, *s.bullets]))
            for s in plan.slides
        ).lower(),
    )
    french = sum(w in _FRENCH for w in words) + sum(
        any(c in w for c in "éèêàçù") for w in words
    )
    return "fr" if french > sum(w in _ENGLISH for w in words) else "en"


_LINES = {
    "en": {
        "source": "Source: {}",
        "user": "the user",
        "illustrative": "Illustrative figures, not from the documents.",
        "unverified": "Figures not found in the documents read.",
        "caption": "(illustrative)",
        "caption_alone": "Illustrative data",
        "bubble_size": "Bubble size: {}",
    },
    "fr": {
        "source": "Source : {}",
        "user": "l'utilisateur",
        "illustrative": "Chiffres illustratifs, non issus des documents.",
        "unverified": "Chiffres non retrouvés dans les documents lus.",
        "caption": "(illustratif)",
        "caption_alone": "Données illustratives",
        "bubble_size": "Taille des bulles : {}",
    },
}


def is_illustrative(slide: SlidePlan) -> bool:
    return lexicon.source_kind(slide.source or "") == "illustrative"


def speaker_notes(slide: SlidePlan, language: str) -> Optional[str]:
    """The takeaway first, unlabelled; then where the figures come from; then
    the model's own notes."""
    lines = _LINES[language]
    notes = [slide.takeaway] if slide.takeaway else []
    source = (slide.source or "").strip()
    if source:
        kind = lexicon.source_kind(source)
        if kind == "illustrative":
            notes.append(lines["illustrative"])
        else:
            notes.append(
                lines["source"].format(lines["user"] if kind == "user" else source)
            )
    if FIGURES_UNVERIFIED in slide.story_notes:
        notes.append(lines["unverified"])
    if slide.notes:
        notes.append(slide.notes)
    return "\n".join(notes) if notes else None


def caption(chart: PlanChart, language: str) -> str:
    """An illustrative chart's caption, said so."""
    lines = _LINES[language]
    title = (chart.title or "").strip()
    return f"{title} {lines['caption']}" if title else lines["caption_alone"]


def with_size_line(chart: PlanChart, language: str, size: str) -> str:
    """A bubble chart's caption with the size measure on its own line:
    PowerPoint has no legend for bubble sizes."""
    line = _LINES[language]["bubble_size"].format(size)
    return "\n".join(t for t in ((chart.title or "").strip(), line) if t)
