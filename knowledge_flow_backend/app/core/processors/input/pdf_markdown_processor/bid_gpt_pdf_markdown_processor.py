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

import PyPDF2
from pathlib import Path
import pypandoc
import shutil
import logging

from knowledge_flow_app.processors.base_file_processor import BaseFileProcessor

# Initialiser le logger
logger = logging.getLogger("bidgpt_api")
class PdfProcessor(BaseFileProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        """Vérifie si le PDF est lisible (exemple simplifié)."""
        try:
            with open(file_path, 'rb') as f:
                PyPDF2.PdfReader(f)  # va lever une erreur si le PDF est corrompu
            return True
        except PyPDF2.errors.PdfReadError as e:
            logger.error(f"Fichier PDF corrompu: {file_path} - {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue en vérifiant {file_path}: {e}")
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        if not self.check_structure(file_path):
            return {"document_name": file_path.name, "error": "Invalid PDF structure"}

        metadata = {}
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                info = reader.metadata  # PyPDF2 v3.x (>= 3.0.0), auparavant c'était reader.getDocumentInfo()

                # Certains champs possibles dans le PDF
                metadata["title"] = info.title
                metadata["author"] = info.author
                metadata["subject"] = info.subject
                # ...

            # Ajout des champs communs
            metadata = self.add_common_metadata(metadata, file_path)

            # Génération de l'UID
            unique_id = self.generate_unique_id(metadata)
            metadata["document_uid"] = unique_id

            return {k: v for k, v in metadata.items() if v}
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des métadonnées PDF: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str) -> dict:

        doc_dir = output_dir / document_uid
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Copier le PDF d’origine
        shutil.copy(file_path, doc_dir / "file.pdf")

        md_path = doc_dir / "file.md"

        # On tente la conversion PDF → markdown avec pypandoc
        # NB : La qualité de la conversion dépend de la structure du PDF
        try:
            pypandoc.convert_file(str(file_path), 'markdown', outputfile=str(md_path))
        except Exception as e:
            logger.error(f"Impossible de convertir le PDF en Markdown: {e}")

        return {"doc_dir": str(doc_dir), "md_file": str(md_path)}
