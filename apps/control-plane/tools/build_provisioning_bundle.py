#!/usr/bin/env python3
"""Package a provisioning fixture atomically; never retain old ZIP entries.

An optional `skill_packs.json` in the fixture selects skills from Agent Skills
pack directories (paths relative to the fixture) for declared spaces:
`[{"space": "<ref>", "pack": "<dir>", "skills": ["<name>", ...]}]`.
They are written to the bundle's `skills.json`; the Control Plane validates them.
"""
import argparse
import json
from pathlib import Path
import tempfile
import zipfile


def skills(source: Path) -> list[dict] | None:
    declarations = source / "skill_packs.json"
    if not declarations.exists():
        return None
    entries = []
    for item in json.loads(declarations.read_text(encoding="utf-8")):
        if set(item) != {"space", "pack", "skills"}:
            raise SystemExit(f"{declarations}: expected space, pack and skills")
        pack = source / item["pack"]
        for name in item["skills"]:
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
declared = skills(source)
target.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
    staging = Path(temporary.name)
try:
    with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest", "users", "organizations", "teams", "projects"):
            archive.write(source / f"{name}.json", f"{name}.json")
        if declared is not None:
            archive.writestr("skills.json", json.dumps(declared, ensure_ascii=False, indent=2))
    staging.replace(target)
finally:
    staging.unlink(missing_ok=True)
print(target.resolve())
