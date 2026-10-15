#!/usr/bin/env python3
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

"""Keep the architecture dossier generated from its sources.

A chapter marks a generated block like this, the body being rewritten by `generate`:

    <!-- generated: include apps/fred-manager/openfga/model.fga text -->
    ...
    <!-- end generated -->

Directives:
    include <path> [lang]   the file, verbatim, in a fenced block
    mermaid <path>          a generated .mmd file as a mermaid block
    routes <path> <base>    the HTTP routes of an axum router
    invariants              each invariant of the dossier and the tests proving it

`check` fails when a block differs from its sources, when an invariant has no test,
or when a test cites an unknown invariant. `tidy-er <file>` shortens the relationship
labels of a tbls mermaid output. Stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1]
ROOT = DOSSIER.parents[1]
BLOCK = re.compile(
    r"(<!-- generated: (?P<directive>[^>]+?) -->\n)(?P<body>.*?)(<!-- end generated -->)",
    re.S,
)
INVARIANT_ROW = re.compile(r"^\| (I\d+) \|", re.M)
PROVES = re.compile(r"//\s*Proves:\s*([I\d, ]+)\n(?:\s*#\[[^\n]*\]\n)*\s*(?:pub )?(?:async )?fn (\w+)")
# Rust sources that may prove an invariant; extend as components are ported.
TEST_SOURCES = ["apps/fred-manager/src", "apps/fred-manager/tests"]


def chapters() -> list[Path]:
    return sorted(DOSSIER.glob("*.md"))


def fenced(lang: str, text: str) -> str:
    return f"```{lang}\n{text.rstrip()}\n```\n"


def routes(path: str, base: str) -> str:
    source = (ROOT / path).read_text()
    rows = []
    # utoipa annotations drive runtime registration and the generated client.
    for annotation, handler in re.findall(
        r"#\[utoipa::path\((.*?)\)\]\s*async fn (\w+)", source, re.S
    ):
        method, route = re.search(
            r'\b(get|post|put|patch|delete),\s*path = "([^\"]+)"', annotation
        ).groups()
        rows.append((route, method.upper(), handler))
    rows.sort()
    lines = ["| Method | Path | Handler |", "| --- | --- | --- |"]
    lines += [f"| {m} | `{base}{r}` | `{h}` |" for r, m, h in rows]
    return "\n".join(lines) + "\n"


def defined_invariants() -> list[str]:
    """Invariant ids defined in hand-written tables; generated blocks only cite them."""
    found: list[str] = []
    for chapter in chapters():
        found += INVARIANT_ROW.findall(BLOCK.sub("", chapter.read_text()))
    return found


def proofs() -> dict[str, list[str]]:
    """Invariant id -> `path::test` names citing it."""
    cited: dict[str, list[str]] = {}
    for base in TEST_SOURCES:
        for file in sorted((ROOT / base).rglob("*.rs")):
            for ids, name in PROVES.findall(file.read_text()):
                for invariant in re.findall(r"I\d+", ids):
                    cited.setdefault(invariant, []).append(f"{file.relative_to(ROOT)}::{name}")
    return cited


def invariants() -> str:
    cited = proofs()
    lines = ["| Invariant | Proved by |", "| --- | --- |"]
    for invariant in defined_invariants():
        tests = "<br>".join(f"`{t}`" for t in cited.get(invariant, [])) or "**none**"
        lines.append(f"| {invariant} | {tests} |")
    return "\n".join(lines) + "\n"


def render(directive: str) -> str:
    kind, *args = directive.split()
    if kind == "include":
        return fenced(args[1] if len(args) > 1 else "", (ROOT / args[0]).read_text())
    if kind == "mermaid":
        return fenced("mermaid", (ROOT / args[0]).read_text())
    if kind == "routes":
        return routes(args[0], args[1])
    if kind == "invariants":
        return invariants()
    raise ValueError(f"unknown directive: {directive}")


def regenerate(text: str) -> str:
    return BLOCK.sub(lambda m: m.group(1) + render(m.group("directive")) + m.group(4), text)


def generate() -> None:
    for chapter in chapters():
        text = chapter.read_text()
        updated = regenerate(text)
        if updated != text:
            chapter.write_text(updated)
            print(f"updated {chapter.relative_to(ROOT)}")


def check() -> int:
    problems = []
    for chapter in chapters():
        text = chapter.read_text()
        if regenerate(text) != text:
            problems.append(f"{chapter.relative_to(ROOT)}: generated blocks are stale (make generate)")
    defined, cited = defined_invariants(), proofs()
    problems += [f"invariant {i} is defined twice" for i in set(defined) if defined.count(i) > 1]
    problems += [f"invariant {i} has no test citing it" for i in defined if i not in cited]
    problems += [f"{t} cites unknown invariant {i}" for i, ts in cited.items() if i not in defined for t in ts]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def tidy_er(path: str) -> None:
    """Shorten tbls relationship labels to the referencing columns."""
    file = ROOT / path
    text = re.sub(r'"FOREIGN KEY \(([^)]*)\) REFERENCES [^"]*"', r'"\1"', file.read_text())
    file.write_text(text.replace('"public.', '"').replace("uuid__", "uuid_array"))


if __name__ == "__main__":
    command, *rest = sys.argv[1:] or ["check"]
    if command == "generate":
        generate()
    elif command == "check":
        sys.exit(check())
    elif command == "tidy-er":
        tidy_er(rest[0])
    else:
        sys.exit(f"unknown command {command}")
