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

from pathlib import Path

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor


class MarkdownMarkdownProcessor(BaseMarkdownProcessor):
    description = "Normalizes existing Markdown files into the expected output.md preview."

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.exists() and file_path.suffix in [".md"]

    def extract_file_metadata(self, file_path: Path) -> dict:
        return {
            "document_name": file_path.name,
            "size_bytes": file_path.stat().st_size,
            "suffix": file_path.suffix,
        }

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"
        with open(file_path, "r", encoding="utf-8") as f_in, open(md_path, "w", encoding="utf-8") as f_out:
            f_out.write(f_in.read())
        return {"doc_dir": str(output_dir), "md_file": str(md_path)}
