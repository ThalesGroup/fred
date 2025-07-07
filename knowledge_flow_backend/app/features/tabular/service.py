# tabular_service.py

import pandas as pd
import io
import logging
from typing import List
from pandas.api.types import (
    is_string_dtype, is_numeric_dtype, is_bool_dtype, is_datetime64_any_dtype
)

from knowledge_flow_app.features.tabular.structures import TabularColumnSchema, TabularDatasetMetadata, TabularQueryRequest, TabularQueryResponse, TabularSchemaResponse
from knowledge_flow_app.features.content.service import ContentService

logger = logging.getLogger(__name__)


class TabularService:
    def __init__(self):
        self.content_service = ContentService()

    def _read_csv(self, document_uid: str) -> pd.DataFrame:
        stream = self._read_stream(document_uid)
        try:
            df = pd.read_csv(stream)
            logger.debug(f"Raw columns from CSV [{document_uid}]: {list(df.columns)}")
            df.columns = [col.strip() for col in df.columns]
            logger.debug(f"Normalized columns for [{document_uid}]: {list(df.columns)}")
            return df
        except Exception as e:
            logger.exception(f"Failed to read CSV for {document_uid}")
            raise ValueError(f"Failed to read CSV for {document_uid}: {str(e)}")

    def _read_stream(self, document_uid: str) -> io.StringIO:
        stream = self.content_service.content_store.get_content(document_uid)
        raw_bytes = stream.read()
        return io.StringIO(raw_bytes.decode("utf-8"))

    def get_schema(self, document_uid: str) -> TabularSchemaResponse:
        df = self._read_csv(document_uid)

        columns: List[TabularColumnSchema] = []
        for col in df.columns:
            dtype = self._map_dtype(df[col])
            columns.append(TabularColumnSchema(name=col, dtype=dtype))

        return TabularSchemaResponse(
            document_uid=document_uid,
            columns=columns,
            row_count=len(df)
        )

    def query(self, document_uid: str, query: TabularQueryRequest) -> TabularQueryResponse:
        df = self._read_csv(document_uid)
        logger.debug(f"Query request on [{document_uid}]: {query.model_dump()}")

        if query.filters:
            for col, value in query.filters.items():
                if col not in df.columns:
                    logger.error(f"Filter error: column '{col}' not in {list(df.columns)}")
                    raise KeyError(f"Column '{col}' not found in CSV columns: {list(df.columns)}")
                logger.debug(f"Applying filter: {col} == {value}")
                df = df[df[col] == value]

        if query.columns:
            logger.debug(f"Selecting columns: {query.columns}")
            df = df[query.columns]

        if query.limit:
            logger.debug(f"Applying limit: {query.limit}")
            df = df.head(query.limit)

        rows = df.to_dict(orient="records")
        logger.debug(f"Returning {len(rows)} rows for [{document_uid}]")
        return TabularQueryResponse(
            document_uid=document_uid,
            rows=rows
        )

    def rquery(self, document_uid: str, query: TabularQueryRequest) -> TabularQueryResponse:
        df = self._read_csv(document_uid)
        logger.debug(f"Query request on [{document_uid}]: {query.model_dump()}")

        if query.columns:
            logger.debug(f"Selecting columns: {query.columns}")
            df = df[query.columns]

        if query.filters:
            for col, value in query.filters.items():
                if col not in df.columns:
                    logger.error(f"Filter error: column '{col}' not in {list(df.columns)}")
                    raise KeyError(f"Column '{col}' not found in CSV columns: {list(df.columns)}")
                logger.debug(f"Applying filter: {col} == {value}")
                df = df[df[col] == value]

        if query.limit:
            logger.debug(f"Applying limit: {query.limit}")
            df = df.head(query.limit)

        rows = df.to_dict(orient="records")
        logger.debug(f"Returning {len(rows)} rows for [{document_uid}]")
        return TabularQueryResponse(
            document_uid=document_uid,
            rows=rows
        )

    def _map_dtype(self, series: pd.Series) -> str:
        if is_string_dtype(series):
            return "string"
        elif is_numeric_dtype(series):
            return "float" if any(series.apply(lambda x: isinstance(x, float))) else "integer"
        elif is_bool_dtype(series):
            return "boolean"
        elif is_datetime64_any_dtype(series):
            return "datetime"
        else:
            return "unknown"
        
    def list_tabular_datasets(self) -> List[TabularDatasetMetadata]:
        all_metadata = self.content_service.metadata_store.get_all_metadata(filters={})
        tabular_metadata = []

        for meta in all_metadata:
            file_name = meta.get("document_name", "")
            if not file_name.lower().endswith(".csv"):
                continue

            tabular_metadata.append(TabularDatasetMetadata(
                document_uid=meta["document_uid"],
                title=meta.get("title", file_name),
                description=meta.get("description", ""),
                tags=meta.get("tags", []),
                domain=meta.get("domain", ""),
                row_count=meta.get("row_count")  # optional: populate during ingestion
            ))

        return tabular_metadata
