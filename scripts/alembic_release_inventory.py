"""Build the Alembic head inventory attached to Fred releases."""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


REVISION_ID = re.compile(r"[A-Za-z0-9_]+\Z")


@dataclass(frozen=True)
class Revision:
    identifier: str
    parents: tuple[str, ...]
    path: Path


@dataclass(frozen=True)
class MigrationTree:
    owner: str
    path: Path
    head: str
    revisions: tuple[Revision, ...]


def _literal_assignment(module: ast.Module, name: str, path: Path) -> object:
    values = []
    for statement in module.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            target = statement.target.id
        elif (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            target = statement.targets[0].id
        else:
            continue
        if target == name:
            try:
                values.append(ast.literal_eval(statement.value))
            except (ValueError, TypeError, SyntaxError) as exc:
                raise ValueError(f"{path}: {name} must be a literal") from exc
    if len(values) != 1:
        raise ValueError(f"{path}: expected exactly one {name} assignment")
    return values[0]


def _revision(path: Path, root: Path) -> Revision:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    identifier = _literal_assignment(module, "revision", path)
    if not isinstance(identifier, str) or not REVISION_ID.fullmatch(identifier):
        raise ValueError(f"{path}: invalid revision identifier {identifier!r}")
    raw_parents = _literal_assignment(module, "down_revision", path)
    if raw_parents is None:
        parents: tuple[str, ...] = ()
    elif isinstance(raw_parents, str):
        parents = (raw_parents,)
    elif isinstance(raw_parents, (tuple, list)):
        parents = tuple(raw_parents)
    else:
        raise ValueError(f"{path}: invalid down_revision {raw_parents!r}")
    if not all(isinstance(parent, str) and REVISION_ID.fullmatch(parent) for parent in parents):
        raise ValueError(f"{path}: invalid down_revision {raw_parents!r}")
    if len(set(parents)) != len(parents):
        raise ValueError(f"{path}: duplicate parent revision")
    return Revision(identifier, parents, path.relative_to(root))


def _owner(path: Path) -> str:
    parts = path.parts
    if parts[0] == "apps":
        return parts[1]
    if parts[:2] == ("libs", "capabilities"):
        return parts[2]
    return parts[1]


def _migration_tree(tree_dir: Path, root: Path) -> MigrationTree:
    version_dir = tree_dir / "versions"
    if not version_dir.is_dir():
        raise ValueError(f"{tree_dir}: missing versions directory")
    paths = sorted(path for path in version_dir.glob("*.py") if path.name != "__init__.py")
    if not paths:
        raise ValueError(f"{version_dir}: no revision files")
    revisions = [_revision(path, root) for path in paths]
    by_id: dict[str, Revision] = {}
    for revision in revisions:
        if revision.identifier in by_id:
            raise ValueError(f"{tree_dir}: duplicate revision {revision.identifier}")
        by_id[revision.identifier] = revision
    children: dict[str, list[str]] = {identifier: [] for identifier in by_id}
    remaining = {identifier: len(revision.parents) for identifier, revision in by_id.items()}
    for revision in revisions:
        for parent in revision.parents:
            if parent not in by_id:
                raise ValueError(f"{revision.path}: missing parent revision {parent}")
            children[parent].append(revision.identifier)
    heads = sorted(identifier for identifier, descendants in children.items() if not descendants)
    if len(heads) != 1:
        raise ValueError(f"{tree_dir}: expected one head, found {heads}")
    ready = [identifier for identifier, count in remaining.items() if count == 0]
    visited = 0
    while ready:
        identifier = ready.pop()
        visited += 1
        for child in children[identifier]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    if visited != len(revisions):
        raise ValueError(f"{tree_dir}: cycle in revision graph")
    relative_path = tree_dir.relative_to(root)
    return MigrationTree(_owner(relative_path), relative_path, heads[0], tuple(revisions))


def discover_trees(root: Path) -> tuple[MigrationTree, ...]:
    trees = []
    projects = []
    for base in (root / "apps", root / "libs"):
        if not base.is_dir():
            continue
        for directory, dirs, files in os.walk(base):
            dirs[:] = sorted(
                name
                for name in dirs
                if name not in {".venv", "node_modules", "target", "__pycache__", "build", "dist"}
                and not name.startswith(".")
            )
            if "pyproject.toml" in files:
                projects.append(Path(directory) / "pyproject.toml")
            if "env.py" not in files:
                continue
            tree_dir = Path(directory)
            if not (tree_dir / "versions").is_dir() and (
                "migration" not in tree_dir.name and tree_dir.name != "alembic"
            ):
                continue
            trees.append(_migration_tree(tree_dir, root))
    if not trees:
        raise ValueError(f"{root}: no Alembic migration trees found")
    discovered = {tree.path for tree in trees}
    for project in sorted(projects):
        config = tomllib.loads(project.read_text(encoding="utf-8")).get("tool", {}).get("alembic")
        if config is None:
            continue
        if config.get("version_locations") or config.get("recursive_version_locations"):
            raise ValueError(f"{project}: unsupported Alembic version locations")
        location = config.get("script_location")
        if not isinstance(location, str):
            raise ValueError(f"{project}: missing Alembic script_location")
        path = Path(location.replace("%(here)s", str(project.parent), 1))
        if not path.is_absolute():
            path = project.parent / path
        try:
            relative_path = path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"{project}: Alembic tree is outside the repository") from exc
        if relative_path not in discovered:
            raise ValueError(
                f"{project}: configured Alembic tree {relative_path} was not discovered"
            )
    return tuple(sorted(trees, key=lambda tree: (tree.owner, str(tree.path))))


def render_inventory(root: Path, version: str, commit: str) -> str:
    if not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        raise ValueError(f"invalid release version {version!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"invalid source commit {commit!r}")
    trees = discover_trees(root)
    lines = [
        f"# Alembic heads - Fred v{version}",
        "",
        f"Source commit: `{commit}`",
        "",
        "Each row shows the head of an Alembic migration tree at the source commit above. "
        "It does not show which migrations have run in a deployment.",
        "",
        "| Component | Migration tree | Head |",
        "| --- | --- | --- |",
    ]
    for tree in trees:
        lines.append(
            f"| {tree.owner} | `{tree.path.as_posix()}` | `{tree.head}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="Fred release version without the v prefix"
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    content = render_inventory(root, arguments.version, commit)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
