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

    <!-- generated: include apps/control-plane/src/authorization.rs rust -->
    ...
    <!-- end generated -->

Directives:
    include <path> [lang]   the file, verbatim, in a fenced block
    mermaid <path>          a generated .mmd file as a mermaid block
    routes <path> <base>    the HTTP routes of an axum router
    openapi <path> [groups...] operations and schemas, optionally filtered by route group
    invariants              each invariant of the dossier and the tests proving it

`check` fails when a block differs from its sources, when an invariant has no test,
or when a test cites an unknown invariant. `tidy-er <file>` shortens the relationship
labels of a tbls mermaid output. Stdlib only.

`generate [markdown paths...]` and `check [markdown paths...]` can target technical
references outside the dossier. Without paths, check also verifies its invariants.
"""

from __future__ import annotations

import json
import re
import sys
from itertools import takewhile
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1]
ROOT = DOSSIER.parents[1]
BLOCK = re.compile(
    r"(<!-- generated: (?P<directive>[^>]+?) -->\n)(?P<body>.*?)(<!-- end generated -->)",
    re.S,
)
INVARIANT_ROW = re.compile(r"^\| (I\d+) \|", re.M)
PROVES = re.compile(
    r"//\s*Proves:\s*([I\d, ]+)\n(?:\s*#\[[^\n]*\]\n)*\s*(?:pub )?(?:async )?fn (\w+)"
)
# Rust sources that may prove an invariant; extend as components are ported.
TEST_SOURCES = ["apps/control-plane/src", "apps/control-plane/tests"]


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
            r'\b(get|post|put|patch|delete),\s*path\s*=\s*"([^\"]+)"', annotation
        ).groups()
        rows.append((route, method.upper(), handler))
    rows.sort()
    lines = ["| Method | Path | Handler |", "| --- | --- | --- |"]
    lines += [f"| {m} | `{base}{r}` | `{h}` |" for r, m, h in rows]
    return "\n".join(lines) + "\n"


METHODS = ["get", "post", "put", "patch", "delete"]
LIMITS = {
    "minimum": ">=",
    "maximum": "<=",
    "minLength": "min length",
    "maxLength": "max length",
    "minItems": "min items",
    "maxItems": "max items",
}


def anchor(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def prose(text: str | None) -> str:
    return " ".join((text or "").split()).replace("|", "\\|")


def type_of(schema: dict) -> str:
    """One-line type expression; component references link to their schema section."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[1]
        return f"[`{name}`](#{anchor(name)})"
    for combinator in ("oneOf", "anyOf", "allOf"):
        if combinator in schema:
            return " or ".join(type_of(s) for s in schema[combinator])
    if "enum" in schema:
        return ", ".join(f"`{v}`" for v in schema["enum"])
    kinds = schema.get("type", "any")
    nullable = isinstance(kinds, list) and "null" in kinds
    kind = (
        next((k for k in kinds if k != "null"), "null")
        if isinstance(kinds, list)
        else kinds
    )
    if kind == "array":
        text = f"array of {type_of(schema.get('items', {}))}"
    elif kind == "object" and isinstance(schema.get("additionalProperties"), dict):
        text = f"map of {type_of(schema['additionalProperties'])}"
    else:
        text = f"{kind} ({schema['format']})" if "format" in schema else kind
    text += "".join(
        f", {label} {schema[key]}" for key, label in LIMITS.items() if key in schema
    )
    return text + (" or null" if nullable else "")


def row(*cells: str) -> str:
    return "| " + " | ".join(cells) + " |"


def fields(schema: dict) -> list[str]:
    required = set(schema.get("required", []))
    lines = [row("Field", "Type", "Required", "Description"), row(*["---"] * 4)]
    lines += [
        row(
            f"`{name}`",
            type_of(field),
            "yes" if name in required else "",
            field_description(field),
        )
        for name, field in sorted(schema["properties"].items())
    ]
    return lines + [""]


def field_description(schema: dict) -> str:
    text = prose(schema.get("description"))
    if "default" in schema:
        text += f" Default: `{json.dumps(schema['default'])}`."
    return text.strip()


def variant_label(schema: dict) -> str:
    """Name a serde-tagged variant by its single-value discriminator, if it has one."""
    for name, field in sorted(schema.get("properties", {}).items()):
        if len(field.get("enum", [])) == 1:
            return f"`{name}` = `{field['enum'][0]}`"
    return type_of(schema)


def schema_section(name: str, schema: dict) -> list[str]:
    lines = [f"### {name}", ""]
    if schema.get("description"):
        lines += [prose(schema["description"]), ""]
    if "properties" in schema:
        return lines + fields(schema)
    parts = schema.get("allOf", [])
    if parts and all("$ref" in p or "properties" in p for p in parts):
        bases = [type_of(p) for p in parts if "$ref" in p]
        lines += [f"Extends {', '.join(bases)} with:", ""]
        for part in parts:
            if "properties" in part:
                lines += fields(part)
        return lines
    variants = schema.get("oneOf", [])
    if any("properties" in v for v in variants):
        lines += ["One of:", ""]
        for variant in variants:
            lines += [f"- {variant_label(variant)}", ""]
            if "properties" in variant:
                lines += fields(variant)
        return lines
    return lines + [
        f"{'One of: ' if 'enum' in schema else 'Type: '}{type_of(schema)}.",
        "",
    ]


def body(content: dict, *, show_media: bool = False) -> str:
    rendered = []
    for media, value in content.items():
        text = type_of(value.get("schema", {}))
        rendered.append(
            text
            if media == "application/json" and not show_media
            else f"{text} (`{media}`)"
        )
    return " or ".join(rendered) or "no body"


def summary_of(op: dict) -> str:
    summary, description = op.get("summary"), op.get("description")
    return prose(
        f"{summary.rstrip('.')}. {description}"
        if summary and description
        else summary or description
    )


def overview(operations: list[tuple[str, str, dict]]) -> list[str]:
    """One row per operation, linking to its section, with its summary's first sentence."""
    lines = [row("Method", "Path", "Summary"), row(*["---"] * 3)]
    for path, method, op in operations:
        first = summary_of(op).split(". ", 1)[0].rstrip(".")
        lines.append(
            row(
                method.upper(),
                f"[{path}](#{anchor(f'{method.upper()} {path}')})",
                first,
            )
        )
    return lines + [""]


def operation_section(path: str, method: str, op: dict) -> list[str]:
    lines = [f"### {method.upper()} {path}", ""]
    summary = summary_of(op)
    if summary:
        lines += [summary, ""]
    public = " · public, no bearer token" if op.get("security") == [{}] else ""
    lines += [f"Operation `{op['operationId']}`{public}.", ""]
    if op.get("parameters"):
        lines += [
            row("Parameter", "In", "Type", "Required", "Description"),
            row(*["---"] * 5),
        ]
        lines += [
            row(
                f"`{p['name']}`",
                p["in"],
                body(p["content"], show_media=True)
                if "content" in p
                else type_of(p.get("schema", {})),
                "yes" if p.get("required") else "",
                field_description(
                    {**p.get("schema", {}), "description": p.get("description")}
                ),
            )
            for p in op["parameters"]
        ]
        lines.append("")
    if "requestBody" in op:
        request = op["requestBody"]
        optional = "" if request.get("required") else " (optional)"
        lines += [f"Request{optional}: {body(request['content'])}.", ""]
    # Group statuses sharing one body and meaning so the common error envelope reads once.
    grouped: dict[str, list[str]] = {}
    for status, response in sorted(op["responses"].items()):
        meaning = prose(response.get("description"))
        text = body(response.get("content", {})) + (f" — {meaning}" if meaning else "")
        grouped.setdefault(text, []).append(status)
    lines += [f"- {', '.join(statuses)}: {text}" for text, statuses in grouped.items()]
    for status, response in sorted(op["responses"].items()):
        for name, header in response.get("headers", {}).items():
            lines += [
                "",
                f"Response {status} header `{name}`: {type_of(header.get('schema', {}))}. {prose(header.get('description'))}",
            ]
        for media, value in response.get("content", {}).items():
            for name, example in value.get("examples", {}).items():
                if "value" in example:
                    lines += [
                        "",
                        f"Response {status} example `{name}` (`{media}`):",
                        "",
                        fenced("json", json.dumps(example["value"], indent=2)).rstrip(),
                    ]
    return lines + [""]


def openapi(path: str, *selected_groups: str) -> str:
    spec = json.loads((ROOT / path).read_text())
    paths = spec["paths"]
    shared = takewhile(lambda s: len(set(s)) == 1, zip(*(p.split("/") for p in paths)))
    prefix = "/".join(s[0] for s in shared)
    groups: dict[str, list[tuple[str, str, dict]]] = {}
    for route, item in sorted(paths.items()):
        relative = route[len(prefix) :]
        if selected_groups and relative.split("/")[1] not in selected_groups:
            continue
        for method in sorted((m for m in item if m in METHODS), key=METHODS.index):
            groups.setdefault(relative.split("/")[1], []).append(
                (relative, method, item[method])
            )
    contents = [f"[`/{g}`](#{anchor(f'/{g} routes')})" for g in sorted(groups)]
    lines = [f"Paths are relative to `{prefix}`.", ""]
    lines += [f"Operations: {' · '.join(contents)}. [Schemas](#schemas).", ""]
    for group, operations in sorted(groups.items()):
        lines += [f"## /{group} routes", ""] + overview(operations)
        for relative, method, op in operations:
            lines += operation_section(relative, method, op)
    lines += ["## Schemas", ""]
    for name, schema in sorted(spec["components"]["schemas"].items()):
        lines += schema_section(name, schema)
    return "\n".join(lines)


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
                    cited.setdefault(invariant, []).append(
                        f"{file.relative_to(ROOT)}::{name}"
                    )
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
    if kind == "openapi":
        return openapi(*args)
    if kind == "invariants":
        return invariants()
    raise ValueError(f"unknown directive: {directive}")


def regenerate(text: str) -> str:
    return BLOCK.sub(
        lambda m: m.group(1) + render(m.group("directive")) + m.group(4), text
    )


def generate(paths: list[str]) -> None:
    for chapter in [ROOT / path for path in paths] if paths else chapters():
        text = chapter.read_text()
        updated = regenerate(text)
        if updated != text:
            chapter.write_text(updated)
            print(f"updated {chapter.relative_to(ROOT)}")


def check(paths: list[str]) -> int:
    problems = []
    for chapter in [ROOT / path for path in paths] if paths else chapters():
        text = chapter.read_text()
        if regenerate(text) != text:
            problems.append(
                f"{chapter.relative_to(ROOT)}: generated blocks are stale (make generate)"
            )
    defined, cited = ([], {}) if paths else (defined_invariants(), proofs())
    problems += [
        f"invariant {i} is defined twice" for i in set(defined) if defined.count(i) > 1
    ]
    problems += [
        f"invariant {i} has no test citing it" for i in defined if i not in cited
    ]
    problems += [
        f"{t} cites unknown invariant {i}"
        for i, ts in cited.items()
        if i not in defined
        for t in ts
    ]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def tidy_er(path: str) -> None:
    """Shorten tbls relationship labels to the referencing columns."""
    file = ROOT / path
    text = re.sub(
        r'"FOREIGN KEY \(([^)]*)\) REFERENCES [^"]*"', r'"\1"', file.read_text()
    )
    file.write_text(text.replace('"public.', '"').replace("uuid__", "uuid_array"))


if __name__ == "__main__":
    command, *rest = sys.argv[1:] or ["check"]
    if command == "generate":
        generate(rest)
    elif command == "check":
        sys.exit(check(rest))
    elif command == "tidy-er":
        tidy_er(rest[0])
    else:
        sys.exit(f"unknown command {command}")
