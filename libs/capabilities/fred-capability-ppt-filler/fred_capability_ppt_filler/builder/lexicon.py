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

"""Sample-text and annotation vocabularies of the template analysis.

Everything here is a plain word list, kept in one place. Sample text never
decides what is fillable: it serves the after-render check and keeps a
repeated sample box from passing for a footer.
"""

from __future__ import annotations

import re
import unicodedata

# Phrases designers type into a zone to say "put your text here". Matched on
# the normalized (lower-case, accent-free) text: prefixes at the start only,
# fragments anywhere.
_SAMPLE_PREFIXES = (
    "cliquez ici",
    "cliquer ici",
    "click here",
    "click to",
    "changez ce",
    "changer ce",
    "change this",
    "modifiez",
    "modifier le",
    "inserez",
    "inserer",
    "insert ",
    "type here",
    "tapez",
    "saisissez",
    "your text",
    "votre texte",
    "lorem ipsum",
    "titre du",
    "titre de la",
    "titre de",
    "sous-titre",
    "sous titre",
    "title of",
    "subtitle",
    "placeholder",
    "espace reserve",
    "nom prenom",
    "nom et prenom",
    "prenom nom",
    "poste ",
    "intitule du poste",
    "job title",
    "numero de telephone",
    "phone number",
    "add text",
    "ajouter du texte",
    "ajoutez",
    "premiere etape",
    "deuxieme etape",
    "troisieme etape",
    "step ",
    "etape ",
    "kpi",
    "message cle",
    "key message",
)

_SAMPLE_FRAGMENTS = (
    "lorem ipsum",
    "cliquez ici",
    "click here",
    "changez ce texte",
    "changer ce texte",
    "change this text",
    "ajouter du texte",
    "add text",
    "type here",
    "placeholder",
)

_SAMPLE_EXACT = frozenset(
    {
        "nom",
        "name",
        "prenom",
        "email",
        "e-mail",
        "mail",
        "telephone",
        "phone",
        "titre",
        "title",
        "texte",
        "text",
        "sous-titre",
        "subtitle",
        "date",
        "auteur",
        "author",
        "legende",
        "caption",
        "description",
        "contact",
        "poste",
        "fonction",
    }
)

# Words that make a slide a contact card.
CONTACT_WORDS = frozenset(
    {
        "contact",
        "nom",
        "prenom",
        "name",
        "email",
        "e-mail",
        "mail",
        "telephone",
        "phone",
        "poste",
        "fonction",
        "job",
    }
)

# Closing words render.py and plan.py still match on. Prefix match on the
# normalized name.
CLOSING_NAMES = ("merci", "thank", "fin", "end", "closing", "questions")

# Names that state a slide kind, first match wins: a layout name, a declared
# shape name or an example slide's title ("Planche de processus"). Each is a
# prefix of the normalized name or of one of its words.
KIND_NAMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "cover",
        ("couverture", "cover", "title slide", "diapositive de titre", "page de garde"),
    ),
    ("section", ("chapitre", "section", "partie", "divider", "intercalaire")),
    (
        "agenda",
        (
            "sommaire",
            "agenda",
            "ordre du jour",
            "table des matieres",
            "table of contents",
        ),
    ),
    ("closing", ("merci", "thank", "closing", "questions", "contact")),
    ("quote", ("message cle", "key message", "citation", "quote", "verbatim")),
    ("team", ("equipe", "team", "organigramme", "org chart", "trombinoscope")),
    ("timeline", ("timeline", "chronologie", "frise", "roadmap", "jalons")),
    ("process", ("processus", "process", "etapes", "steps")),
    ("figures", ("chiffres", "key figures", "kpi", "indicateurs", "figures")),
)

# Shape names an author may set in PowerPoint's Selection pane. The name is
# normalized (lower-case, accents stripped, `_`/`-`/space folded).
SHAPE_NAME_ROLES = {
    "title": "title",
    "titre": "title",
    "subtitle": "subtitle",
    "sous titre": "subtitle",
    "heading": "heading",
    "entete": "heading",
    "body": "body",
    "corps": "body",
    "texte": "body",
    "text": "body",
    "caption": "caption",
    "legende": "caption",
    "number": "number",
    "numero": "number",
    "value": "number",
    "valeur": "number",
    "label": "label",
    "libelle": "label",
    "image": "image",
    "picture": "image",
    "photo": "image",
    "keep": "keep",
    "fixe": "keep",
    "static": "keep",
    "decor": "keep",
    "decoration": "keep",
}

# Speaker-notes directives, each on its own line: `kind: cards`, `label: KPI`.
# `intent:` and the old intent names are still read so older decks keep working.
KIND_NOTE = re.compile(
    r"^\s*(?:kind|intent)\s*:\s*([a-z_]+)\s*$", re.IGNORECASE | re.MULTILINE
)
LEGACY_KINDS = {
    "title": "cover",
    "content": "bullets",
    "steps": "process",
    "statement": "quote",
    "contact": "closing",
}
LABEL_NOTE = re.compile(r"^\s*label\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

# Titles of resource pages (Slidesgo/SlidesCarnival font, palette, credits
# sheets). Not "icons": "3 icons + text" is a design, icon sheets are found
# by their layout. Bare "resources" only alone.
_LIBRARY_TITLE = re.compile(
    r"\b(fonts|typography|typographie|palettes?"
    r"|attributions?|credits|instructions for use|presentation maker|this template"
    r"|ce modele|(graphic|alternative|editable) resources|ressources graphiques)\b"
    r"|^(resources|ressources)$"
)
_LIBRARY_TITLE_WORDS = 7

# PowerPoint's own naming: any words followed by a space and a counter.
_AUTO_NAME = re.compile(r"^.*\s\d+$")

_NUMBERISH = re.compile(
    r"^[\s#]*[0-9]{1,4}([.,][0-9]+)?\s*(%|€|\$|k|m|x|/[0-9]+)?\s*$", re.IGNORECASE
)
_YEAR = re.compile(r"^(19|20)[0-9]{2}$")


def normalize(text: str) -> str:
    """Lower-case, accent-free, whitespace-folded form used by every matcher."""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    return re.sub(r"[\s_\-]+", " ", stripped).strip().lower()


def is_sample_text(text: str) -> bool:
    """True when ``text`` reads as designer sample text rather than content."""
    norm = normalize(text)
    if not norm:
        return False
    if norm in _SAMPLE_EXACT:
        return True
    if any(norm.startswith(prefix) for prefix in _SAMPLE_PREFIXES):
        return True
    return any(fragment in norm for fragment in _SAMPLE_FRAGMENTS)


def is_numberish(text: str) -> bool:
    """A figure a card or an agenda entry shows big: `01`, `60%`, `2024`, `3`."""
    return bool(_NUMBERISH.match(text.strip()))


def is_year(text: str) -> bool:
    return bool(_YEAR.match(text.strip()))


def role_from_shape_name(name: str) -> str | None:
    """Role declared through a Selection-pane shape name, else None.

    PowerPoint's automatic names (`TextBox 12`, `Title 1`, `Image 44`,
    `Titre 3`) are `<words> <number>` and never count as a declaration. A
    declared name is a vocabulary word, optionally followed by a `_`/`-`
    suffix (`heading_2`, `image-main`).
    """
    if is_auto_name(name):
        return None
    norm = normalize(name)
    base = norm.split(" ", 1)[0] if " " in norm else norm
    if base not in SHAPE_NAME_ROLES and norm in SHAPE_NAME_ROLES:
        base = norm
    return SHAPE_NAME_ROLES.get(base)


def is_auto_name(name: str) -> bool:
    """PowerPoint's automatic shape names (`TextBox 12`) declare nothing."""
    return bool(_AUTO_NAME.match(name.strip()))


def kind_from_name(name: str) -> str | None:
    """The slide kind a name states (see :data:`KIND_NAMES`), else None."""
    for kind, prefixes in KIND_NAMES:
        if name_matches(name, prefixes):
            return kind
    return None


def name_matches(name: str, prefixes: tuple[str, ...]) -> bool:
    norm = normalize(name)
    return any(norm.startswith(prefix) or f" {prefix}" in norm for prefix in prefixes)


def is_library_title(title: str) -> bool:
    """A short title naming a resource page ("Nature icons", "Fonts")."""
    norm = normalize(title)
    return (
        len(norm.split()) <= _LIBRARY_TITLE_WORDS
        and _LIBRARY_TITLE.search(norm) is not None
    )


def has_contact_words(texts: list[str]) -> bool:
    words = set()
    for text in texts:
        words.update(normalize(text).replace("-", " ").split())
    return len(words & CONTACT_WORDS) >= 2
