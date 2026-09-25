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

"""Inventory tracked source headers; signals only, never licensing decisions.

Run from any checkout directory. JSON goes to stdout; errors fail the command.
Generated files are classified separately, not counted as compliant or missing.
Untracked files, symlinks and non-source formats are outside this first pass.
"""

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh", ".css", ".scss"}


def classify(path: str, content: str) -> str:
    lines = []
    for line in content.splitlines()[:40]:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*", "*/")):
            lines.append(line)
        else:
            break
    header = "\n".join(lines)
    if (
        path.endswith("OpenApi.ts")
        or ".generated." in path
        or re.search(
            r"(?i)auto[- ]generated|automatically generated|@generated", header
        )
    ):
        return "generated_review_separately"
    if "SPDX-License-Identifier:" in header:
        return (
            "spdx_review"  # SPDX metadata is not proof of the full-header convention.
        )
    if "Licensed under the Apache License, Version 2.0" in header:
        if "Copyright" in header and "limitations under the License." in header:
            return "apache_header_markers_present"
        return "apache_header_incomplete"
    if re.search(r"(?i)copyright|license|licence", header):
        return "other_notice_review"
    return "no_notice_detected"


def main() -> None:
    root = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
    )
    paths = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    records = []
    excluded = Counter()
    for name in sorted(filter(None, paths)):
        path = root / name
        if path.is_symlink():
            excluded["symlink"] += 1
            continue
        if path.suffix not in SUFFIXES:
            excluded["non_source_format"] += 1
            continue
        if not path.is_file():
            excluded["missing_from_worktree"] += 1
            continue
        records.append(
            {"path": name, "status": classify(name, path.read_text(encoding="utf-8"))}
        )
    print(
        json.dumps(
            {
                "commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, text=True
                ).strip(),
                "scope": "tracked working-tree source files; first 40 lines; marker detection, not legal compliance",
                "suffixes": sorted(SUFFIXES),
                "counts": dict(
                    sorted(Counter(record["status"] for record in records).items())
                ),
                "excluded": dict(sorted(excluded.items())),
                "files": records,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
