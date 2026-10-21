#!/usr/bin/env python3
"""Package the five demo files atomically; never retain entries from an old ZIP."""
import os
from pathlib import Path
import tempfile
import zipfile

source = Path(os.environ["DEMO_PROVISIONING_FIXTURE_DIR"])
target = Path(os.environ["DEMO_BUNDLE_FILE"])
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
