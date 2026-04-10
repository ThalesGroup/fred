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

from __future__ import annotations

import copy
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar
from urllib.parse import quote_plus

import clickhouse_connect
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sqlalchemy import MetaData, Table, create_engine, distinct, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, AnnHit, BaseVectorHit, BaseVectorStore, FullTextHit, HybridHit, SearchFilter

logger = logging.getLogger(__name__)
DEBUG = True

_SAFE_SQL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_METADATA_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RETRIEVABLE_COLUMN = "retrievable"
_SCOPE_COLUMN = "scope"
_USER_COLUMN = "user_id"
_SESSION_COLUMN = "session_id"
_DOC_UID_COLUMN = "document_uid"

T = TypeVar("T", bound=BaseVectorHit)


def _safe_sql_name(value: str, *, field: str) -> str:
    if not _SAFE_SQL_NAME.match(value):
        raise ValueError(f"Invalid SQL identifier for {field}: {value!r}")
    return value


def _to_json_safe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, set):
        return list(v)
    if isinstance(v, dict):
        return {k: _to_json_safe(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_to_json_safe(x) for x in v]
    return v


def _normalize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    md = dict(md or {})
    for key in ("created", "modified", "date_added_to_kb"):
        if key in md:
            md[key] = _to_json_safe(md[key])
    tag_ids = md.get("tag_ids")
    if tag_ids is None:
        md["tag_ids"] = []
    elif isinstance(tag_ids, str):
        md["tag_ids"] = [tag_ids]
    else:
        md["tag_ids"] = [str(x) for x in list(tag_ids)]
    return _to_json_safe(md)


def _ensure_chunk_uid(md: Dict[str, Any]) -> str:
    cid = md.get(CHUNK_ID_FIELD)
    if isinstance(cid, str) and cid:
        return cid
    doc_uid = md.get("document_uid")
    cidx = md.get("chunk_index")
    if isinstance(doc_uid, str) and doc_uid and isinstance(cidx, int):
        cid = f"{doc_uid}::chunk::{cidx}"
    else:
        cid = f"chunk_{int(datetime.now(timezone.utc).timestamp() * 1000000)}"
    md[CHUNK_ID_FIELD] = cid
    return cid


def _as_list(values: Any) -> List[Any]:
    if values is None:
        return []
    try:
        return list(values)
    except TypeError:
        return [values]


def _split_metadata_values(values: Any) -> tuple[List[Any], List[Any]]:
    include_values: List[Any] = []
    exclude_values: List[Any] = []
    for v in _as_list(values):
        if isinstance(v, str) and v.startswith("!"):
            if v[1:]:
                exclude_values.append(v[1:])
        else:
            include_values.append(v)
    return include_values, exclude_values


def _is_true_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1"}
    return value is True or value == 1


def _is_false_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"false", "0"}
    return value is False or value == 0


def _as_nullable_uint8(value: Any) -> Optional[int]:
    if value is None:
        return None
    if _is_true_value(value):
        return 1
    if _is_false_value(value):
        return 0
    return None


def _min_max_normalize(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


class ClickHouseVectorStoreAdapter(BaseVectorStore):
    """
    ClickHouse-backed Vector Store with OpenSearch-like API surface.
    - add_documents / delete / ANN / full_text / hybrid
    - diagnostics helpers used by metadata endpoints
    """

    def __init__(
        self,
        embedding_model: Embeddings,
        embedding_model_name: str,
        host: str,
        database: str,
        table: str,
        username: str,
        password: str,
        *,
        port: int = 8123,
        secure: bool = False,
        verify: bool = True,
        bulk_size: int = 1000,
        client_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._database = _safe_sql_name(database, field="database")
        self._table = _safe_sql_name(table, field="table")
        self._username = username
        self._password = password
        self._secure = secure
        self._verify = verify
        self._bulk_size = bulk_size
        self._client_settings = dict(client_settings or {})
        self._embedding_model = embedding_model
        self._embedding_model_name = embedding_model_name
        self._expected_dim: Optional[int] = None
        self._ch = None
        self._sa_engine: Optional[Engine] = None
        self._sa_metadata = MetaData()
        self._sa_table: Optional[Table] = None

        logger.info(
            "[VECTOR][CLICKHOUSE] initialized host=%s port=%s database=%s table=%s secure=%s",
            self._host,
            self._port,
            self._database,
            self._table,
            self._secure,
        )

    @property
    def index_name(self) -> Optional[str]:
        return self._table

    @property
    def _table_ref(self) -> str:
        return f"{self._database}.{self._table}"

    @property
    def _sqlalchemy_uri(self) -> str:
        auth = f"{quote_plus(self._username)}:{quote_plus(self._password)}@" if self._username else ""
        uri = f"clickhousedb://{auth}{self._host}:{self._port}/{self._database}"
        params: list[str] = []
        params.append(f"secure={'true' if self._secure else 'false'}")
        params.append(f"verify={'true' if self._verify else 'false'}")
        return f"{uri}?{'&'.join(params)}"

    @property
    def _client(self):
        if self._ch is None:
            self._ch = clickhouse_connect.get_client(
                host=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                database=self._database,
                secure=self._secure,
                verify=self._verify,
                **self._client_settings,
            )
        return self._ch

    @property
    def _engine(self) -> Engine:
        if self._sa_engine is None:
            # Registers clickhousedb SQLAlchemy dialect.
            import clickhouse_connect.cc_sqlalchemy  # noqa: F401

            self._sa_engine = create_engine(self._sqlalchemy_uri, future=True)
        return self._sa_engine

    @property
    def _orm_table(self) -> Table:
        if self._sa_table is None:
            self._ensure_table_exists()
            self._sa_metadata.clear()
            self._sa_table = Table(
                self._table,
                self._sa_metadata,
                schema=self._database,
                autoload_with=self._engine,
            )
        return self._sa_table

    def _query_rows(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> List[tuple]:
        res = self._client.query(sql, parameters=parameters or {})
        return [tuple(r) for r in (res.result_rows or [])]

    def _command(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> Any:
        return self._client.command(sql, parameters=parameters or {})

    def _get_embedding_dimension(self) -> int:
        dummy_vector = self._embedding_model.embed_query("dummy")
        return len(dummy_vector)

    def _ensure_table_exists(self) -> None:
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self._table_ref}
        (
            chunk_uid String,
            document_uid String,
            text String,
            metadata String,
            tag_ids Array(String),
            retrievable Nullable(UInt8),
            scope Nullable(String),
            user_id Nullable(String),
            session_id Nullable(String),
            embedding Array(Float32),
            embedding_dim UInt16,
            embedding_model LowCardinality(String),
            vector_index LowCardinality(String),
            token_count UInt32,
            ingested_at DateTime64(3, 'UTC')
        )
        ENGINE = ReplacingMergeTree(ingested_at)
        ORDER BY (document_uid, chunk_uid)
        """
        self._command(create_sql)

    def validate_index_or_fail(self) -> None:
        logger.info(
            "[VECTOR][CLICKHOUSE] validating vector table=%s",
            self._table_ref,
        )
        try:
            self._ensure_table_exists()
            expected_dim = self._expected_dim or self._get_embedding_dimension()
            self._expected_dim = expected_dim
            t = self._orm_table
            stmt = select(t.c.embedding_dim).where(t.c.embedding_dim > 0).limit(1)
            with Session(self._engine, future=True) as session:
                row = session.execute(stmt).first()
            if row:
                actual_dim = int(row[0])
                if actual_dim != expected_dim:
                    raise ValueError(
                        "ClickHouse vector table is not compatible with the configured embedding model.\n"
                        f"   Table: {self._table_ref}\n"
                        f"   Model: {self._embedding_model_name or 'unknown'}\n"
                        f"   Dimension mismatch: table has {actual_dim}, model requires {expected_dim}."
                    )
        except ValueError as e:
            logger.critical("[VECTOR][CLICKHOUSE] table validation failed: %s", e)
            raise SystemExit(1) from e

    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        try:
            if ids is not None and len(ids) != len(documents):
                raise ValueError("ids length must match documents length")
            if not documents:
                return []

            self._ensure_table_exists()
            expected_dim = self._expected_dim or self._get_embedding_dimension()
            self._expected_dim = expected_dim
            table = self._orm_table

            assigned_ids: List[str] = []
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            model_name = self._embedding_model_name or "unknown"
            vectors = self._embedding_model.embed_documents([d.page_content or "" for d in documents])

            rows: List[Dict[str, Any]] = []
            for idx, (doc, vec) in enumerate(zip(documents, vectors)):
                md = _normalize_metadata(doc.metadata or {})
                forced_id = ids[idx] if ids else None
                if forced_id:
                    md[CHUNK_ID_FIELD] = forced_id
                cid = _ensure_chunk_uid(md)
                assigned_ids.append(cid)
                md.setdefault("embedding_model", model_name)
                md.setdefault("vector_index", self._table)
                md.setdefault("token_count", len((doc.page_content or "").split()))
                md.setdefault("ingested_at", now_iso)

                tag_ids = md.get("tag_ids") or []
                if isinstance(tag_ids, str):
                    tag_ids = [tag_ids]
                tag_ids = [str(x) for x in tag_ids]

                if len(vec) != expected_dim:
                    raise RuntimeError(f"Embedding dimension mismatch for chunk_uid={cid}: got {len(vec)}, expected {expected_dim}")
                float_vec = [float(v) for v in vec]
                token_count = int(md.get("token_count") or len((doc.page_content or "").split()))

                document_uid = str(md.get("document_uid") or "")
                retrievable = _as_nullable_uint8(md.get("retrievable"))
                scope = str(md.get("scope")) if md.get("scope") is not None else None
                user_id = str(md.get("user_id")) if md.get("user_id") is not None else None
                session_id = str(md.get("session_id")) if md.get("session_id") is not None else None

                metadata_json = json.dumps(md, ensure_ascii=True)
                doc.metadata = md

                rows.append(
                    {
                        "chunk_uid": cid,
                        "document_uid": document_uid,
                        "text": doc.page_content or "",
                        "metadata": metadata_json,
                        "tag_ids": tag_ids,
                        "retrievable": retrievable,
                        "scope": scope,
                        "user_id": user_id,
                        "session_id": session_id,
                        "embedding": float_vec,
                        "embedding_dim": len(float_vec),
                        "embedding_model": model_name,
                        "vector_index": self._table,
                        "token_count": token_count,
                        "ingested_at": now,
                    }
                )

            with Session(self._engine, future=True) as session:
                session.execute(table.insert(), rows)
                session.commit()

            logger.debug(
                "[VECTOR][CLICKHOUSE] upserted %s chunk(s) into %s",
                len(assigned_ids),
                self._table_ref,
            )
            return assigned_ids
        except Exception as e:
            logger.exception("[VECTOR][CLICKHOUSE] failed to add documents.")
            raise RuntimeError("Unexpected error during vector indexing.") from e

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        try:
            self._command(
                f"ALTER TABLE {self._table_ref} DELETE WHERE document_uid = {{doc_uid:String}} SETTINGS mutations_sync = 1",
                {"doc_uid": document_uid},
            )
            logger.debug(
                "[VECTOR][CLICKHOUSE] deleted vector chunks for document_uid=%s table=%s",
                document_uid,
                self._table_ref,
            )
        except Exception:
            logger.exception(
                "[VECTOR][CLICKHOUSE] failed to delete vectors for document_uid=%s.",
                document_uid,
            )
            raise RuntimeError("Failed to delete vectors from ClickHouse.")

    def get_document_chunk_count(self, *, document_uid: str) -> int:
        try:
            t = self._orm_table
            stmt = select(func.count()).select_from(t).where(t.c.document_uid == document_uid)
            with Session(self._engine, future=True) as session:
                value = session.execute(stmt).scalar_one()
            return int(value or 0)
        except Exception:
            logger.exception(
                "[VECTOR][CLICKHOUSE] failed to count vector chunks for document_uid=%s in table=%s",
                document_uid,
                self._table_ref,
            )
            return 0

    def list_document_uids(self) -> List[str]:
        try:
            t = self._orm_table
            stmt = select(distinct(t.c.document_uid)).where(t.c.document_uid != "")
            with Session(self._engine, future=True) as session:
                rows = session.execute(stmt).all()
            return sorted([str(r[0]) for r in rows if r and r[0]])
        except Exception:
            logger.warning(
                "[VECTOR][CLICKHOUSE] Could not list document_uids from table=%s",
                self._table_ref,
                exc_info=True,
            )
            return []

    def set_document_retrievable(self, *, document_uid: str, value: bool) -> None:
        try:
            ivalue = 1 if value else 0
            self._command(
                f"ALTER TABLE {self._table_ref} UPDATE retrievable = {{value:UInt8}} WHERE document_uid = {{doc_uid:String}} SETTINGS mutations_sync = 1",
                {"value": ivalue, "doc_uid": document_uid},
            )
            logger.info(
                "[VECTOR][CLICKHOUSE] updated retrievable=%s for document_uid=%s.",
                value,
                document_uid,
            )
        except Exception:
            logger.exception(
                "[VECTOR][CLICKHOUSE] failed to update retrievable flag for document_uid=%s.",
                document_uid,
            )
            raise RuntimeError("Failed to update retrievable flag in ClickHouse.")

    def _decode_metadata(self, metadata_raw: Any, retrievable: Optional[int]) -> Dict[str, Any]:
        md: Dict[str, Any]
        if isinstance(metadata_raw, dict):
            md = dict(metadata_raw)
        elif isinstance(metadata_raw, str) and metadata_raw:
            try:
                parsed = json.loads(metadata_raw)
                md = dict(parsed) if isinstance(parsed, dict) else {}
            except Exception:
                md = {}
        else:
            md = {}
        md = _normalize_metadata(md)
        if retrievable is not None:
            md["retrievable"] = bool(int(retrievable))
        return md

    def get_vectors_for_document(self, document_uid: str, with_document: bool = True) -> List[Dict[str, Any]]:
        try:
            t = self._orm_table
            if with_document:
                stmt = select(t.c.chunk_uid, t.c.embedding, t.c.text).where(t.c.document_uid == document_uid)
            else:
                stmt = select(t.c.chunk_uid, t.c.embedding).where(t.c.document_uid == document_uid)
            with Session(self._engine, future=True) as session:
                rows = session.execute(stmt).all()
            out: List[Dict[str, Any]] = []
            for row in rows:
                if with_document:
                    chunk_uid, vec, text = row
                else:
                    chunk_uid, vec = row
                    text = ""
                entry: Dict[str, Any] = {"chunk_uid": chunk_uid, "vector": list(vec)}
                if with_document:
                    entry["text"] = text or ""
                out.append(entry)
            return out
        except Exception:
            logger.exception(
                "[VECTOR][CLICKHOUSE] failed to fetch vectors for document_uid=%s",
                document_uid,
            )
            return []

    def get_chunks_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        try:
            t = self._orm_table
            stmt = select(t.c.chunk_uid, t.c.text, t.c.metadata, t.c.retrievable).where(t.c.document_uid == document_uid)
            with Session(self._engine, future=True) as session:
                rows = session.execute(stmt).all()
            out: List[Dict[str, Any]] = []
            for chunk_uid, text, metadata_raw, retrievable in rows:
                md = self._decode_metadata(metadata_raw, retrievable)
                out.append(
                    {
                        "chunk_uid": chunk_uid,
                        "text": text or "",
                        "metadata": md,
                    }
                )
            return out
        except Exception:
            logger.exception(
                "[VECTOR][CLICKHOUSE] failed to fetch chunks for document_uid=%s",
                document_uid,
            )
            return []

    def get_chunk(self, document_uid: str, chunk_uid: str) -> Dict[str, Any]:
        try:
            t = self._orm_table
            stmt = select(t.c.chunk_uid, t.c.text, t.c.metadata, t.c.retrievable).where(t.c.document_uid == document_uid, t.c.chunk_uid == chunk_uid).limit(1)
            with Session(self._engine, future=True) as session:
                rows = session.execute(stmt).all()
            if not rows:
                logger.warning("[VECTOR][CLICKHOUSE] chunk not found: %s", chunk_uid)
                return {"chunk_uid": chunk_uid}
            _, text, metadata_raw, retrievable = rows[0]
            return {
                "chunk_uid": chunk_uid,
                "text": text or "",
                "metadata": self._decode_metadata(metadata_raw, retrievable),
            }
        except Exception:
            logger.exception("[VECTOR][CLICKHOUSE] failed to fetch chunk %s", chunk_uid)
            return {"chunk_uid": chunk_uid}

    def delete_chunk(self, document_uid: str, chunk_uid: str) -> None:
        try:
            t = self._orm_table
            stmt = (
                select(func.count())
                .select_from(t)
                .where(
                    t.c.document_uid == document_uid,
                    t.c.chunk_uid == chunk_uid,
                )
            )
            with Session(self._engine, future=True) as session:
                exists = int(session.execute(stmt).scalar_one() or 0)
            if exists == 0:
                logger.warning(
                    "[VECTOR][CLICKHOUSE] cannot delete; chunk not found: %s",
                    chunk_uid,
                )
                return
            self._command(
                f"""
                ALTER TABLE {self._table_ref}
                DELETE WHERE document_uid = {{doc_uid:String}} AND chunk_uid = {{chunk_uid:String}}
                SETTINGS mutations_sync = 1
                """,
                {"doc_uid": document_uid, "chunk_uid": chunk_uid},
            )
            logger.debug(
                "[VECTOR][CLICKHOUSE] deleted chunk %s for document_uid=%s",
                chunk_uid,
                document_uid,
            )
        except Exception:
            logger.exception(
                "[VECTOR][CLICKHOUSE] failed to delete chunk %s for document_uid=%s",
                chunk_uid,
                document_uid,
            )

    def _build_hits(self, rows: List[tuple], hit_type: Type[T]) -> List[T]:
        now_iso = datetime.now(timezone.utc).isoformat()
        model_name = self._embedding_model_name or "unknown"
        results: List[T] = []

        for rank, row in enumerate(rows, start=1):
            chunk_uid, text, metadata_raw, retrievable, score = row
            meta = self._decode_metadata(metadata_raw, retrievable)
            meta.setdefault(CHUNK_ID_FIELD, chunk_uid)
            meta["score"] = float(score)
            meta["rank"] = rank
            meta["retrieved_at"] = now_iso
            meta.setdefault("embedding_model", model_name)
            meta.setdefault("vector_index", self._table)
            meta.setdefault("token_count", len((text or "").split()))

            doc = Document(page_content=text or "", metadata=meta)
            results.append(hit_type(document=doc, score=float(score)))
        return results

    def _build_ann_hits(self, rows: List[tuple]) -> List[AnnHit]:
        hits = self._build_hits(rows, AnnHit)
        if DEBUG and hits:
            logger.debug("[VECTOR][CLICKHOUSE][ANN] built hits count=%d", len(hits))
        return hits

    def _build_hybrid_hits(self, rows: List[tuple]) -> List[HybridHit]:
        hits = self._build_hits(rows, HybridHit)
        if DEBUG and hits:
            logger.debug("[VECTOR][CLICKHOUSE][HYBRID] built hits count=%d", len(hits))
        return hits

    def _build_fulltext_hits(self, rows: List[tuple]) -> List[FullTextHit]:
        hits = self._build_hits(rows, FullTextHit)
        if DEBUG and hits:
            logger.debug("[VECTOR][CLICKHOUSE][FULLTEXT] built hits count=%d", len(hits))
        return hits

    def _build_filter_conditions(self, search_filter: Optional[SearchFilter], table: Table) -> List[Any]:
        if not search_filter:
            return []
        conditions: List[Any] = []

        if search_filter.tag_ids:
            conditions.append(func.hasAny(table.c.tag_ids, [str(x) for x in search_filter.tag_ids]))

        direct_columns = {
            "document_uid": table.c.document_uid,
            "user_id": table.c.user_id,
            "session_id": table.c.session_id,
            "scope": table.c.scope,
        }

        if search_filter.metadata_terms:
            for field, values in search_filter.metadata_terms.items():
                values_list = _as_list(values)
                if not values_list:
                    continue

                if field == "retrievable":
                    want_true = any(_is_true_value(v) for v in values_list)
                    want_false = any(_is_false_value(v) for v in values_list)
                    if want_true and not want_false:
                        conditions.append(or_(table.c.retrievable == 1, table.c.retrievable.is_(None)))
                    elif want_false and not want_true:
                        conditions.append(or_(table.c.retrievable == 0, table.c.retrievable.is_(None)))
                    continue

                include_values, exclude_values = _split_metadata_values(values_list)
                col = direct_columns.get(field)

                if col is not None:
                    if include_values:
                        conditions.append(col.in_([str(v) for v in include_values]))
                    if exclude_values:
                        # Keep NULL values when excluding terms (e.g. scope != 'session'):
                        # in SQL, NOT IN over NULL yields NULL (filtered out) without this guard.
                        conditions.append(or_(col.is_(None), ~col.in_([str(v) for v in exclude_values])))
                    continue

                if not _SAFE_METADATA_FIELD.match(field):
                    logger.warning("[VECTOR][CLICKHOUSE][FILTER] ignoring unsupported metadata field '%s'", field)
                    continue

                json_expr = func.JSONExtractString(table.c.metadata, field)
                if include_values:
                    conditions.append(json_expr.in_([str(v) for v in include_values]))
                if exclude_values:
                    conditions.append(or_(json_expr.is_(None), ~json_expr.in_([str(v) for v in exclude_values])))

        return conditions

    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        logger.debug("[VECTOR][CLICKHOUSE][ANN] query=%r k=%d search_filter=%s", query, k, search_filter)
        if k <= 0:
            return []

        try:
            query_vector = self._embedding_model.embed_query(query)
        except Exception as e:
            logger.exception("[VECTOR][CLICKHOUSE] failed to compute embedding.")
            raise RuntimeError("Embedding model failed.") from e

        try:
            t = self._orm_table
            score = (1.0 - func.cosineDistance(t.c.embedding, [float(v) for v in query_vector])).label("score")
            stmt = select(t.c.chunk_uid, t.c.text, t.c.metadata, t.c.retrievable, score)
            for cond in self._build_filter_conditions(search_filter, t):
                stmt = stmt.where(cond)
            stmt = stmt.order_by(score.desc()).limit(int(k))
            with Session(self._engine, future=True) as session:
                rows = session.execute(stmt).all()
        except Exception as e:
            logger.warning("[VECTOR][CLICKHOUSE][ANN] query failed: %s", str(e))
            raise RuntimeError(str(e)) from e

        return self._build_ann_hits([tuple(r) for r in rows])

    def full_text_search(
        self,
        query: str,
        top_k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[FullTextHit]:
        if top_k <= 0:
            return []
        try:
            t = self._orm_table
            pos = func.positionCaseInsensitiveUTF8(t.c.text, query)
            score = (1.0 / (1.0 + pos)).label("score")
            stmt = select(t.c.chunk_uid, t.c.text, t.c.metadata, t.c.retrievable, score)
            for cond in self._build_filter_conditions(search_filter, t):
                stmt = stmt.where(cond)
            stmt = stmt.where(pos > 0).order_by(score.desc()).limit(int(top_k))
            with Session(self._engine, future=True) as session:
                rows = session.execute(stmt).all()
        except Exception as e:
            logger.warning("[VECTOR][CLICKHOUSE][FULLTEXT] query failed: %s", str(e))
            raise RuntimeError(str(e)) from e

        return self._build_fulltext_hits([tuple(r) for r in rows])

    def hybrid_search(
        self,
        query: str,
        top_k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[HybridHit]:
        if top_k <= 0:
            return []
        candidate_k = max(top_k * 2, top_k)
        ann_hits = self.ann_search(query=query, k=candidate_k, search_filter=search_filter)
        full_hits = self.full_text_search(query=query, top_k=candidate_k, search_filter=search_filter)

        ann_by_id: Dict[str, AnnHit] = {}
        for hit in ann_hits:
            cid = str(hit.document.metadata.get(CHUNK_ID_FIELD) or "")
            if cid:
                ann_by_id[cid] = hit
        full_by_id: Dict[str, FullTextHit] = {}
        for hit in full_hits:
            cid = str(hit.document.metadata.get(CHUNK_ID_FIELD) or "")
            if cid:
                full_by_id[cid] = hit

        ann_norm = _min_max_normalize({cid: float(hit.score) for cid, hit in ann_by_id.items()})
        full_norm = _min_max_normalize({cid: float(hit.score) for cid, hit in full_by_id.items()})

        merged_rows: List[tuple] = []
        for cid in set(ann_by_id.keys()) | set(full_by_id.keys()):
            combined = 0.5 * ann_norm.get(cid, 0.0) + 0.5 * full_norm.get(cid, 0.0)
            if combined <= 0:
                continue
            source_hit = ann_by_id.get(cid) or full_by_id.get(cid)
            if source_hit is None:
                continue
            doc_copy = copy.deepcopy(source_hit.document)
            md = _normalize_metadata(doc_copy.metadata or {})
            md[CHUNK_ID_FIELD] = cid
            retrievable = _as_nullable_uint8(md.get("retrievable"))
            metadata_raw = json.dumps(md, ensure_ascii=True)
            merged_rows.append((cid, doc_copy.page_content or "", metadata_raw, retrievable, float(combined)))

        merged_rows.sort(key=lambda row: float(row[4]), reverse=True)
        return self._build_hybrid_hits(merged_rows[:top_k])
