#!/usr/bin/env python3
# ruff: noqa: E402
"""
Standalone processor benchmark — no running server required.

Usage:
    python tests/scripts/bench_processors.py tests/assets/sample.pdf
    python tests/scripts/bench_processors.py tests/assets/sample.docx --out ./target/bench/
    python tests/scripts/bench_processors.py sample.pdf --processors pdf_fast_lite,pdf_medium_docling

The script instantiates processors directly (same code path as /dev/bench/run) without needing
Temporal, MinIO, or Keycloak. Outputs a table to stdout; optionally writes markdown to --out dir.
"""

import logging
import warnings

logging.disable(logging.INFO)  # RapidOCR/docling install their own handlers — this is the only reliable way to silence them
warnings.filterwarnings("ignore")  # suppress pydub RuntimeWarning about ffmpeg

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from knowledge_flow_backend.features.benchmark.procbench.registry import default_registry
from knowledge_flow_backend.features.benchmark.procbench.runner import FastAdapter, StandardProcessorAdapter


def _fmt_num(n):
    return f"{n:,}" if n is not None else "-"


def main():
    parser = argparse.ArgumentParser(description="Run ingestion processors locally and compare markdown output")
    parser.add_argument("file", help="Path to input document (.pdf, .docx, .pptx, .txt, .md)")
    parser.add_argument("--processors", "-p", default=None, help="Comma-separated processor ids (default: all matching file type)")
    parser.add_argument("--out", "-o", default=None, help="Directory to write .md output files (default: none)")
    args = parser.parse_args()

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    ext = file_path.suffix.lower()
    reg = default_registry()

    if args.processors:
        ids = [p.strip() for p in args.processors.split(",")]
        missing = [i for i in ids if i not in reg]
        if missing:
            print(f"ERROR: unknown processor ids: {', '.join(missing)}", file=sys.stderr)
            print(f"Available: {', '.join(reg)}", file=sys.stderr)
            sys.exit(1)
        specs = [reg[i] for i in ids]
    else:
        specs = [s for s in reg.values() if ext in s.file_types]

    if not specs:
        supported = ", ".join(sorted({ft for s in reg.values() for ft in s.file_types}))
        print(f"ERROR: no processors for '{ext}'. Supported extensions: {supported}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out).expanduser().resolve() if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nBenchmarking: {file_path.name}  ({ext})")
    print(f"Processors  : {', '.join(s.id for s in specs)}\n")

    col_w = 36
    print(f"{'Processor':<{col_w}}  {'Status':>6}  {'ms':>6}  {'chars':>7}  {'words':>6}  {'heads':>5}  {'imgs':>4}  {'tables':>6}  {'est.tok':>7}")
    print("-" * (col_w + 60))

    results = []
    for spec in specs:
        adapter = StandardProcessorAdapter() if spec.kind == "standard" else FastAdapter()
        t0 = time.perf_counter()
        r = adapter.run(spec, file_path)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        m = r.metrics
        status_sym = "OK" if r.status == "ok" else "ERR"
        print(
            f"{spec.display_name:<{col_w}}  {status_sym:>6}  {elapsed_ms:>6}  "
            f"{_fmt_num(m.chars if m else None):>7}  "
            f"{_fmt_num(m.words if m else None):>6}  "
            f"{_fmt_num(m.headings if m else None):>5}  "
            f"{_fmt_num(m.images if m else None):>4}  "
            f"{_fmt_num(m.table_like_lines if m else None):>6}  "
            f"{_fmt_num(m.tokens_est if m else None):>7}"
        )
        if r.status == "error":
            print(f"  └─ {r.error_message}")

        if out_dir and r.markdown:
            out_file = out_dir / f"{file_path.stem}__{spec.id}.md"
            out_file.write_text(r.markdown, encoding="utf-8")
            print(f"  └─ written: {out_file}")

        results.append(r)

    print()
    return 0 if all(r.status == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
