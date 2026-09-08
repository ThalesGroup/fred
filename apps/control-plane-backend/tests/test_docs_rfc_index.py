import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_README = _REPO_ROOT / "docs/swift/README.md"


def test_every_rfc_linked_from_the_index_is_committed() -> None:
    """A renamed RFC that was never `git add`ed leaves the index pointing at nothing.

    Checks the tracked set, not just the disk, so an untracked replacement fails
    here instead of only in CI after the commit has already shipped broken.
    """
    linked = set(
        re.findall(r"\]\((rfc/[^)\s#]+\.md)\)", _README.read_text(encoding="utf-8"))
    )
    assert linked, "RFC index is empty — the link pattern no longer matches"

    for target in sorted(linked):
        path = _README.parent / target
        assert path.is_file(), f"docs/swift/README.md links a missing RFC: {target}"

    if (_REPO_ROOT / ".git").exists():
        tracked = set(
            subprocess.run(
                ["git", "-C", str(_REPO_ROOT), "ls-files", "docs/swift/rfc"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
        )
        for target in sorted(linked):
            assert f"docs/swift/{target}" in tracked, (
                f"docs/swift/README.md links an untracked RFC: {target}"
            )
