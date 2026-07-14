# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Turn a pytest JUnit XML run into a short, claims-grouped Markdown report.

Minimal version (see RFC-C3-validation-extensions.md Extension F for the
fuller, tag-bound evidence report this could grow into - reports.md,
environment.json, sha256sums, signing). This script does exactly one thing:
make a run readable by someone who does not want to parse pytest output -
group results by the real-world claim being tested, not by test function name.

Usage:
    pytest --junitxml=report.xml [-x omitted, so the run doesn't stop early]
    python3 generate_report.py report.xml > report.md

Requires .claim_groups.json (written by conftest.py's
pytest_collection_modifyitems) to exist alongside this script - it maps each
test's display name to its source file, since the JUnit XML's own classname
is blanked out by the plain-English nodeid rewrite.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CLAIM_GROUPS_FILE = Path(__file__).parent / ".claim_groups.json"

# Maps a test file to the human claim area it proves. Anything not listed
# here falls back to its own filename - a new test file still gets a report
# section, just an unpolished one, instead of being silently dropped.
GROUP_LABELS = {
    "test_platform_role_isolation.py": "Platform-role isolation (AUTHZ-05)",
    "test_content_scope_bypass.py": "Content-scope team isolation",
    "test_runtime_team_isolation.py": "Team isolation (cross-team + runtime)",
}

# Group display order - anything unlisted is appended after these, alphabetically.
GROUP_ORDER = list(GROUP_LABELS.values())

# Substrings in a failure message that suggest an infrastructure hiccup rather
# than an authorization finding (a connection reset mid-test looks nothing
# like an AssertionError about a status code). Heuristic, not authoritative -
# always worth a human glance, but it keeps real findings from being buried.
INFRA_HINTS = (
    "connectionerror",
    "connection reset",
    "readerror",
    "readtimeout",
    "remotedisconnected",
    "connectionrefused",
)


def _status(testcase: ET.Element) -> tuple[str, str]:
    """Return (status, detail) for one <testcase>: passed/failed/xfailed/error."""
    failure = testcase.find("failure")
    if failure is not None:
        message = failure.get("message", "")
        if any(hint in message.lower() for hint in INFRA_HINTS):
            return "infra", message
        return "failed", message
    error = testcase.find("error")
    if error is not None:
        return "error", error.get("message", "")
    skipped = testcase.find("skipped")
    if skipped is not None:
        if skipped.get("type") == "pytest.xfail":
            return "xfail", skipped.get("message", "")
        return "skipped", skipped.get("message", "")
    return "passed", ""


ICONS = {
    "passed": "PASS",
    "failed": "FAIL",
    "error": "ERROR",
    "xfail": "GAP",
    "skipped": "SKIP",
    "infra": "INFRA",
}


def _junit_mangled(name: str) -> str:
    """Best-effort reproduction of pytest's junitxml name mangling.

    A docstring containing a literal "/" (a path separator, to pytest's
    nodeid logic) gets that "/" turned into "." in the JUnit XML - so a
    display name that matches exactly in .claim_groups.json can silently miss
    the JUnit `name` attribute. This lets the lookup below fall back to a
    normalized match instead of dropping the test into "Other" without
    explanation. Prefer fixing the offending docstring (avoid "/") over
    relying on this - it is a safety net, not a substitute.
    """
    return name.replace("/", ".")


def generate_report(junit_xml_path: Path) -> str:
    tree = ET.parse(junit_xml_path)
    testcases = tree.getroot().iter("testcase")

    claim_groups: dict[str, str] = {}
    if CLAIM_GROUPS_FILE.exists():
        claim_groups = json.loads(CLAIM_GROUPS_FILE.read_text())
    claim_groups_normalized = {_junit_mangled(k): v for k, v in claim_groups.items()}

    groups: dict[str, list[tuple[str, str, str]]] = {}
    for tc in testcases:
        name = tc.get("name", "")
        source_file = claim_groups.get(name) or claim_groups_normalized.get(name, "")
        label = GROUP_LABELS.get(source_file, source_file or "Other")
        status, detail = _status(tc)
        groups.setdefault(label, []).append((name, status, detail))

    counts = {"passed": 0, "failed": 0, "error": 0, "xfail": 0, "skipped": 0, "infra": 0}
    for entries in groups.values():
        for _, status, _ in entries:
            counts[status] += 1

    blocking_findings = counts["failed"] + counts["error"] + counts["infra"]
    if blocking_findings:
        verdict = f"NOT READY - {blocking_findings} blocking finding(s) need attention"
    elif counts["xfail"]:
        verdict = f"READY WITH ACCEPTED GAPS - {counts['xfail']} known xfail(s) remain"
    else:
        verdict = "READY - no unexplained findings"

    lines: list[str] = []
    lines.append("# Fred Authorization Validation Report")
    lines.append("")
    lines.append(f"**Result:** {verdict}")
    lines.append(
        f"**Totals:** {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['error']} error, {counts['xfail']} known gap (xfail), "
        f"{counts['infra']} possible infra issue, {counts['skipped']} skipped"
    )
    lines.append("")

    ordered_labels = [label for label in GROUP_ORDER if label in groups]
    ordered_labels += sorted(label for label in groups if label not in GROUP_ORDER)

    for label in ordered_labels:
        entries = sorted(groups[label], key=lambda e: (e[1] != "failed", e[1] != "error", e[0]))
        lines.append(f"## {label}")
        lines.append("")
        lines.append("| Result | Claim |")
        lines.append("|---|---|")
        for name, status, _ in entries:
            lines.append(f"| {ICONS[status]} | {name} |")
        lines.append("")

        details = [(n, s, d) for n, s, d in entries if s in ("failed", "error") and d]
        if details:
            lines.append("<details><summary>Details for failures in this section</summary>")
            lines.append("")
            for name, status, detail in details:
                first_line = detail.splitlines()[0] if detail else ""
                lines.append(f"- **{name}**: {first_line}")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    if counts["infra"]:
        lines.append("## Needs attention (not a security finding)")
        lines.append("")
        for entries in groups.values():
            for name, status, detail in entries:
                if status == "infra":
                    first_line = detail.splitlines()[0] if detail else ""
                    lines.append(f"- **{name}**: {first_line} - looks like an infra/connection issue, not an authorization result. Re-run to confirm before treating it as a finding.")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 generate_report.py <junit-xml-path>", file=sys.stderr)
        return 2
    junit_xml_path = Path(sys.argv[1])
    if not junit_xml_path.exists():
        print(f"JUnit XML file not found: {junit_xml_path}", file=sys.stderr)
        return 2
    print(generate_report(junit_xml_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
