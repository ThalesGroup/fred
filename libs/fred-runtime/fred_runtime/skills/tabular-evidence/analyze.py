# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def analyze(path: Path) -> dict:
    if not path.is_file() or not path.resolve().is_relative_to(
        Path("/inputs").resolve()
    ):
        raise ValueError("Expected a mounted file under /inputs")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("File exceeds the mounted input limit")
    totals = defaultdict(float)
    top = None
    row_count = 0
    with path.open(newline="", encoding="utf-8-sig") as source:
        for row_number, row in enumerate(csv.DictReader(source), start=2):
            row_count += 1
            category = row["category"].strip()
            amount = float(row["amount"])
            totals[category] += amount
            if top is None or amount > top["amount"]:
                top = {"row": row_number, "category": category, "amount": amount}
    return {
        "rows": row_count,
        "totals": dict(sorted(totals.items())),
        "highest": top,
    }


if __name__ == "__main__":
    print(json.dumps(analyze(Path(sys.argv[1])), sort_keys=True))
