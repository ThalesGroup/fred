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

import logging
from app.common.structures import OutputProcessorResponse, Status
import pandas as pd
from langchain.schema.document import Document
import io
from fastapi import HTTPException
import dateparser


from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.common.vectorization_utils import load_langchain_doc_from_metadata
from app.core.processors.output.base_output_processor import BaseOutputProcessor

logger = logging.getLogger(__name__)


def parse_date(value: str) -> pd.Timestamp | None:
    dt = dateparser.parse(value, settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False})
    if dt:
        return pd.to_datetime(dt)
    return pd.NaT


class TabularProcessor(BaseOutputProcessor):
    """
    A pipeline for processing tabular data.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.tabular_store = self.context.get_tabular_store()
        logger.info("Initializing TabularPipeline")

    def process(self, file_path: str, metadata: DocumentMetadata) -> OutputProcessorResponse:
        try:
            logger.info(f"Processing file: {file_path} with metadata: {metadata}")

            # 1. Load the document
            document: Document =  load_langchain_doc_from_metadata(file_path, metadata)
            logger.debug(f"Document loaded: {document}")
            if not document:
                raise ValueError("Document is empty or not loaded correctly.")

            # 2. Load the DataFrame from the document
            df = pd.read_csv(io.StringIO(document.page_content))
            document_name = metadata.document_name.split(".")[0]
            for col in df.columns:
                if df[col].dtype == object:
                    sample_values = df[col].dropna().astype(str).head(10)
                    parsed_samples = sample_values.map(parse_date)
                    success_ratio = parsed_samples.notna().mean()
                    if success_ratio > 0.6 and parsed_samples.nunique() > 1:
                        logger.info(f"🕒 Parsing column '{col}' as datetime (score: {success_ratio:.2f})")
                        df[col] = df[col].astype(str).map(parse_date)

            logger.debug(f"document {document}")

            # 3. save the document into the selected tabular storage
            try:
                result = self.tabular_store.save_table(document_name, df)
                logger.debug(f"Document added to Tabular Store: {result}")
            except Exception as e:
                logger.exception("Failed to add documents to Tabular Storage: %s", e)
                raise HTTPException(status_code=500, detail="Failed to add documents to Tabular Storage") from e
            metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
            return OutputProcessorResponse(status=Status.SUCCESS)

        except Exception as e:
            logger.exception(f"Error during vectorization: {e}")
            raise HTTPException(status_code=500, detail=str(e))
