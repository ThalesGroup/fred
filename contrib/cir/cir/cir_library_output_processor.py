from __future__ import annotations

import json
import logging
import shutil
import tempfile
import base64
import importlib.resources as pkg_resources
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence

from fred_core.processors import (
    DocumentMetadata,
    LibraryDocumentInput,
    LibraryOutputProcessor,
    LibraryProcessorBundle,
    LibraryProcessorRequest,
)
from pydantic import BaseModel

from .config import get_settings

logger = logging.getLogger(__name__)


class CorpusBundle(BaseModel):
    graph_dir: Path
    archive_path: Path
    corpus_size: int


class CirLibraryOutputProcessor(LibraryOutputProcessor):
    """
    Standalone HippoRAG library processor (no Knowledge Flow dependency).

    - Accepts markdown previews + DocumentMetadata.
    - Builds a corpus and optional HippoRAG graph (if dependency installed).
    - Returns updated metadata with a `hipporag` extension describing the bundle.
    """

    description = "Builds a HippoRAG knowledge graph for a library."

    def __init__(self) -> None:
        settings = get_settings()
        self.max_words_per_chunk = max(1, settings.max_words_per_chunk)
        self.settings = settings

        work_root = Path(tempfile.gettempdir()) / "fred-hipporag"
        work_root.mkdir(parents=True, exist_ok=True)
        self.work_root = work_root

    def process_library(
        self,
        documents: Sequence[LibraryDocumentInput],
        library_tag: str | None = None,
        request: LibraryProcessorRequest | None = None,
    ) -> tuple[List[DocumentMetadata], LibraryProcessorBundle]:
        if not documents:
            return [], LibraryProcessorBundle(status="skipped", library_tag=library_tag)

        corpus, doc_strings = self._build_corpus(documents)
        if not corpus:
            logger.info(
                "CirLibraryOutputProcessor: no usable markdown previews, skipping."
            )
            return [entry.metadata for entry in documents], LibraryProcessorBundle(
                status="skipped", library_tag=library_tag, document_count=len(documents), corpus_size=0
            )

        bundle = self._build_bundle(corpus, doc_strings)

        bundle_meta = {
            "graph_bundle_path": str(bundle.archive_path),
            "library_tag": library_tag,
            "document_count": len(documents),
            "corpus_size": bundle.corpus_size,
            "status": "success",
        }

        for entry in documents:
            entry.metadata.extensions = entry.metadata.extensions or {}
            entry.metadata.extensions["hipporag"] = bundle_meta

        bundle_info = self._package_bundle(bundle, request, len(documents))

        return [entry.metadata for entry in documents], bundle_info

    def _build_corpus(
        self, documents: Sequence[LibraryDocumentInput]
    ) -> tuple[list[dict], list[str]]:
        corpus: list[dict] = []
        doc_strings: list[str] = []

        for entry in documents:
            text = entry.preview_markdown
            if not text and entry.file_path:
                path = Path(entry.file_path)
                if path.suffix.lower() != ".md":
                    logger.info(
                        "CirLibraryOutputProcessor: skipping non-markdown preview %s",
                        path,
                    )
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "CirLibraryOutputProcessor: failed to read %s (%s)", path, exc
                    )
                    continue
            if not text:
                logger.info(
                    "CirLibraryOutputProcessor: empty preview for %s",
                    entry.metadata.document_uid,
                )
                continue

            text = text.strip()

            title_base = entry.metadata.title or entry.metadata.document_name
            date_str = (
                entry.metadata.created.isoformat()
                if entry.metadata.created
                else entry.metadata.source.date_added_to_kb.isoformat()
            )

            chunks = self._chunk_markdown(text)
            if not chunks:
                chunks = [text.strip()]

            for idx, chunk in enumerate(chunks):
                chunk_title = f"{title_base}_{idx + 1}"
                corpus.append(
                    {
                        "title": chunk_title,
                        "text": chunk,
                        "context": None,
                        "date": date_str,
                    }
                )
                doc_strings.append(
                    f"Filename: {chunk_title}\nText:\n{chunk}\nDate:{date_str}\n"
                )

        return corpus, doc_strings

    def _chunk_markdown(self, text: str) -> list[str]:
        """
        Lightweight chunker: respects paragraph boundaries and caps by word count.
        """
        max_words = self.max_words_per_chunk
        chunks: list[str] = []
        current: list[str] = []
        word_budget = 0

        for paragraph in text.split("\n\n"):
            words = paragraph.split()
            if not words:
                continue

            if word_budget + len(words) <= max_words:
                current.append(paragraph.strip())
                word_budget += len(words)
                continue

            if current:
                chunks.append("\n\n".join(current).strip())
                current = []
                word_budget = 0

            if len(words) > max_words:
                words_only: list[str] = []
                for word in words:
                    words_only.append(word)
                    if len(words_only) >= max_words:
                        chunks.append(" ".join(words_only).strip())
                        words_only = []
                if words_only:
                    current.append(" ".join(words_only).strip())
                    word_budget = len(words_only)
            else:
                current.append(paragraph.strip())
                word_budget = len(words)

        if current:
            chunks.append("\n\n".join(current).strip())

        return chunks

    def _build_bundle(self, corpus: list[dict], docs: list[str]) -> CorpusBundle:
        graph_dir = Path(tempfile.mkdtemp(prefix="hipporag-", dir=self.work_root))
        self._write_corpus_manifest(graph_dir, corpus)
        self._maybe_run_hipporag(graph_dir, corpus, docs)

        archive_path = Path(
            shutil.make_archive(
                base_name=str(graph_dir),
                format="zip",
                root_dir=graph_dir,
            )
        )
        return CorpusBundle(
            graph_dir=graph_dir, archive_path=archive_path, corpus_size=len(corpus)
        )

    def _write_corpus_manifest(self, graph_dir: Path, corpus: list[dict]) -> None:
        graph_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "corpus_size": len(corpus),
        }
        (graph_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
        )
        with open(graph_dir / "corpus.jsonl", "w", encoding="utf-8") as f:
            for item in corpus:
                f.write(json.dumps(item, ensure_ascii=True) + "\n")

    def _maybe_run_hipporag(
        self, graph_dir: Path, corpus: list[dict], docs: list[str]
    ) -> bool:
        try:
            from hipporag import HippoRAG
            from hipporag.utils.config_utils import BaseConfig
        except ImportError:
            logger.info(
                "CirLibraryOutputProcessor: hipporag dependency not installed; only corpus is exported."
            )
            return False

        # Resolve rerank prompt path
        rerank_path: str | None = None
        if self.settings.rerank_prompt_path:
            candidate = Path(self.settings.rerank_prompt_path)
            if candidate.exists():
                rerank_path = str(candidate)
            else:
                logger.warning("Configured rerank prompt path does not exist: %s", candidate)
        if rerank_path is None:
            try:
                pkg_path = pkg_resources.files("hipporag.prompts.dspy_prompts") / "filter_llama3.3-70B-Instruct.json"  # type: ignore[arg-type]
                if pkg_path.is_file():
                    rerank_path = str(pkg_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to resolve default rerank prompt from hipporag package: %s", exc)

        if rerank_path is None:
            logger.warning("No rerank prompt found; falling back to HippoRAG built-in default prompt.")

        s = self.settings
        config = BaseConfig(
            save_dir=str(graph_dir),
            llm_base_url=s.llm_base_url,
            llm_name=s.llm_model,
            dataset=str(graph_dir),
            embedding_model_name=s.embedding_model,
            rerank_dspy_file_path=rerank_path,
            retrieval_top_k=s.retrieval_top_k,
            linking_top_k=s.linking_top_k,
            max_qa_steps=s.max_qa_steps,
            qa_top_k=s.qa_top_k,
            graph_type=s.graph_type,
            embedding_batch_size=s.embedding_batch_size,
            max_new_tokens=s.max_new_tokens,
            corpus_len=len(corpus),
            openie_mode=s.openie_mode,
            save_openie=s.save_openie,
            information_extraction_model_name=s.openie_model,
            temperature=s.temperature,
            force_index_from_scratch=True,
            force_openie_from_scratch=True,
            is_directed_graph=s.directed_graph,
            preprocess_chunk_overlap_token_size=s.chunk_overlap_tokens,
            preprocess_chunk_func=s.chunk_func,
            preprocess_chunk_max_token_size=None,
        )

        logger.info(
            "CirLibraryOutputProcessor: launching HippoRAG with %d corpus chunks",
            len(corpus),
        )
        hipporag = HippoRAG(global_config=config)
        hipporag.index(docs=docs)
        logger.info(
            "CirLibraryOutputProcessor: HippoRAG graph generated in %s", graph_dir
        )
        return True

    def _package_bundle(
        self, bundle: CorpusBundle, request: LibraryProcessorRequest | None, document_count: int
    ) -> LibraryProcessorBundle:
        data = bundle.archive_path.read_bytes()
        bundle_name = bundle.archive_path.name
        corpus_size = bundle.corpus_size

        upload_url = request.bundle_upload_url if request else None
        upload_headers = request.bundle_upload_headers if request else {}
        return_inline = True if request is None else request.return_bundle_inline

        if upload_url:
            try:
                import httpx

                with httpx.Client(timeout=120) as client:
                    resp = client.put(upload_url, headers=upload_headers, content=data)
                    resp.raise_for_status()
                return LibraryProcessorBundle(
                    status="uploaded",
                    upload_status="success",
                    upload_url=str(upload_url),
                    bundle_name=bundle_name,
                    bundle_size_bytes=len(data),
                    library_tag=request.library_tag if request else None,
                    corpus_size=corpus_size,
                    document_count=document_count,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bundle upload failed: %s", exc)
                # Fallback to inline if allowed
                if not return_inline:
                    return LibraryProcessorBundle(
                        status="failed",
                        error=str(exc),
                        upload_status="failed",
                        upload_url=str(upload_url),
                        bundle_name=bundle_name,
                        bundle_size_bytes=len(data),
                        library_tag=request.library_tag if request else None,
                        corpus_size=corpus_size,
                        document_count=document_count,
                    )

        b64_bundle = base64.b64encode(data).decode("ascii") if return_inline else None
        return LibraryProcessorBundle(
            status="success",
            bundle_name=bundle_name,
            bundle_size_bytes=len(data),
            bundle_b64=b64_bundle,
            library_tag=request.library_tag if request else None,
            corpus_size=corpus_size,
            document_count=document_count,
        )
