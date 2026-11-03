#!/usr/bin/env python3
"""Package a provisioning fixture atomically; never retain old ZIP entries."""
import argparse
from pathlib import Path
import tempfile
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("target", type=Path)
args = parser.parse_args()
source, target = args.source, args.target
target.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
    staging = Path(temporary.name)
try:
    with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest", "users", "organizations", "teams", "projects"):
            archive.write(source / f"{name}.json", f"{name}.json")
    staging.replace(target)
finally:
    staging.unlink(missing_ok=True)
print(target.resolve())
