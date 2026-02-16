#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests


@dataclass(frozen=True)
class Fixture:
    kind: str  # "pdf" | "docx" | "pptx"
    name: str  # local filename
    url: str  # remote URL


FIXTURES: list[Fixture] = [
    # ----------------
    # PDFs (mix: samples + arXiv)
    # ----------------
    Fixture("pdf", "file-examples_100kB.pdf", "https://file-examples.com/wp-content/storage/2017/10/file-example_PDF_1MB.pdf"),
    Fixture("pdf", "file-examples_500kB.pdf", "https://file-examples.com/wp-content/storage/2017/10/file-example_PDF_500_kB.pdf"),
    Fixture("pdf", "file-examples_1MB.pdf", "https://file-examples.com/wp-content/storage/2017/10/file-example_PDF_1MB.pdf"),
    Fixture("pdf", "arxiv_attention_is_all_you_need.pdf", "https://arxiv.org/pdf/1706.03762.pdf"),
    Fixture("pdf", "arxiv_resnet.pdf", "https://arxiv.org/pdf/1512.03385.pdf"),
    # ----------------
    # DOCX (complex: standards/templates/tables)
    # ----------------
    Fixture("docx", "file-examples_10kB.docx", "https://file-examples.com/wp-content/storage/2017/02/file-sample_100kB.docx"),
    Fixture("docx", "file-examples_100kB.docx", "https://file-examples.com/wp-content/storage/2017/02/file-sample_100kB.docx"),
    Fixture("docx", "file-examples_500kB.docx", "https://file-examples.com/wp-content/storage/2017/02/file-sample_500kB.docx"),
    Fixture("docx", "owasp_asvs_4.0.3_en.docx", "https://raw.githubusercontent.com/OWASP/ASVS/v4.0.3/4.0/docs_en/OWASP%20Application%20Security%20Verification%20Standard%204.0.3-en.docx"),
    Fixture("docx", "fria_assessment_template.docx", "https://raw.githubusercontent.com/swzaken/freetemplates/main/AI%20Act/FRIA%20assessment%20template%20V2.0.docx"),
    Fixture("docx", "rerun_example_tables_lists.docx", "https://raw.githubusercontent.com/rerun-io/rerun-loader-python-example-docx/main/example.docx"),
    Fixture("docx", "omegat_demo.docx", "https://raw.githubusercontent.com/miurahr/omegat-for-cat-beginners/master/docs/files/demo.docx"),
    # ----------------
    # PPTX (real decks: charts/animations/large-ish)
    # ----------------
    Fixture("pptx", "microsoft_cntk_deep_learning.pptx", "https://raw.githubusercontent.com/wiki/Microsoft/CNTK/ppt/S6843-Deep-Learning-in-Microsoft-with-CNTK.pptx"),
    Fixture("pptx", "svm_course_deck.pptx", "https://raw.githubusercontent.com/marcio-mourao/Supervised-Learning-SVM/master/SVM.pptx"),
    Fixture("pptx", "azure_data_catalog_training.pptx", "https://raw.githubusercontent.com/Azure-Samples/data-catalog-dotnet-get-started/master/Azure%20Data%20Catalog%20Training.pptx"),
]

# NOTE:
# - Certains sites changent leurs URLs; GitHub raw est généralement stable.
# - Tu peux ajouter tes propres PDF "hard" en complétant FIXTURES.


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(fx: Fixture, out_dir: Path, *, timeout_s: int, max_mb: int, overwrite: bool) -> None:
    target_dir = out_dir / fx.kind
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / fx.name

    if dst.exists() and not overwrite:
        print(f"[SKIP] {fx.kind:4} {fx.name} (exists)")
        return

    max_bytes = max_mb * 1024 * 1024

    print(f"[GET ] {fx.kind:4} {fx.name} <- {fx.url}")
    with requests.get(fx.url, stream=True, timeout=timeout_s) as r:
        r.raise_for_status()

        # best-effort content-length check
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > max_bytes:
            raise RuntimeError(f"Refusing download: Content-Length={cl} > max_mb={max_mb}")

        tmp = dst.with_suffix(dst.suffix + ".part")
        written = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise RuntimeError(f"Refusing download: exceeded max_mb={max_mb} while streaming")
                f.write(chunk)

        tmp.replace(dst)

    print(f"[OK  ] {fx.kind:4} {fx.name} size={dst.stat().st_size} sha256={sha256_file(dst)[:16]}...")


def main(fixtures: Iterable[Fixture]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="fixtures", help="Output directory")
    ap.add_argument("--timeout", type=int, default=60, help="HTTP timeout (seconds)")
    ap.add_argument("--max-mb", type=int, default=50, help="Max size per file (MB)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0

    for fx in fixtures:
        try:
            download_one(fx, out_dir, timeout_s=args.timeout, max_mb=args.max_mb, overwrite=args.overwrite)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[FAIL] {fx.kind:4} {fx.name} :: {e}")

    print(f"\nSummary: ok={ok} fail={fail} out={out_dir}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(FIXTURES))
