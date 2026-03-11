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

import io
import logging
import re
import asyncio

import dateparser
import pandas as pd
from langchain_core.documents import Document
from pandas._libs.tslibs.nattype import NaTType

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.asyncio_loop_context import get_current_asyncio_loop
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage
from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor, TabularProcessingError
from knowledge_flow_backend.core.processors.output.vectorization_processor.vectorization_utils import load_langchain_doc_from_metadata
from knowledge_flow_backend.features.tabular.registry_service import (
    TabularRegistryService,
    build_physical_table_name,
)

logger = logging.getLogger(__name__)

_DATE_REGEX = re.compile(
    r"""(
        \b\d{1,2}/\d{1,2}/\d{4}\b |
        \b\d{1,2}/\d{1,2}/\d{2}\b |
        \b\d{1,2}-\d{1,2}-\d{4}\b |
        \b\d{1,2}-\d{1,2}-\d{2}\b |
        \b\d{1,2}\.\d{1,2}\.\d{4}\b |
        \b\d{1,2}\.\d{1,2}\.\d{2}\b |
        \b\d{4}-\d{1,2}-\d{1,2}\b |
        \b\d{4}/\d{1,2}/\d{1,2}\b |
        \b\d{4}\.\d{1,2}\.\d{1,2}\b |

        \b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{2,4}\b |  # 1 Jan 2023
        \b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{1,2},?\s*\d{2,4}\b | # Jan 1, 2023

         \b\d{1,2}\s*(jan|fév|mar|avr|mai|jun|juin|juil|jui|aoû|sep|sept|oct|nov|déc)\s*\d{2,4}\b |  # 1 Fév 2023
        \b(jan|fév|mar|avr|mai|jun|juin|juil|jui|aoû|sep|sept|oct|nov|déc)\s*\d{1,2},?\s*\d{2,4}\b | # Fév 1, 2023

        \b\d{1,2}\s*(january|february|march|april|may|june|july|august|
                    september|october|november|december)\s*\d{2,4}\b |             # 1 January 2023
        \b(january|february|march|april|may|june|july|august|
            september|october|november|december)\s+\d{1,2},?\s*\d{2,4}\b |         # January 1, 2023

        \b\d{1,2}\s*(janvier|février|mars|avril|mai|juin|juillet|août|
                     septembre|octobre|novembre|décembre)\s*\d{2,4}\b |            # 1 septembre 2023
        \b(janvier|février|mars|avril|mai|juin|juillet|août|
            septembre|octobre|novembre|décembre)\s+\d{1,2},?\s*\d{2,4}\b           # septembre 1, 2023
    )""",
    re.IGNORECASE | re.VERBOSE,
)

def _looks_like_date(value: str) -> bool:
    """Check if the string matches a common date format (with separators or month names)."""
    return bool(_DATE_REGEX.search(value))


def _looks_like_compact_date(value: str) -> bool:
    """Check for compact date strings like YYYYMM or YYYYMMDD."""
    if not re.fullmatch(r"\d{6,8}", value):
        return False
    try:
        month = int(value[4:6])
        if not (1 <= month <= 12):
            return False
        if len(value) == 8:
            day = int(value[6:8])
            return 1 <= day <= 31
        return True
    except ValueError:
        return False


def _parse_date(value: str) -> pd.Timestamp | NaTType:
    """Attempt to parse a string into a pandas Timestamp using dateparser."""
    if not isinstance(value, str) or not any(c.isdigit() for c in value):
        return pd.NaT

    dt = dateparser.parse(value, settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False})

    if dt is None:
        return pd.NaT

    try:
        ts = pd.to_datetime(dt, errors="raise")
        return ts if ts.year >= 0 else pd.NaT
    except (ValueError, OverflowError):
        return pd.NaT


def is_valid_date(series: pd.Series, threshold: float = 0.7) -> bool:
    """
    Determine if a series contains mostly valid dates (above the given threshold).
    Uses both format heuristics and actual parsing.
    """
    values = series.dropna().astype(str)
    if values.empty:
        return False

    def is_parsable(value: str) -> bool:
        return (_looks_like_date(value) or _looks_like_compact_date(value)) and not bool(pd.isna(_parse_date(value)))

    valid_count = sum(is_parsable(val) for val in values)
    return (valid_count / len(values)) >= threshold


class TabularProcessor(BaseOutputProcessor):
    """
    A pipeline for processing tabular data.
    """

    description = "Loads tabular outputs, cleans column names, detects dates, and saves tables to the SQL store."

    def __init__(self):
        context = ApplicationContext.get_instance()
        self.csv_input_db_name, self.csv_input_store = context.get_csv_input_store_info()
        self.registry_service = TabularRegistryService(
            stores_info=context.get_tabular_stores(),
            registry_store=context.get_tabular_dataset_registry_store(),
            metadata_store=context.get_metadata_store(),
        )

        logger.info("Initializing TabularPipeline")

    def _schedule_registry_upsert(self, metadata: DocumentMetadata, row_count: int) -> None:
        coro = self.registry_service.upsert_for_metadata(
            metadata,
            db_name=self.csv_input_db_name,
            row_count=row_count,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            owner_loop = get_current_asyncio_loop()
            if owner_loop is not None and owner_loop.is_running() and not owner_loop.is_closed():
                asyncio.run_coroutine_threadsafe(coro, owner_loop).result()
                return
            asyncio.run(coro)
            return

        task = loop.create_task(coro)
        task.add_done_callback(lambda completed: self._log_registry_failure(metadata.document_uid, completed))

    @staticmethod
    def _log_registry_failure(document_uid: str, task: asyncio.Task) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.error(
                "Failed to upsert tabular dataset registry for %s",
                document_uid,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        try:
            logger.info(f"Processing file: {file_path} with metadata: {metadata}")

            document: Document = load_langchain_doc_from_metadata(file_path, metadata)
            logger.debug(f"Document loaded: {document}")
            if not document:
                raise ValueError("Document is empty or not loaded correctly.")

            df = pd.read_csv(io.StringIO(document.page_content))
            df.columns = [sanitize_sql_name(col) for col in df.columns]

            for col in df.select_dtypes(include=["object"]).columns:
                sample = pd.Series(df[col].dropna().astype(str).head(20))
                if not sample.empty and is_valid_date(sample, threshold=0.7):
                    logger.info(f"🕒 Parsing column '{col}' as datetime")
                    df[col] = df[col].astype(str).map(_parse_date)

            logger.debug(f"document {document}")

            try:
                if self.csv_input_store is None:
                    raise RuntimeError("csv_input_store is not initialized")

                table_name = build_physical_table_name(metadata.document_uid)
                result = self.csv_input_store.save_table(table_name, df)
                logger.debug(f"Document added to Tabular Store: {result}")
                self._schedule_registry_upsert(metadata, len(df.index))
            except Exception as e:
                logger.exception("Failed to add documents to Tabular Storage")
                raise TabularProcessingError("Failed to add documents to Tabular Storage") from e

            metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
            return metadata

        except Exception as e:
            logger.exception("Unexpected error during tabular processing")
            raise TabularProcessingError("Tabular processing failed") from e
