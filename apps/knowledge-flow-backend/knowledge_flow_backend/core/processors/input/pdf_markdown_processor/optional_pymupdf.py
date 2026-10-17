"""Load the explicitly selected PDF extra without masking broken installations."""

from importlib import import_module
from types import ModuleType


def require_pymupdf(selection: str) -> tuple[ModuleType, ModuleType]:
    try:
        fitz = import_module("fitz")
        # PyMuPDF4LLM otherwise silently ignores ImportError from its layout extra.
        import_module("pymupdf.layout")
        return fitz, import_module("pymupdf4llm")
    except ModuleNotFoundError as exc:
        if exc.name not in {"fitz", "pymupdf", "pymupdf.layout", "pymupdf4llm"}:
            raise
        raise ImportError(
            f"{selection} requires the optional 'pymupdf' extra. "
            "Run `uv sync --extra pymupdf` in apps/knowledge-flow-backend, "
            "or build the Knowledge Flow image with `--build-arg INSTALL_PYMUPDF=true`."
        ) from exc
