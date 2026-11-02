"""Check an installed Knowledge API image's ingestion dependency boundary.

Run with that image's Python. Development mode skips host executable inventory.
This check imports the API and builds its schema without contacting services.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import shutil
import sys

FORBIDDEN_DISTRIBUTIONS = {
    "knowledge-flow-worker",
    "temporalio",
    "docling",
    "docling-slim",
    "docling-core",
    "docling-ibm-models",
    "docling-parse",
    "paddleocr",
    "paddlepaddle",
    "paddlepaddle-gpu",
    "paddlex",
    "faster-whisper",
    "av",
    "openvino",
    "markitdown",
    "pypandoc",
    "pypandoc-binary",
    "pymupdf",
    "pymupdf4llm",
    "pymupdf-layout",
    "pypdfium2",
    "python-docx",
    "python-pptx",
}
FORBIDDEN_BINARIES = ("soffice", "libreoffice", "ffmpeg", "pandoc", "inkscape")


def check(*, development: bool = False) -> dict:
    installed = {
        d.metadata["Name"].lower().replace("_", "-"): d.version
        for d in importlib.metadata.distributions()
    }
    unexpected = FORBIDDEN_DISTRIBUTIONS & installed.keys()
    if unexpected:
        raise RuntimeError(
            f"Ingestion distributions in API installation: {sorted(unexpected)}"
        )
    if not development:
        binaries = [name for name in FORBIDDEN_BINARIES if shutil.which(name)]
        if binaries:
            raise RuntimeError(f"Ingestion executables in API image: {binaries}")
    if importlib.util.find_spec("knowledge_flow_worker") is not None:
        raise RuntimeError("Worker source is importable from the API environment")
    from fred_core.documents import DocumentMetadata
    from knowledge_flow_backend.common.structures import Configuration
    from knowledge_flow_backend.main import create_app

    properties = Configuration.model_json_schema()["properties"]
    unexpected_config = {
        "processing",
        "scheduler",
        "manager_processing",
        "attachment_processors",
        "output_processors",
    } & properties.keys()
    if unexpected_config:
        raise RuntimeError(
            f"Worker configuration in API schema: {sorted(unexpected_config)}"
        )
    if any(
        name.startswith(("knowledge_flow_worker", "temporalio")) for name in sys.modules
    ):
        raise RuntimeError("API import loaded ingestion runtime")
    assert callable(create_app) and DocumentMetadata is not None
    return {"packages": installed, "configuration_properties": sorted(properties)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check(development=args.development), indent=2))
