"""Pick the Docker images a pull request has to build.

Each changed path goes to the first `pr_selection` rule of .github/docker-images.json
it matches. A path no rule claims builds every image, except an image whose
`pr_inputs` it does not match. Releases and non-PR runs build everything.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path


def matches(path: str, pattern: str) -> bool:
    # "dir/**" covers a whole tree; any other pattern stays at its own depth,
    # so "*.md" means root files only, never apps/x/README.md.
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return path.count("/") == pattern.count("/") and fnmatch.fnmatchcase(path, pattern)


def validate(manifest: dict) -> None:
    names = {image["name"] for image in manifest["images"]}
    for rule in manifest["pr_selection"]["rules"]:
        unknown = set(rule["images"]) - names
        if unknown:
            raise ValueError(f"pr_selection rule {rule['paths']} names unknown images {sorted(unknown)}")


def select(manifest: dict, changed: list[str]) -> dict[str, list[str]]:
    """Map every image name to the changed paths that select it; empty means skipped."""
    selected: dict[str, list[str]] = {image["name"]: [] for image in manifest["images"]}
    inputs = {image["name"]: image.get("pr_inputs") for image in manifest["images"]}
    rules = manifest["pr_selection"]["rules"]
    for path in changed:
        rule = next((r for r in rules if any(matches(path, p) for p in r["paths"])), None)
        if rule is not None:
            targets = rule["images"]
        else:
            targets = [name for name, own in inputs.items() if own is None or any(matches(path, p) for p in own)]
        for name in targets:
            selected[name].append(path)
    return selected


def changed_paths(base: str, head: str, repo: str = ".") -> list[str]:
    # Three dots: the PR's own changes against its merge base, so the final head
    # is always checked against the target branch. --no-renames reports a rename
    # as a deletion plus an addition, so both sides are classified.
    out = subprocess.run(
        ["git", "-C", repo, "diff", "--name-only", "--no-renames", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def report(selected: dict[str, list[str]], full_reason: str | None) -> str:
    lines = ["## Docker image selection", ""]
    if full_reason:
        lines += [f"Building every image: {full_reason}.", ""]
    for name, paths in selected.items():
        if full_reason:
            lines.append(f"- **{name}**: selected")
        elif paths:
            shown = ", ".join(f"`{p}`" for p in paths[:5]) + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
            lines.append(f"- **{name}**: selected by {shown}")
        else:
            lines.append(f"- **{name}**: skipped, no changed path is one of its inputs")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=".github/docker-images.json")
    parser.add_argument("--publish", choices=["true", "false"], required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    validate(manifest)
    publish = args.publish == "true"
    candidates = [image for image in manifest["images"] if not publish or image["publish"]]

    full_reason = None
    if publish:
        full_reason = "release build"
    elif not (args.base and args.head):
        full_reason = "not a pull request (manual or base-branch run)"
    else:
        try:
            selected = select(manifest, changed_paths(args.base, args.head))
        except subprocess.CalledProcessError as error:
            full_reason = f"could not diff {args.base}...{args.head} ({error.stderr.strip()})"
    if full_reason:
        selected = {image["name"]: ["*"] for image in candidates}

    matrix = [
        {key: image[key] for key in ("name", "context", "dockerfile", "build_args")}
        for image in candidates
        if selected.get(image["name"])
    ]
    summary = report({image["name"]: selected[image["name"]] for image in candidates}, full_reason)
    print(summary)
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(summary)
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            handle.write(f"include={json.dumps(matrix, separators=(',', ':'))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
