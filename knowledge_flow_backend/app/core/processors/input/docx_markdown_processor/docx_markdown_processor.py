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

import zipfile
import logging
from datetime import datetime
from pathlib import Path
from docx import Document

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
import subprocess

logger = logging.getLogger(__name__)


def default_or_unknown(value: str, default="None") -> str:
    return value.strip() if value and value.strip() else default


class DocxMarkdownProcessor(BaseMarkdownProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        try:
            with zipfile.ZipFile(file_path, "r") as docx_zip:
                return "word/document.xml" in docx_zip.namelist()
        except zipfile.BadZipFile:
            logger.error(f"{file_path} n'est pas une archive ZIP valide.")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la vérification de {file_path}: {e}")
        return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        try:
            doc = Document(file_path)
            return {
                "title": default_or_unknown(doc.core_properties.title),
                "author": default_or_unknown(doc.core_properties.author),
                "created": (doc.core_properties.created.isoformat() if isinstance(doc.core_properties.created, datetime) else "Non disponible"),
                "modified": (doc.core_properties.modified.isoformat() if isinstance(doc.core_properties.modified, datetime) else "Non disponible"),
                "last_modified_by": default_or_unknown(doc.core_properties.last_modified_by),
                "category": default_or_unknown(doc.core_properties.category),
                "subject": default_or_unknown(doc.core_properties.subject),
                "keywords": default_or_unknown(doc.core_properties.keywords),
            }
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des métadonnées pour {file_path}: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        images_dir = output_dir
        extra_args = [f"--extract-media={images_dir}", "--preserve-tabs", "--wrap=none", "--reference-links"]

        subprocess.run(
            [
                "pandoc",
                "--to",
                "markdown",
                "--to",
                "markdown_strict",
                str(file_path),
                "-o",
                str(md_path),
                *extra_args,
            ],
        )

        # pypandoc.convert_file(str(file_path), to="markdown_strict+pipe_tables", outputfile=str(md_path), extra_args=extra_args)

        # Convert EMF to SVG
        for img_path in (images_dir / "media").glob("*.emf"):
            svg_path = img_path.with_suffix(".svg")
            subprocess.run(["inkscape", str(img_path), "--export-filename=" + str(svg_path)])

            # Remove the original EMF file
            img_path.unlink()

        # Update references in the markdown file
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        md_content = md_content.replace(".emf", ".svg")

        # Change media path to use api endpoint
        md_content = md_content.replace(str(output_dir), f"knowledge-flow/v1/markdown/{document_uid}")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        for f in output_dir.glob("*.lua"):
            f.unlink()

        return {"doc_dir": str(output_dir), "md_file": str(md_path)}
