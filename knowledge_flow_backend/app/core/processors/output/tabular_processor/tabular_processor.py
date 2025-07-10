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
import pandas as pd
from langchain.schema.document import Document
import io
from fastapi import HTTPException


from app.application_context import ApplicationContext
from app.common.structures import Status, OutputProcessorResponse
from app.core.processors.output.base_output_processor import BaseOutputProcessor

from app.core.stores.tabular.duckdb_tabular_store_factory import get_tabular_store

logger = logging.getLogger(__name__)


class TabularProcessor(BaseOutputProcessor):
    """
    A pipeline for processing tabular data.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.file_loader = self.context.get_document_loader()
        logger.info(f"📄 Document loader initialized: {self.file_loader.__class__.__name__}")

        self.tabular_store = get_tabular_store()
        logger.info("Initializing TabularPipeline")

    def process(self, file_path: str, metadata: dict) -> OutputProcessorResponse:
        try:
            logger.info(f"Processing file: {file_path} with metadata: {metadata}")

            # 1. Load the document
            document: Document = self.file_loader.load(file_path, metadata)
            logger.debug(f"Document loaded: {document}")
            if not document:
                raise ValueError("Document is empty or not loaded correctly.")
            
            # 2. Load the DataFrame from the document
            df = pd.read_csv(io.StringIO(document.page_content))
            document_name = metadata.get("document_name").split('.')[0]

            logger.info(document)
            
            # 3. save the document into the selected tabular storage            
            try:
                result = self.tabular_store.save_table(document_name, df)
                logger.debug(f"Document added to Tabular Store: {result}")
            except Exception as e:
                logger.exception("Failed to add documents to Tabular Storage: %s", e)
                raise HTTPException(status_code=500, detail="Failed to add documents to Tabular Storage") from e

            return OutputProcessorResponse(status=Status.SUCCESS)
        
        except Exception as e:
            logger.exception(f"Error during vectorization: {e}")
            raise HTTPException(status_code=500, detail=str(e))


