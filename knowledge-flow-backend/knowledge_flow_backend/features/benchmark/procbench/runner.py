# Copyright Thales 2025
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

import dataclasses
import datetime as dt
import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, List, Literal, Optional, Protocol

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownResult

from .models import ProcessorRunMetrics, ProcessorRunResult

logger = logging.getLogger(__name__)


class Adapter(Protocol):
    def run(self, processor_spec: "ProcessorSpec", file_path: Path, work_dir: Path) -> ProcessorRunResult: ...


@dataclasses.dataclass
class ProcessorSpec:
    id: str
    kind: Literal["standard", "lite"]
    display_name: str
    file_types: List[str]  # [".pdf"], [".docx"], etc.
    # Prefer a factory to build the processor instance
    factory: Optional[Callable[[], Any]] = None
    import_path: Optional[str] = None  # unused in in-app runner


def _analyze_markdown(md_text: str) -> ProcessorRunMetrics:
    lines = md_text.splitlines()
    chars = len(md_text)
    words = len(md_text.split())

    headings = sum(1 for ln in lines if ln.lstrip().startswith("#"))
    h1 = sum(1 for ln in lines if ln.startswith("# "))
    h2 = sum(1 for ln in lines if ln.startswith("## "))
    h3 = sum(1 for ln in lines if ln.startswith("### "))
    images = md_text.count("![")
    links = md_text.count("](")
    codeblocks = md_text.count("```") // 2
    table_rule = sum(1 for ln in lines if "|" in ln)
    tokens_est = int(chars / 4)

    return ProcessorRunMetrics(
        chars=chars,
        words=words,
        headings=headings,
        h1=h1,
        h2=h2,
        h3=h3,
        images=images,
        links=links,
        code_blocks=codeblocks,
        table_like_lines=table_rule,
        tokens_est=tokens_est,
    )


class StandardProcessorAdapter:
    """
    Adapter to run standard processors (stateful, filesystem-based).
    """

    def run(self, processor_spec: ProcessorSpec, file_path: Path) -> ProcessorRunResult:
        # Use a TemporaryDirectory for standard processors' outputs (no persistent files)
        temp_dir = tempfile.TemporaryDirectory()
        output_dir = Path(temp_dir.name) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        if processor_spec.factory is None:
            raise RuntimeError(f"ProcessorSpec '{processor_spec.id}' has no factory")
        inst = processor_spec.factory()
        if not isinstance(inst, BaseMarkdownProcessor):
            raise TypeError(f"Processor '{processor_spec.id}' is not a BaseMarkdownProcessor")

        uid = f"{file_path.stem}-{int(time.time())}"
        started = time.perf_counter()
        try:
            inst.convert_file_to_markdown(file_path, output_dir, uid)
            candidate = output_dir / "output.md"
            if candidate.exists():
                md_file = candidate
            else:
                raise FileNotFoundError("Markdown output file not found after processing")
            md_text = md_file.read_text(encoding="utf-8") if md_file and md_file.exists() else ""
            dur = int((time.perf_counter() - started) * 1000)
            stats = _analyze_markdown(md_text) if md_text else None
            return ProcessorRunResult(
                processor_id=processor_spec.id,
                display_name=processor_spec.display_name,
                kind=processor_spec.kind,
                status="ok",
                duration_ms=dur,
                markdown=md_text or None,
                metrics=stats,
            )
        except Exception as e:  # noqa: BLE001
            dur = int((time.perf_counter() - started) * 1000)
            return ProcessorRunResult(
                processor_id=processor_spec.id,
                display_name=processor_spec.display_name,
                kind=processor_spec.kind,
                status="error",
                duration_ms=dur,
                markdown=None,
                metrics=None,
                error_message=str(e),
            )
        finally:
            try:
                temp_dir.cleanup()
            except Exception:
                logger.warning(f"Failed to cleanup temp directory {temp_dir.name}")
                pass


class LiteAdapter:
    """
    Adapter to run lightweight processors (stateless, in-memory).
    """

    def run(self, processor_spec: ProcessorSpec, file_path: Path) -> ProcessorRunResult:
        if processor_spec.factory is None:
            raise RuntimeError(f"ProcessorSpec '{processor_spec.id}' has no factory")
        inst = processor_spec.factory()
        if not isinstance(inst, BaseLiteMdProcessor):
            raise TypeError(f"Processor '{processor_spec.id}' is not a BaseLiteMdProcessor")

        started = time.perf_counter()
        try:
            result: LiteMarkdownResult = inst.extract(file_path)
            md_text = result.markdown or ""
            page_count = result.page_count
            dur = int((time.perf_counter() - started) * 1000)
            stats = _analyze_markdown(md_text) if md_text else None
            logger.info(
                "Lite adapter result | processor=%s kind=%s len=%d pages=%s duration_ms=%d",
                processor_spec.id,
                processor_spec.kind,
                len(md_text),
                page_count,
                dur,
            )
            return ProcessorRunResult(
                processor_id=processor_spec.id,
                display_name=processor_spec.display_name,
                kind=processor_spec.kind,
                status="ok",
                duration_ms=dur,
                markdown=md_text or None,
                metrics=stats,
                page_count=page_count if isinstance(page_count, int) else None,
            )
        except Exception as e:  # noqa: BLE001
            dur = int((time.perf_counter() - started) * 1000)
            return ProcessorRunResult(
                processor_id=processor_spec.id,
                display_name=processor_spec.display_name,
                kind=processor_spec.kind,
                status="error",
                duration_ms=dur,
                markdown=None,
                metrics=None,
                error_message=str(e),
            )


def timestamp_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")
