#!/usr/bin/env python3
"""Validate PR migration notes and prepare reproducible operator release guides."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

import yaml

POLICY = ".github/migration-policy.json"
SECTIONS = (
    "Applicability",
    "Prerequisites",
    "Configuration",
    "Upgrade",
    "Validation",
    "Rollback",
    "Limitations",
)
IMPACTS = {"none": 0, "minor": 1, "major": 2}
VERSION = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|<fill[^>]*>|\[describe[^\]]*\]", re.I)


class Invalid(ValueError):
    """Actionable policy failure."""


class UniqueLoader(yaml.SafeLoader):
    """YAML mapping loader that rejects duplicate keys instead of losing data."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise Invalid(f"Duplicate or non-string metadata key: {key!r}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def require(condition, message):
    if not condition:
        raise Invalid(message)


def schema_property_paths(
    schema: object, path: tuple[str, ...] = ()
) -> set[tuple[str, ...]]:
    """Collect declared options in the generated, inline chart schema.

    Ignore annotations and combine alternatives so reordering them is not
    mistaken for removing an option.
    """
    if not isinstance(schema, dict):
        return set()
    paths = set()
    for keyword in ("properties", "patternProperties"):
        for name, child in schema.get(keyword, {}).items():
            child_path = (*path, keyword, name)
            paths.add(child_path)
            paths.update(schema_property_paths(child, child_path))
    for keyword in ("anyOf", "allOf", "oneOf"):
        for child in schema.get(keyword, []):
            paths.update(schema_property_paths(child, path))
    for keyword in ("items", "additionalProperties"):
        paths.update(schema_property_paths(schema.get(keyword), (*path, keyword)))
    return paths


_VALIDATION_KEYS = {
    "type",
    "properties",
    "patternProperties",
    "additionalProperties",
    "required",
    "items",
    "anyOf",
    "allOf",
    "oneOf",
    "not",
    "enum",
    "const",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "format",
    "if",
    "then",
    "else",
}


def schema_validation_shape(node: object) -> object:
    """Keep validation rules while ignoring descriptions and ordering."""
    if not isinstance(node, dict):
        return node
    result = {}
    for key, value in node.items():
        if key not in _VALIDATION_KEYS:
            continue
        if key in {"properties", "patternProperties"}:
            result[key] = {
                name: schema_validation_shape(child) for name, child in value.items()
            }
        elif key in {"anyOf", "allOf", "oneOf"}:
            result[key] = sorted(
                (schema_validation_shape(child) for child in value),
                key=lambda child: json.dumps(child, sort_keys=True),
            )
        elif key in {"required", "enum"}:
            result[key] = sorted(value, key=str)
        elif key == "items" and isinstance(value, list):
            result[key] = [schema_validation_shape(child) for child in value]
        elif isinstance(value, dict):
            result[key] = schema_validation_shape(value)
        else:
            result[key] = value
    return result


def version(value):
    match = VERSION.fullmatch(value)
    require(match is not None, f"Invalid version {value!r}; use X.Y.Z or X.Y.Z-rc.1")
    suffix = match[4]
    require(
        not suffix
        or all(
            not p.isdigit() or p == "0" or not p.startswith("0")
            for p in suffix.split(".")
        ),
        "Numeric prerelease identifiers cannot have leading zeros",
    )
    return tuple(int(match[i]) for i in (1, 2, 3))


def precedence(value):
    core = version(value)
    suffix = VERSION.fullmatch(value)[4]
    identifiers = (
        tuple((0, int(p)) if p.isdigit() else (1, p) for p in suffix.split("."))
        if suffix
        else ()
    )
    return core, 1 if suffix is None else 0, identifiers


def minimum(previous, impact):
    major, minor, patch = version(previous)
    if "-" in previous:
        return f"{major}.{minor}.{patch}"
    if impact == "major":
        return f"{major + 1}.0.0"
    if impact == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


@dataclass
class Note:
    path: str
    meta: dict
    body: str

    @property
    def impact(self):
        return self.meta["impact"]


def substantive(value):
    return (
        isinstance(value, str)
        and len(value.strip()) >= 15
        and not PLACEHOLDER.search(value)
    )


def parse_note(path, text):
    require(text.startswith("---\n"), f"{path}: missing YAML front matter")
    parts = text.split("\n---\n", 1)
    require(len(parts) == 2, f"{path}: unclosed front matter")
    meta = yaml.load(parts[0][4:], Loader=UniqueLoader)
    body = parts[1].strip()
    require(isinstance(meta, dict), f"{path}: metadata must be a mapping")
    allowed = {
        "schema",
        "title",
        "impact",
        "configuration",
        "configuration_reason",
        "no_action_reason",
        "after",
        "covers",
    }
    require(
        not (meta.keys() - allowed),
        f"{path}: unknown metadata keys {meta.keys() - allowed}",
    )
    require(
        type(meta.get("schema")) is int and meta["schema"] == 1,
        f"{path}: schema must be 1",
    )
    require(
        isinstance(meta.get("title"), str)
        and len(meta["title"].strip()) >= 5
        and "\n" not in meta["title"],
        f"{path}: title must be a single descriptive line",
    )
    require(
        isinstance(meta.get("impact"), str) and meta["impact"] in IMPACTS,
        f"{path}: impact must be none, minor or major",
    )
    require(
        meta.get("configuration") in ("none", "local", "production"),
        f"{path}: declare configuration: none, local or production",
    )
    require(
        substantive(meta.get("configuration_reason")),
        f"{path}: explain configuration ownership/compatibility",
    )
    if meta["impact"] == "none":
        require(
            substantive(meta.get("no_action_reason")),
            f"{path}: none requires no_action_reason",
        )
    require(not PLACEHOLDER.search(text), f"{path}: replace template placeholders")
    # Ignore examples when finding structural sections.
    prose = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", body, flags=re.M | re.S)
    headings = list(re.finditer(r"^## ([^\n]+)\n", prose, re.M))
    for section in SECTIONS:
        entries = [(i, h) for i, h in enumerate(headings) if h[1] == section]
        require(
            len(entries) == 1, f"{path}: exactly one '## {section}' section required"
        )
        i, h = entries[0]
        end = headings[i + 1].start() if i + 1 < len(headings) else len(prose)
        require(
            substantive(prose[h.end() : end]),
            f"{path}: {section} needs substantive instructions or a reason it does not apply",
        )
    for key in ("after", "covers"):
        require(
            isinstance(meta.get(key, []), list)
            and all(isinstance(v, str) for v in meta.get(key, [])),
            f"{path}: {key} must be a list of strings",
        )
    require(
        all(re.fullmatch(r"[0-9a-f]{40}", v) for v in meta.get("covers", [])),
        f"{path}: covers requires full commit SHA values",
    )
    return Note(path, meta, body)


class Repo:
    def __init__(self, root=".", head="HEAD", worktree=False):
        self.root = Path(root).resolve()
        self.head = self.resolve(head)
        self.worktree = worktree
        if worktree:
            require(
                self.head == self.resolve("HEAD"),
                "--worktree requires the checked-out HEAD",
            )
        self.policy = json.loads(self.read(POLICY))
        require(self.policy.get("schema") == 1, "Unsupported migration policy schema")
        self.notes_dir = self.policy["notes_dir"]
        self.releases_dir = self.policy["releases_dir"]
        for path in (self.notes_dir, self.releases_dir):
            require(
                re.fullmatch(r"deploy/release-notes/(?:changes|releases)", path),
                f"Unsafe policy path: {path}",
            )
        require(
            re.fullmatch(r"[0-9a-f]{40}", self.policy["activation_base"]),
            "activation_base must be a full commit SHA",
        )
        require(
            re.fullmatch(
                r"https://github.com/[\w.-]+/[\w.-]+", self.policy["repository"]
            ),
            "Invalid repository URL",
        )

    def git(self, *args, check=True, raw=False):
        result = subprocess.run(
            ["git", *args], cwd=self.root, text=True, capture_output=True
        )
        if check and result.returncode:
            raise Invalid(f"git {' '.join(args[:2])}: {result.stderr.strip()}")
        return (
            (result.stdout if raw else result.stdout.rstrip("\n"))
            if check
            else result.returncode
        )

    def resolve(self, ref):
        require(not ref.startswith("-"), "Refs cannot start with '-'")
        return self.git(
            "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"
        )

    def ancestor(self, base, head=None):
        return (
            self.git(
                "merge-base",
                "--is-ancestor",
                self.resolve(base),
                head or self.head,
                check=False,
            )
            == 0
        )

    def read(self, path, ref=None):
        if ref is None and self.worktree:
            p = self.root / path
            require(
                p.is_file() and not p.is_symlink(), f"Missing or symlink file: {path}"
            )
            return p.read_text()
        return self.git("show", f"{ref or self.head}:{path}", raw=True)

    def paths(self, ref=None):
        if ref is None and self.worktree:
            paths = self.git(
                "ls-files", "-z", "--cached", "--others", "--exclude-standard"
            ).split("\0")
            return {p for p in paths if p and (self.root / p).is_file()}
        return set(
            filter(
                None,
                self.git("ls-tree", "-rz", "--name-only", ref or self.head).split("\0"),
            )
        )

    def note_paths(self, ref=None):
        return {
            p
            for p in self.paths(ref)
            if p.startswith(self.notes_dir + "/") and p.endswith(".md")
        }

    def changes(self, base, head=None):
        args = ["diff", "--name-only", "--no-renames", "-z", self.resolve(base)]
        if head or not self.worktree:
            args.append(head or self.head)
        args.append("--")
        paths = set(filter(None, self.git(*args).split("\0")))
        if head is None and self.worktree:
            paths |= set(
                filter(
                    None,
                    self.git("ls-files", "--others", "--exclude-standard", "-z").split(
                        "\0"
                    ),
                )
            )
        return paths

    def release_tags(self) -> dict[str, str]:
        """Only this release line's first-parent tags, including prereleases."""
        history = self.git("rev-list", "--first-parent", self.head).splitlines()
        boundary = self.policy["activation_base"]
        require(
            boundary in history,
            "Policy activation boundary must be on first-parent history; fetch full history",
        )
        commits = set(history[: history.index(boundary) + 1])
        tags = {}
        for tag in self.git(
            "tag", "--merged", self.head, "--list", "code/v*"
        ).splitlines():
            if VERSION.fullmatch(tag[6:]):
                commit = self.resolve(tag)
                if commit in commits:
                    tags[tag] = commit
        return tags

    def baseline(self, explicit=None, target=None):
        boundary = self.policy["activation_base"]
        releases = {
            tag: commit
            for tag, commit in self.release_tags().items()
            if tag[6:] != target
        }
        if explicit:
            if explicit == boundary:
                require(
                    not releases,
                    "Initial release baseline cannot replace an existing release",
                )
                return boundary
            require(
                explicit in releases,
                "Baseline must be an existing code/v tag on this release line's first-parent ancestry",
            )
            version(explicit[6:])
            return explicit
        tags = {}
        for tag, commit in releases.items():
            tags.setdefault(commit, []).append(tag)
        for commit in self.git("rev-list", "--first-parent", self.head).splitlines():
            if commit in tags:
                require(
                    len(tags[commit]) == 1,
                    "Multiple release tags on baseline commit; supply --base",
                )
                return tags[commit][0]
        return boundary

    def notes(self, baseline=None):
        old = self.note_paths(baseline) if baseline else set()
        current = self.note_paths()
        if baseline:
            for path in old:
                require(
                    path in current and self.read(path, baseline) == self.read(path),
                    f"Published note is immutable: {path}; add a correction note",
                )
        return [parse_note(p, self.read(p)) for p in sorted(current - old)]

    def check_pr(self, base):
        base = self.git("merge-base", self.resolve(base), self.head)
        require(
            not (self.note_paths(base) - self.note_paths()),
            "Retain existing migration notes; add a correction instead of deleting or renaming them",
        )
        added = self.note_paths() - self.note_paths(base)
        require(
            added, "Every PR must add a migration note, including docs-only changes"
        )
        notes = [parse_note(p, self.read(p)) for p in sorted(added)]
        # Validate edits too, without allowing an old note to satisfy the PR.
        for path in self.changes(base) & self.note_paths():
            parse_note(path, self.read(path))
        baseline = self.baseline()
        self.notes(baseline)
        changed = self.changes(base)
        rank = max(IMPACTS[n.impact] for n in notes)
        new_paths = self.paths() - self.paths(base)
        if any(
            re.search(r"/(?:alembic|migrations)/versions/[^/]+\.py$", p)
            and not p.endswith("/__init__.py")
            for p in new_paths
        ):
            require(rank >= 1, "New Alembic revision requires minor or major impact")
        config_paths = {
            p
            for p in changed
            if ("/config/" in p and p.endswith((".yaml", ".json")))
            or p.endswith("/values.yaml")
            or p.endswith("/values.schema.json")
            or p.endswith("/security/structure.py")
            or p.endswith("/app/config.py")
        }
        if config_paths or any(n.meta["configuration"] == "production" for n in notes):
            production = [n for n in notes if n.meta["configuration"] == "production"]
            local = [n for n in notes if n.meta["configuration"] == "local"]
            require(
                production or local,
                "Configuration changes require configuration: production or local with a specific explanation",
            )
            if production:
                chart_dirs = {
                    str(Path(path).parent)
                    for path in changed
                    if path.startswith("deploy/charts/")
                    and Path(path).name in {"values.yaml", "values.schema.json"}
                }
                substantive_chart = False
                comment_only_chart = False
                for directory in chart_dirs:
                    chart = f"{directory}/values.yaml"
                    schema = f"{directory}/values.schema.json"
                    removed_options = set()
                    validation_changed = False
                    if (
                        schema in changed
                        and schema in self.paths(base)
                        and schema in self.paths()
                    ):
                        old_schema = json.loads(self.read(schema, base))
                        new_schema = json.loads(self.read(schema))
                        removed_options = schema_property_paths(
                            old_schema
                        ) - schema_property_paths(new_schema)
                        validation_changed = schema_validation_shape(
                            old_schema
                        ) != schema_validation_shape(new_schema)
                    require(
                        not removed_options or chart in changed,
                        "Removing a chart option requires its values.yaml change in the same PR",
                    )
                    if chart in changed:
                        before = (
                            yaml.safe_load(self.read(chart, base))
                            if chart in self.paths(base)
                            else None
                        )
                        after = (
                            yaml.safe_load(self.read(chart))
                            if chart in self.paths()
                            else None
                        )
                        chart_substantive = (
                            before != after
                            or bool(removed_options)
                            or validation_changed
                        )
                        substantive_chart |= chart_substantive
                        comment_only_chart |= not chart_substantive
                    else:
                        substantive_chart |= validation_changed and not removed_options
                if comment_only_chart and not substantive_chart:
                    raise Invalid(
                        "Comment-only values.yaml edits require a generated chart schema validation change or removed option; declare local if appropriate"
                    )
                require(
                    substantive_chart,
                    "Production configuration changes require chart values.yaml or a chart schema validation change in the same PR",
                )
        return notes

    def coverage(self, base, notes):
        blockers = []
        covers = {sha for n in notes for sha in n.meta.get("covers", [])}
        for sha in covers:
            require(self.ancestor(sha), f"Covered commit is not an ancestor: {sha}")
        start = self.resolve(base)
        for commit in self.git(
            "rev-list", "--first-parent", "--reverse", f"{start}..{self.head}"
        ).splitlines():
            parent = self.resolve(f"{commit}^1")
            if not self.changes(parent, commit):
                continue
            added = (self.note_paths(commit) - self.note_paths(parent)) & {
                n.path for n in notes
            }
            if not added and commit not in covers:
                blockers.append(
                    f"Uncovered contribution {commit}: add a note with covers: [<full SHA>] after reviewing its impact"
                )
        if self.worktree and self.changes(self.head):
            require(
                self.note_paths() - self.note_paths(self.head),
                "Release preparation changes require a new migration note too",
            )
        return blockers


def ordered(notes, published=()):
    by_name = {Path(n.path).stem: n for n in notes}
    require(len(by_name) == len(notes), "Duplicate note identities")
    done = {Path(p).stem for p in published}
    result = []
    while by_name:
        ready = sorted(
            k for k, n in by_name.items() if set(n.meta.get("after", [])) <= done
        )
        require(ready, "Migration ordering has a cycle or unknown 'after' dependency")
        for k in ready:
            result.append(by_name.pop(k))
            done.add(k)
    return result


def exported_body(note, repository, target):
    def absolute(link):
        parts = urlsplit(link)
        if parts.scheme or link.startswith("//"):
            require(
                parts.scheme in ("http", "https", "mailto") or link.startswith("//"),
                f"Unsafe link in {note.path}",
            )
            return link
        path = (
            posixpath.normpath(posixpath.join(posixpath.dirname(note.path), parts.path))
            if parts.path
            else note.path
        )
        require(not path.startswith(("../", "/")), f"Link escapes repository: {link}")
        suffix = ("?" + parts.query if parts.query else "") + (
            "#" + parts.fragment if parts.fragment else ""
        )
        return f"{repository}/blob/code/v{target}/{quote(path, safe='/')}" + suffix

    # Convert inline and reference-style Markdown links to immutable release URLs.
    body = re.sub(
        r"(!?\[[^\]\n]*\]\()([^\s)]+)(\))",
        lambda m: m[1] + absolute(m[2]) + m[3],
        note.body,
    )
    body = re.sub(
        r"^(\[[^\]\n]+\]:\s*)(\S+)", lambda m: m[1] + absolute(m[2]), body, flags=re.M
    )
    return body


def release_plan(repo, base=None, target=None):
    if target:
        version(target)
    base = repo.baseline(base, target)
    notes = ordered(repo.notes(base), repo.note_paths(base))
    require(
        notes,
        "No migration notes in release range; audit missing declarations before releasing",
    )
    impact = max((n.impact for n in notes), key=IMPACTS.get)
    if base == repo.policy["activation_base"]:
        require(target, "The initial release requires an explicit --version")
        recommended = ".".join(map(str, version(target)))
    else:
        recommended = minimum(base[6:], impact)
    target = target or recommended
    require(
        version(target) >= version(recommended),
        f"v{target} is insufficient for {impact}; minimum v{recommended}",
    )
    for tag, commit in repo.release_tags().items():
        previous = tag[6:]
        if previous == target and commit == repo.head:
            continue  # verifying this publication, not issuing it twice
        require(
            precedence(target) > precedence(previous),
            f"Target v{target} must advance beyond existing {tag}",
        )
    return {
        "base": base,
        "version": target,
        "impact": impact,
        "minimum": recommended,
        "notes": [n.path for n in notes],
        "blockers": repo.coverage(base, notes),
    }, notes


def render(repo, plan, notes):
    lines = [
        f"# Release report - v{plan['version']}",
        "",
        f"Report baseline: `{plan['base']}`",
        f"Operational impact: **{plan['impact']}** (minimum version: `{plan['minimum']}`).",
        "",
        "Fresh installation required. Upgrades from Swift or an earlier Weaver are not supported. Customer-specific values remain in private deployment repositories; the matching Fred chart is the configuration reference.",
        "",
        "This initial report starts a new release history; it does not reconstruct the Swift-to-Weaver changes."
        if plan["base"] == repo.policy["activation_base"]
        else "This report lists changes since the previous release, including prereleases; it does not certify an upgrade path.",
        "",
    ]
    for note in notes:
        url = f"{repo.policy['repository']}/blob/code/v{plan['version']}/{quote(note.path, safe='/')}"
        lines.extend(
            [
                f"## {note.meta['title']}",
                "",
                f"Impact: **{note.impact}** - [Source]({url})",
                "",
            ]
        )
        if note.impact == "none":
            lines.extend(
                [
                    note.meta["no_action_reason"],
                    "",
                    "See the source note for applicability, validation and rollback.",
                    "",
                ]
            )
        else:
            body = exported_body(note, repo.policy["repository"], plan["version"])
            body = re.sub(r"^(#{1,5}) ", r"#\1 ", body, flags=re.M)
            lines.extend([body, ""])
    return "\n".join(lines)


def verify_pair(repo, target, attempts=1, delay=5):
    for attempt in range(attempts):
        found = {}
        for prefix in ("code", "chart"):
            ref = f"refs/tags/{prefix}/v{target}"
            if repo.git("rev-parse", "--verify", ref, check=False) == 0:
                found[prefix] = repo.resolve(ref)
        if len(found) == 2:
            require(
                all(sha == repo.head for sha in found.values()),
                "Code/chart tags must point to this same commit",
            )
            return
        if attempt + 1 < attempts:
            time.sleep(delay)
            for prefix in ("code", "chart"):
                ref = f"refs/tags/{prefix}/v{target}"
                repo.git("fetch", "--no-tags", "origin", f"{ref}:{ref}", check=False)
    raise Invalid("Both code/v and chart/v tags must exist before publication")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check-pr", "plan", "generate", "verify"))
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--worktree", action="store_true")
    parser.add_argument("--version")
    parser.add_argument("--require-tags", action="store_true")
    parser.add_argument("--tag-attempts", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        require(1 <= args.tag_attempts <= 12, "tag-attempts must be between 1 and 12")
        repo = Repo(head=args.head, worktree=args.worktree)
        if args.command == "check-pr":
            require(args.base, "check-pr requires --base")
            notes = repo.check_pr(args.base)
            print(f"Migration notes valid: {len(notes)} new declaration(s)")
            return 0
        if args.command in ("generate", "verify"):
            require(args.version, "generate/verify requires --version")
        base = args.base
        if args.command == "verify" and base is None:
            saved = repo.read(f"{repo.releases_dir}/v{args.version}/migration.md")
            match = re.search(
                r"^Report baseline: `(code/v[^`]+|[0-9a-f]{40})`$", saved, re.M
            )
            require(match is not None, "Guide is missing its release baseline")
            base = match[1]
        plan, notes = release_plan(repo, base, args.version)
        print(json.dumps(plan, indent=2))
        require(
            not plan["blockers"],
            "Release coverage is incomplete; resolve blockers above",
        )
        if args.command == "plan":
            return 0
        if args.require_tags:
            require(not args.worktree, "Publication verification cannot use --worktree")
            verify_pair(repo, plan["version"], args.tag_attempts)
        path = f"{repo.releases_dir}/v{plan['version']}/migration.md"
        expected = render(repo, plan, notes)
        if args.command == "generate":
            output = repo.root / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(expected)
            print(f"Generated {path}")
        else:
            require(repo.read(path) == expected, f"Stale guide: regenerate {path}")
            print(f"Verified {path}")
        return 0
    except (Invalid, OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"Migration policy: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
