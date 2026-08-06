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

"""
Read-only reconciliation scan for the Kea->Swift "stuck pending" gap (GitHub #2234).

Documents restored by the manual OpenSearch/S3 copy have their Postgres
`processing.stages` reset by the importer (`importer.py::_reset_transported_stages`),
so `stages["vector"]`/`stages["sql"]` read `not_started` even when the real
content already exists. `/corpus/revectorize` (mode=incremental, force=false)
is the safe repair path, but running it blind at ~10k documents across an
unknown number of `source_tag` values is not "extra sure": it silently falls
back to a real, costly re-embed whenever `get_document_chunk_count` errors or
returns 0 (index misconfiguration, or a genuinely never-restored document),
and it never repairs the `sql` stage for tabular (CSV/XLSX) documents at all.

This script makes NO writes anywhere (Postgres, OpenSearch, object store). It
loads every document's metadata and, for each one not already marked done,
checks the *real* backing store directly -- the same calls the production
workflow (`RevectorizeDocument`, `features/scheduler/workflow.py`) makes --
and buckets the result so an operator can see, with real numbers instead of
guesses, which repairs are free and which are not, per `source_tag`, before
anything is run for real.

Buckets:
  already_ready          -- stage already DONE, nothing to do.
  safe_repair             -- vector chunks exist; /corpus/revectorize will only
                              flip the Postgres flag, no re-embed.
  needs_real_reembed      -- 0 vector chunks found; /corpus/revectorize would
                              trigger a genuine (LLM-cost) re-embed. Review by
                              hand before running.
  tabular_ok_flag_only    -- Parquet artifact exists in the content store but
                              `sql` stage isn't marked done; NOT fixed by
                              /corpus/revectorize today (metadata-only repair
                              is vector-only) -- needs a small backend addition
                              or a manual flag flip.
  tabular_needs_reprocess -- no Parquet artifact found; a real re-process is
                              required, not just a flag repair.
  count_error              -- the real-store check itself failed (e.g. index
                              name/config mismatch). Fix and re-run the scan
                              before touching anything else -- do NOT treat
                              these as "needs_real_reembed", the check itself
                              is unreliable for them.

Usage (against the target environment's own config, same as the API/worker):

  CONFIG_FILE=/path/to/target-configuration.yaml \
    uv run python -m knowledge_flow_backend.scripts.kea_reconcile_scan \
    [--out report.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass

from fred_core.documents.document_structures import (
    DocumentMetadata,
    ProcessingStage,
    ProcessingStatus,
)

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import load_configuration
from knowledge_flow_backend.core.stores.content.base_content_store import BaseContentStore
from knowledge_flow_backend.core.stores.vector.base_vector_store import BaseVectorStore
from knowledge_flow_backend.features.tabular.artifacts import (
    TABULAR_EXTENSION_KEY,
    TABULAR_MULTI_EXTENSION_KEY,
)

logger = logging.getLogger("kea_reconcile_scan")

_TABULAR_FILE_TYPES = {"csv", "xlsx"}


@dataclass
class DocVerdict:
    document_uid: str
    document_name: str
    source_tag: str | None
    file_type: str
    bucket: str
    detail: str = ""


def _tabular_object_key(metadata: DocumentMetadata) -> str | None:
    extensions = metadata.extensions or {}
    single = extensions.get(TABULAR_EXTENSION_KEY)
    if isinstance(single, dict) and single.get("object_key"):
        return str(single["object_key"])
    multi = extensions.get(TABULAR_MULTI_EXTENSION_KEY)
    if isinstance(multi, dict):
        tables = multi.get("tables")
        if isinstance(tables, list) and tables and isinstance(tables[0], dict):
            return str(tables[0].get("object_key")) if tables[0].get("object_key") else None
    return None


async def _scan_one(
    metadata: DocumentMetadata,
    vector_store: BaseVectorStore,
    content_store: BaseContentStore,
) -> DocVerdict:
    uid = metadata.identity.document_uid
    name = metadata.identity.document_name
    source_tag = metadata.source.source_tag
    file_type = metadata.file.file_type.value if metadata.file else "other"
    stages = metadata.processing.stages

    if file_type in _TABULAR_FILE_TYPES:
        if stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE:
            return DocVerdict(uid, name, source_tag, file_type, "already_ready")
        object_key = _tabular_object_key(metadata)
        if not object_key:
            return DocVerdict(uid, name, source_tag, file_type, "tabular_needs_reprocess", "no tabular_v1/tabular_multi_v1 extension recorded")
        try:
            await asyncio.to_thread(content_store.stat_object, object_key)
            return DocVerdict(
                uid,
                name,
                source_tag,
                file_type,
                "tabular_ok_flag_only",
                f"parquet present at {object_key}; sql stage needs a metadata-only repair not yet wired up",
            )
        except FileNotFoundError:
            return DocVerdict(uid, name, source_tag, file_type, "tabular_needs_reprocess", f"parquet missing at {object_key}")
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any store failure must surface as count_error, never as a silent 0
            return DocVerdict(uid, name, source_tag, file_type, "count_error", f"stat_object({object_key}) failed: {exc}")

    if stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE:
        return DocVerdict(uid, name, source_tag, file_type, "already_ready")

    if not hasattr(vector_store, "get_document_chunk_count"):
        return DocVerdict(uid, name, source_tag, file_type, "count_error", f"{type(vector_store).__name__} has no get_document_chunk_count")

    try:
        count = await asyncio.to_thread(vector_store.get_document_chunk_count, document_uid=uid)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 -- same reasoning: never fold a real error into "0 chunks"
        return DocVerdict(uid, name, source_tag, file_type, "count_error", str(exc))

    if count > 0:
        return DocVerdict(uid, name, source_tag, file_type, "safe_repair", f"{count} chunks already indexed")
    return DocVerdict(uid, name, source_tag, file_type, "needs_real_reembed", "0 chunks found in the vector store")


async def run(out_path: str | None) -> None:
    configuration = load_configuration()
    ApplicationContext(configuration)
    app_context = ApplicationContext.get_instance()

    metadata_store = app_context.get_metadata_store()
    content_store = app_context.get_content_store()
    vector_store = app_context.get_create_vector_store(app_context.get_embedder())

    docs = await metadata_store.get_all_metadata({})
    logger.info("Loaded %d document metadata row(s)", len(docs))

    verdicts = [await _scan_one(d, vector_store, content_store) for d in docs]

    by_tag: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for v in verdicts:
        by_tag[v.source_tag or "<no source_tag>"][v.bucket] += 1

    print("\n=== Kea reconciliation scan -- per source_tag ===")
    grand_total: dict[str, int] = defaultdict(int)
    for tag, counts in sorted(by_tag.items()):
        print(f"\nsource_tag={tag}  (total={sum(counts.values())})")
        for bucket, n in sorted(counts.items()):
            print(f"  {bucket:26s} {n}")
            grand_total[bucket] += n

    print(f"\n=== TOTAL ({len(verdicts)} documents) ===")
    for bucket, n in sorted(grand_total.items()):
        print(f"  {bucket:26s} {n}")

    if grand_total.get("count_error"):
        print(
            f"\n/!\\ {grand_total['count_error']} document(s) errored checking the real store -- "
            "fix this (likely an index/config mismatch) BEFORE running /corpus/revectorize. "
            "Run with --out and inspect their `detail` field."
        )
    if grand_total.get("needs_real_reembed"):
        print(f"/!\\ {grand_total['needs_real_reembed']} document(s) have 0 real vector chunks -- /corpus/revectorize would trigger a genuine, costly re-embed for these. Review by hand.")
    if grand_total.get("tabular_needs_reprocess"):
        print(f"/!\\ {grand_total['tabular_needs_reprocess']} tabular document(s) have no Parquet artifact -- these need a real re-process, not a flag repair.")
    if grand_total.get("tabular_ok_flag_only"):
        print(
            f"/!\\ {grand_total['tabular_ok_flag_only']} tabular document(s) have their Parquet artifact but "
            "no repair path exists yet for the `sql` stage -- /corpus/revectorize's metadata-only skip only "
            "marks `vector`, never `sql`."
        )

    if out_path:
        with open(out_path, "w") as f:
            json.dump([asdict(v) for v in verdicts], f, indent=2)
        print(f"\nFull per-document report written to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None, help="Optional path to write the full per-document JSON report")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    asyncio.run(run(args.out))


if __name__ == "__main__":
    main()
