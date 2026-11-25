#!/usr/bin/env python3
"""Package a provisioning fixture atomically; never retain old ZIP entries.

An optional `skill_packs.json` in the fixture selects skills from Agent Skills
pack directories (paths relative to the fixture) for declared spaces:
`[{"space": "<ref>", "pack": "<dir>", "skills": ["<name>", ...]}]`.
`prompt_packs.json` uses the same selection with a `prompts` list; each named
JSON file contains a category name and a prompt creation request. Both are written
to their optional bundle files; the Control Plane validates them.
"""
import argparse
import json
from pathlib import Path
import tempfile
import zipfile


def resources(source: Path, kind: str) -> list[dict] | None:
    declarations = source / f"{kind[:-1]}_packs.json"
    if not declarations.exists():
        return None
    entries = []
    for item in json.loads(declarations.read_text(encoding="utf-8")):
        if set(item) != {"space", "pack", kind}:
            raise SystemExit(f"{declarations}: expected space, pack and {kind}")
        pack = source / item["pack"]
        for name in item[kind]:
            if kind == "prompts":
                entry = json.loads((pack / f"{name}.json").read_text(encoding="utf-8"))
                entry["space"] = item["space"]
                entries.append(entry)
                continue
            root = pack / name
            if not (root / "SKILL.md").is_file():
                raise SystemExit(f"{root}: SKILL.md not found")
            files = {
                path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }
            entries.append({"space": item["space"], "name": name, "files": files})
    return entries


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("target", type=Path)
args = parser.parse_args()
source, target = args.source, args.target
declared = {kind: resources(source, kind) for kind in ("skills", "prompts")}
target.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
    staging = Path(temporary.name)
try:
    with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest", "users", "organizations", "teams", "projects"):
            archive.write(source / f"{name}.json", f"{name}.json")
        for kind, entries in declared.items():
            if entries is not None:
                archive.writestr(f"{kind}.json", json.dumps(entries, ensure_ascii=False, indent=2))
    staging.replace(target)
finally:
    staging.unlink(missing_ok=True)
print(target.resolve())
