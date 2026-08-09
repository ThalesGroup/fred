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
Seed a large synthetic corpus (fake libraries + documents + vectors) for local
load-testing of repair/audit tooling (e.g. metadata/vector reconciliation scans,
`/corpus/revectorize`, `MetadataService.audit_stores`).

This writes directly to the same Postgres tag/metadata stores, OpenSearch
vector index, ReBAC engine (OpenFGA), and content store (Minio/S3) the
running backend uses -- it does NOT go through the ingestion pipeline, so no
LLM/embedding cost is incurred for the documents themselves. The only real
network call is a single dummy embedding to learn the configured vector
dimension (needed so fake vectors match the real mapping); everything else
is synthetic. Pass --skip-content to skip writing content objects
(Postgres+OpenSearch+ReBAC only, faster, but every document is flagged
`missing_content` by audit tooling).

`--team-id` must be the team's *real* internal id, not its display name --
they are different strings (see `teammetadata` table). A document's ReBAC
visibility (schema.fga: `tag.read = ... team_member from owner`, then
`document.read = read from parent`) depends on BOTH the tag->team ownership
tuple AND a document->tag parent tuple per document; this script writes both,
but a wrong --team-id makes every seeded library invisible with no error.

Intended for a LOCAL docker-compose stack only. Never point CONFIG_FILE at a
shared/staging/prod configuration when running this.

Usage (against your local stack's own config, same as the API/worker):

  CONFIG_FILE=/path/to/local-configuration.yaml \
    uv run python -m knowledge_flow_backend.scripts.seed_synthetic_corpus \
    --team-id fredlab --libraries 100 --documents 20000

  # Remove everything this script previously created (matched by identity.uploaded_by,
  # never by source_tag -- see the note on source_tag="fred" below), before
  # re-seeding a fresh run:
  CONFIG_FILE=/path/to/local-configuration.yaml \
    uv run python -m knowledge_flow_backend.scripts.seed_synthetic_corpus --purge
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Iterator

import numpy as np
from fred_core import RebacReference, Relation, RelationType, Resource
from fred_core.documents.document_structures import (
    AccessInfo,
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from minio.deleteobjects import DeleteObject
from opensearchpy.helpers import bulk

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import load_configuration
from knowledge_flow_backend.core.stores.content.minio_content_store import MinioStorageBackend
from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from knowledge_flow_backend.features.tag.structure import Tag, TagType

logger = logging.getLogger("seed_synthetic_corpus")

SEED_UPLOADED_BY = "seed-synthetic-corpus"
SEED_CHUNK_SUFFIX = "::seed-chunk-0"


def _build_tag(team_id: str, index: int) -> Tag:
    now = datetime.now(timezone.utc)
    return Tag(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        owner_id=team_id,
        name=f"seed-library-{index:03d}",
        description="Synthetic seed library for local load-testing (seed_synthetic_corpus.py)",
        type=TagType.DOCUMENT,
    )


def _build_document(tag: Tag, index: int) -> DocumentMetadata:
    now = datetime.now(timezone.utc)
    name = f"seed-doc-{index:06d}.txt"
    doc = DocumentMetadata(
        identity=Identity(
            document_name=name,
            document_uid=str(uuid.uuid4()),
            title=name,
            created=now,
            modified=now,
            uploaded_by=SEED_UPLOADED_BY,
        ),
        source=SourceInfo(  # type: ignore[reportCallIssue]  # basedpyright doesn't recognize Field(None, ...) positional defaults (only Field(default=...)) as satisfying SourceInfo's synthesized __init__; pull_location genuinely defaults to None (document_structures.py) -- same false positive on every SourceInfo(...) call omitting it, e.g. test_repair_vector_metadata_activities.py:75
            source_type=SourceType.PUSH,
            # "fred" (not a seed-specific marker) on purpose: it's the same source_tag
            # every real manual upload gets (IngestionInput.source_tag default,
            # ingestion_controller.py) -- repair tooling like 3a filters candidates by
            # source_tag, so a synthetic-only marker here would make seeded documents
            # invisible to exactly the workflows this corpus exists to load-test.
            # `identity.uploaded_by` above is the safe marker `_purge` matches on instead.
            source_tag="fred",
            retrievable=True,
            date_added_to_kb=now,
        ),
        file=FileInfo(
            file_type=FileType.TXT,
            mime_type="text/plain",
            file_size_bytes=random.randint(2_000, 200_000),  # nosec B311: synthetic fixture size, not security-sensitive
            page_count=1,
        ),
        tags=Tagging(tag_ids=[tag.id], tag_names=[tag.name]),
        access=AccessInfo(),
    )
    doc.mark_stage_done(ProcessingStage.RAW_AVAILABLE)
    doc.mark_stage_done(ProcessingStage.PREVIEW_READY)
    doc.mark_stage_done(ProcessingStage.VECTORIZED)
    return doc


async def _seed_tags(tag_store, rebac, team_id: str, n_tags: int, concurrency: int) -> list[Tag]:
    tags = [_build_tag(team_id, i) for i in range(n_tags)]
    sem = asyncio.Semaphore(concurrency)

    async def _one(tag: Tag) -> None:
        async with sem:
            await tag_store.create_tag(tag)
            # Team ownership tuple, mirrors TagService.create_tag_for_user -- without
            # this, a ReBAC-enabled stack won't show the library under the team space.
            await rebac.add_relation(
                Relation(
                    subject=RebacReference(type=Resource.TEAM, id=team_id),
                    relation=RelationType.OWNER,
                    resource=RebacReference(type=Resource.TAGS, id=tag.id),
                )
            )

    await asyncio.gather(*(_one(t) for t in tags))
    return tags


async def _seed_documents(metadata_store, tags: list[Tag], n_docs: int, concurrency: int) -> list[DocumentMetadata]:
    docs: list[DocumentMetadata] = []
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(i: int) -> None:
        nonlocal done
        doc = _build_document(tags[i % len(tags)], i)
        async with sem:
            await metadata_store.save_metadata(doc)
        docs.append(doc)
        done += 1
        if done % 2000 == 0:
            logger.info("  ... %d/%d documents saved", done, n_docs)

    await asyncio.gather(*(_one(i) for i in range(n_docs)))
    return docs


def _document_parent_relation(doc: DocumentMetadata) -> Relation:
    # schema.fga: `document.read = read from parent`, `parent: [tag]`. Without this
    # tuple a document is invisible in any ReBAC-filtered listing (e.g. the
    # "Ressources d'equipe" folder view, MetadataService.get_document_metadata_in_tag)
    # even though the tag/folder itself is visible and the Postgres row carries the
    # right tag_id -- the tag being visible does not imply its documents are.
    return Relation(
        subject=RebacReference(type=Resource.TAGS, id=doc.tags.tag_ids[0]),
        relation=RelationType.PARENT,
        resource=RebacReference(type=Resource.DOCUMENTS, id=doc.document_uid),
    )


async def _seed_document_parent_relations(rebac, docs: list[DocumentMetadata], concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(doc: DocumentMetadata) -> None:
        nonlocal done
        async with sem:
            await rebac.add_relation(_document_parent_relation(doc))
        done += 1
        if done % 2000 == 0:
            logger.info("  ... %d/%d document ReBAC parent tuple(s) written", done, len(docs))

    await asyncio.gather(*(_one(d) for d in docs))


def _content_object_key(doc: DocumentMetadata) -> str:
    # `input/` matters: MinioStorageBackend.get_content() looks for the primary
    # object under exactly this prefix, so this also makes preview/download work,
    # not just the content-store presence check `audit_stores` relies on.
    return f"{doc.document_uid}/input/{doc.document_name}"


def _fake_content_bytes(doc: DocumentMetadata) -> bytes:
    return (
        f"Synthetic seed content for {doc.document_name} (document_uid={doc.document_uid}).\nGenerated by seed_synthetic_corpus.py for local audit/repair load-testing -- not a real file.\n"
    ).encode("utf-8")


async def _seed_content(content_store, docs: list[DocumentMetadata], concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    done = 0

    def _put_one(doc: DocumentMetadata) -> None:
        data = _fake_content_bytes(doc)
        content_store.client.put_object(
            content_store.document_bucket,
            _content_object_key(doc),
            io.BytesIO(data),
            length=len(data),
            content_type="text/plain",
        )

    async def _one(doc: DocumentMetadata) -> None:
        nonlocal done
        async with sem:
            await asyncio.to_thread(_put_one, doc)
        done += 1
        if done % 2000 == 0:
            logger.info("  ... %d/%d fake content object(s) written", done, len(docs))

    await asyncio.gather(*(_one(d) for d in docs))


def _vector_actions(docs: list[DocumentMetadata], index_name: str, dim: int, rng: np.random.Generator) -> Iterator[dict]:
    for doc in docs:
        chunk_uid = f"{doc.document_uid}{SEED_CHUNK_SUFFIX}"
        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": chunk_uid,
            "_source": {
                "text": "Synthetic seed content for local audit/repair load-testing.",
                "vector_field": rng.uniform(-1.0, 1.0, dim).tolist(),
                "metadata": {
                    "document_uid": doc.document_uid,
                    "document_name": doc.document_name,
                    "chunk_uid": chunk_uid,
                    "chunk_index": 0,
                    "tag_ids": list(doc.tags.tag_ids),
                    "retrievable": True,
                    "type": doc.file.file_type.value,
                    "mime_type": doc.file.mime_type,
                    "file_size_bytes": doc.file.file_size_bytes,
                },
            },
        }


async def _purge_document_parent_relations(rebac, docs: list[DocumentMetadata], concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(doc: DocumentMetadata) -> None:
        nonlocal done
        try:
            async with sem:
                await rebac.delete_relation(_document_parent_relation(doc))
        except Exception as exc:  # noqa: BLE001 -- tuple may already be gone (partial prior run); never block metadata cleanup
            logger.debug("Could not delete ReBAC parent tuple for document=%s (may already be absent): %s", doc.document_uid, exc)
        done += 1
        if done % 2000 == 0:
            logger.info("  ... %d/%d document ReBAC parent tuple(s) purged", done, len(docs))

    await asyncio.gather(*(_one(d) for d in docs))


async def _purge(app_context: ApplicationContext, concurrency: int) -> None:
    metadata_store = app_context.get_metadata_store()
    tag_store = app_context.get_tag_store()
    rebac = app_context.get_rebac_engine()
    vector_store = app_context.get_create_vector_store(app_context.get_embedder())
    # This script is explicitly OpenSearch/Minio-only (see module docstring): it writes
    # fake vector chunks and content objects straight to those backends' low-level
    # clients for bulk-seeding/purging performance, bypassing the abstract
    # BaseVectorStore/BaseContentStore interface on purpose. Narrowing with isinstance
    # (instead of a blanket type:ignore on every attribute access below) gives real type
    # safety and a clear failure if this is ever run against a differently configured
    # local stack (e.g. Chroma or filesystem content storage) instead of a cryptic
    # AttributeError mid-purge.
    if not isinstance(vector_store, OpenSearchVectorStoreAdapter):
        raise RuntimeError(f"seed_synthetic_corpus.py only supports the OpenSearch-backed vector store; configured backend is {type(vector_store).__name__}.")

    # Matched on identity.uploaded_by, not source_tag: seeded documents deliberately
    # carry source_tag="fred" (the same value every real upload gets) so repair
    # tooling that filters by source_tag actually sees them -- uploaded_by is the
    # marker no real document shares, so this is still exact and safe.
    docs = await metadata_store.get_all_metadata({"identity": {"uploaded_by": SEED_UPLOADED_BY}})
    logger.info("Purging %d previously seeded document(s) (ReBAC parent tuple + Postgres row) ...", len(docs))
    if docs:
        await _purge_document_parent_relations(rebac, docs, concurrency)
    tag_ids: set[str] = set()
    doc_uids: list[str] = []
    for doc in docs:
        tag_ids.update(doc.tags.tag_ids or [])
        doc_uids.append(doc.document_uid)
        await metadata_store.delete_metadata(doc.document_uid)

    if docs:
        # Content objects carry no "seed" marker of their own -- they're only
        # findable through the Postgres rows just deleted above, via the exact
        # key this script writes them under (`_content_object_key`). A content
        # object orphaned by an earlier run that died between these two steps
        # would not be caught here; that's a known gap, not a bug in this pass.
        content_store = app_context.get_content_store()
        if not isinstance(content_store, MinioStorageBackend):
            raise RuntimeError(f"seed_synthetic_corpus.py only supports the MinIO/S3-backed content store; configured backend is {type(content_store).__name__}.")
        logger.info("Purging %d fake content object(s) from bucket=%s ...", len(docs), content_store.document_bucket)
        delete_list = [DeleteObject(_content_object_key(doc)) for doc in docs]
        errors = list(content_store.client.remove_objects(content_store.document_bucket, delete_list))
        if errors:
            logger.warning("Some content object(s) failed to delete: %s", errors[:5])

    all_tags = await tag_store.list_all_tags()
    seed_tags = [t for t in all_tags if t.id in tag_ids or t.name.startswith("seed-library-")]
    logger.info("Purging %d previously seeded library/tag(s) (Postgres row + ReBAC ownership tuple) ...", len(seed_tags))
    for tag in seed_tags:
        try:
            await rebac.delete_relation(
                Relation(
                    subject=RebacReference(type=Resource.TEAM, id=tag.owner_id),
                    relation=RelationType.OWNER,
                    resource=RebacReference(type=Resource.TAGS, id=tag.id),
                )
            )
        except Exception as exc:  # noqa: BLE001 -- tuple may already be gone (partial prior run); never block the Postgres cleanup below on it
            logger.warning("Could not delete ReBAC ownership tuple for tag=%s (may already be absent): %s", tag.id, exc)
        await tag_store.delete_tag_by_id(tag.id)

    # Match on *both* document_uid (docs found via uploaded_by above) and tag_ids
    # (covers a prior interrupted run that deleted the Postgres row but not the
    # vector chunk, or vice versa) -- either signal alone can miss a partial run.
    seed_tag_id_list = [t.id for t in seed_tags]
    should_clauses: list[dict] = []
    if doc_uids:
        should_clauses.append({"terms": {"metadata.document_uid": doc_uids}})
    if seed_tag_id_list:
        should_clauses.append({"terms": {"metadata.tag_ids": seed_tag_id_list}})

    if should_clauses:
        logger.info("Purging fake vector chunks from OpenSearch index=%s ...", vector_store.index_name)
        resp = vector_store.client.delete_by_query(
            index=vector_store.index_name,
            body={"query": {"bool": {"should": should_clauses, "minimum_should_match": 1}}},
        )
        vector_store.client.indices.refresh(index=vector_store.index_name)
        logger.info("Deleted %d vector chunk(s).", resp.get("deleted", 0))
    else:
        logger.info("No seeded document_uid/tag_ids found -- nothing to purge from OpenSearch.")


async def _synthetic_pool(metadata_store) -> list[DocumentMetadata]:
    return await metadata_store.get_all_metadata({"identity": {"uploaded_by": SEED_UPLOADED_BY}})


async def _mark_stuck_pending(metadata_store, n: int, seed: int, concurrency: int) -> None:
    """
    The #2234 "stuck pending" shape, at scale: flip VECTORIZED back to
    NOT_STARTED in Postgres for `n` synthetic documents while leaving their
    OpenSearch chunks and S3 content completely untouched -- Postgres lies
    that the work was never done, even though it demonstrably was. Never
    touches the 18(ish) real documents: the candidate pool is scoped to
    identity.uploaded_by, same as `_purge`.
    """
    pool = await _synthetic_pool(metadata_store)
    eligible = [d for d in pool if d.processing.stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE]
    logger.info("Synthetic pool=%d, eligible (currently vector=done)=%d", len(pool), len(eligible))
    if n > len(eligible):
        logger.warning("Requested %d but only %d eligible -- marking all of them.", n, len(eligible))
    rng = random.Random(seed)  # nosec B311: deterministic sampling for test-corpus reproducibility, not security-sensitive
    chosen = rng.sample(eligible, min(n, len(eligible)))

    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(doc: DocumentMetadata) -> None:
        nonlocal done
        doc.set_stage_status(ProcessingStage.VECTORIZED, ProcessingStatus.NOT_STARTED)
        async with sem:
            await metadata_store.save_metadata(doc)
        done += 1

    await asyncio.gather(*(_one(d) for d in chosen))
    logger.info("Marked %d synthetic document(s) as stuck-pending (vector=not_started; OpenSearch/S3 untouched).", done)


async def _restore_stuck_pending(metadata_store, concurrency: int) -> None:
    """Reverse _mark_stuck_pending: set vector back to DONE for every synthetic
    document currently marked not_started. Safe because nothing else in this
    pool ever sets that stage to not_started -- there's nothing else to confuse
    it with."""
    pool = await _synthetic_pool(metadata_store)
    stuck = [d for d in pool if d.processing.stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.NOT_STARTED]
    logger.info("Restoring %d stuck-pending synthetic document(s) back to vector=done ...", len(stuck))

    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(doc: DocumentMetadata) -> None:
        nonlocal done
        doc.set_stage_status(ProcessingStage.VECTORIZED, ProcessingStatus.DONE)
        async with sem:
            await metadata_store.save_metadata(doc)
        done += 1

    await asyncio.gather(*(_one(d) for d in stuck))
    logger.info("Restored %d document(s).", done)


async def run(args: argparse.Namespace) -> None:
    configuration = load_configuration()
    ApplicationContext(configuration)
    app_context = ApplicationContext.get_instance()

    if args.purge:
        await _purge(app_context, args.concurrency)
        return

    if args.mark_stuck_pending is not None:
        await _mark_stuck_pending(app_context.get_metadata_store(), args.mark_stuck_pending, args.seed, args.concurrency)
        return

    if args.restore_stuck_pending:
        await _restore_stuck_pending(app_context.get_metadata_store(), args.concurrency)
        return

    tag_store = app_context.get_tag_store()
    metadata_store = app_context.get_metadata_store()
    rebac = app_context.get_rebac_engine()

    logger.info("Creating %d synthetic librar(y/ies) under team_id=%r ...", args.libraries, args.team_id)
    tags = await _seed_tags(tag_store, rebac, args.team_id, args.libraries, args.concurrency)

    logger.info("Creating %d synthetic document(s) across %d librar(y/ies) ...", args.documents, len(tags))
    t0 = time.monotonic()
    docs = await _seed_documents(metadata_store, tags, args.documents, args.concurrency)
    logger.info("Postgres metadata seeded in %.1fs", time.monotonic() - t0)

    logger.info("Writing %d document ReBAC parent tuple(s) (tag -> document) ...", len(docs))
    t0 = time.monotonic()
    await _seed_document_parent_relations(rebac, docs, args.concurrency)
    logger.info("ReBAC parent tuples written in %.1fs", time.monotonic() - t0)

    if not args.skip_content:
        content_store = app_context.get_content_store()
        if not isinstance(content_store, MinioStorageBackend):
            raise RuntimeError(f"seed_synthetic_corpus.py only supports the MinIO/S3-backed content store; configured backend is {type(content_store).__name__}.")
        logger.info("Writing %d small fake content object(s) to bucket=%s ...", len(docs), content_store.document_bucket)
        t0 = time.monotonic()
        await _seed_content(content_store, docs, args.concurrency)
        logger.info("Fake content written in %.1fs", time.monotonic() - t0)

    logger.info("Resolving the real embedder once to learn the configured vector dimension (one real API call) ...")
    vector_store = app_context.get_create_vector_store(app_context.get_embedder())
    if not isinstance(vector_store, OpenSearchVectorStoreAdapter):
        raise RuntimeError(f"seed_synthetic_corpus.py only supports the OpenSearch-backed vector store; configured backend is {type(vector_store).__name__}.")
    index_name = vector_store.index_name
    if index_name is None:
        raise RuntimeError("OpenSearch vector store has no configured index_name.")
    mapping = vector_store.client.indices.get_mapping(index=index_name)
    dim = mapping[index_name]["mappings"]["properties"]["vector_field"]["dimension"]
    logger.info("Vector index=%s dimension=%d -- indexing %d fake vector chunk(s) ...", index_name, dim, len(docs))

    t0 = time.monotonic()
    rng = np.random.default_rng(args.seed)
    success, errors = bulk(
        vector_store.client,
        _vector_actions(docs, index_name, dim, rng),
        chunk_size=1000,
        request_timeout=120,
        raise_on_error=False,
    )
    vector_store.client.indices.refresh(index=index_name)
    logger.info(
        "Indexed %d fake vector chunk(s) in %.1fs (errors=%d)",
        success,
        time.monotonic() - t0,
        len(errors) if isinstance(errors, list) else 0,
    )
    if errors:
        logger.warning("First few bulk errors: %s", errors[:3])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team-id", default="fredlab", help="Team space that will own the synthetic libraries.")
    parser.add_argument("--libraries", type=int, default=100, help="Number of synthetic libraries (tags) to create.")
    parser.add_argument("--documents", type=int, default=20000, help="Number of synthetic documents to create, spread round-robin across libraries.")
    parser.add_argument("--concurrency", type=int, default=20, help="Max concurrent Postgres writes.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for fake vectors/sizes (reproducible runs).")
    parser.add_argument("--skip-content", action="store_true", help="Skip writing small fake content objects to the content store (Minio/S3) -- Postgres+OpenSearch only, faster.")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Delete everything a previous run of this script created (matched by identity.uploaded_by / seed-library-* tag names), then exit. Run again without --purge to re-seed.",
    )
    parser.add_argument(
        "--mark-stuck-pending",
        type=int,
        default=None,
        metavar="N",
        help="Standalone action: flip N already-seeded synthetic documents' vector stage back to not_started in Postgres, leaving their OpenSearch chunks and S3 content untouched (the #2234 'stuck pending' shape, at scale). Never touches real documents. Exits after running.",
    )
    parser.add_argument(
        "--restore-stuck-pending",
        action="store_true",
        help="Standalone action: reverse --mark-stuck-pending -- set vector back to done for every synthetic document currently marked not_started. Exits after running.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
