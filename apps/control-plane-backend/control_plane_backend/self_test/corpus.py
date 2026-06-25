from __future__ import annotations

from pydantic import BaseModel

# The golden corpus is crafted so retrieval has ONE provable answer: a unique
# marker phrase lives in exactly one library. We assert on *which* document is
# retrieved, never on LLM prose — so the check is deterministic even against a
# real vector store. See ADMIN-SELF-TEST-HARNESS-RFC §4.

# A nonsense, collision-free marker so a keyword/semantic hit is unambiguous.
MARKER_PHRASE = "Marchtober"


class TestDocument(BaseModel):
    filename: str
    text: str


class TestLibrary(BaseModel):
    # Stable name lets seeding be idempotent (reconcile by name, never duplicate).
    name: str
    description: str
    document: TestDocument


# Library ALPHA holds the marker fact; BETA holds only unrelated content.
LIBRARY_ALPHA = TestLibrary(
    name="fred-selftest-alpha",
    description="Self-test golden corpus (alpha) — safe to delete.",
    document=TestDocument(
        filename="fred-selftest-alpha.md",
        text=(
            "# Fred self-test fixture document ALPHA\n\n"
            f"The Fredchurro festival takes place in {MARKER_PHRASE}.\n\n"
            "This sentence is the only place the marker fact appears."
        ),
    ),
)

LIBRARY_BETA = TestLibrary(
    name="fred-selftest-beta",
    description="Self-test golden corpus (beta) — safe to delete.",
    document=TestDocument(
        filename="fred-selftest-beta.md",
        text=(
            "# Fred self-test fixture document BETA\n\n"
            "This document is about unrelated topics: weather, gardening, and tea.\n\n"
            "It deliberately contains no festival information at all."
        ),
    ),
)

# The probe question used to validate scoping. Scoped to ALPHA it must surface
# the marker; scoped to BETA it must not.
PROBE_QUESTION = "When does the Fredchurro festival take place?"
