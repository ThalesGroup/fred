#!/usr/bin/env python3
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

"""Patch Docling's RapidOCR defaults to support OpenVINO artifact lookup.

Docling 2.78.0 accepts `RapidOcrOptions.backend="openvino"` but its
`RapidOcrModel._default_models` mapping only contains `onnxruntime` and
`torch`. When `artifacts_path` is configured, Docling indexes this mapping
with `"openvino"` and crashes with `KeyError`.

This build-time patch keeps the application code clean by extending the
installed Docling module inside the image. OpenVINO uses the same ONNX model
files as the onnxruntime backend, so mirroring those default paths is enough.
"""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path


PATCH_SENTINEL = "# FRED Docker patch: RapidOCR OpenVINO artifact defaults"
PATCH_SNIPPET = f"""

{PATCH_SENTINEL}
if "openvino" not in RapidOcrModel._default_models:
    RapidOcrModel._default_models["openvino"] = {{
        key: dict(value)
        for key, value in RapidOcrModel._default_models["onnxruntime"].items()
    }}
""".lstrip()


def main() -> None:
    spec = find_spec("docling.models.stages.ocr.rapid_ocr_model")
    if spec is None or spec.origin is None:
        raise RuntimeError("Could not locate docling.models.stages.ocr.rapid_ocr_model")

    module_path = Path(spec.origin)
    content = module_path.read_text(encoding="utf-8")
    if PATCH_SENTINEL in content:
        print(module_path)
        print("Docling RapidOCR OpenVINO patch already present.")
        return

    module_path.write_text(content.rstrip() + "\n\n" + PATCH_SNIPPET, encoding="utf-8")
    print(module_path)
    print("Patched Docling RapidOCR OpenVINO defaults.")


if __name__ == "__main__":
    main()
